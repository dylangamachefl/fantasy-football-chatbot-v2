import os
import pandas as pd
import logging
from dotenv import load_dotenv
from langchain_classic.evaluation.qa import QAEvalChain
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from tqdm import tqdm
import time
from datetime import datetime

# --- SETUP ---
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("evals")
logger.setLevel(logging.INFO)
load_dotenv()

# --- AGENT V3 IMPORTS ---
from graph_builder_v3 import app  # This is graph_builder_v3 (deterministic)
from agent_state_v3 import create_initial_state, AgentState, QueryMetadata


class RateLimitingCallbackHandler(BaseCallbackHandler):
    """(Unchanged)"""

    def __init__(self, delay_seconds: int = 5):
        self.delay_seconds = delay_seconds
        logger.info(
            f"[Callback] Rate Limiter initialized with a {self.delay_seconds}s delay."
        )

    def _rate_limit(self, event_name: str) -> None:
        logger.info(
            f"[Callback] Triggered by {event_name}. Waiting for {self.delay_seconds} seconds..."
        )
        time.sleep(self.delay_seconds)
        logger.info("[Callback] ...Resuming.")

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs) -> None:
        self._rate_limit("on_llm_start")

    def on_chat_model_start(
        self, serialized: dict, messages: list[list[BaseMessage]], **kwargs
    ) -> None:
        self._rate_limit("on_chat_model_start")


def format_sql_queries(queries: list[QueryMetadata]) -> str:
    """(Unchanged)"""
    if not queries:
        return "No queries executed."

    formatted = []
    for i, q in enumerate(queries, 1):
        status = "✓" if q.get("success") else "✗"
        query_text = q.get("query_text", "N/A").replace("\n", " ")
        rows = q.get("rows_returned", 0)

        formatted.append(f"{i}. {status} [Rows: {rows}] {query_text}")

        if not q.get("success"):
            error_msg = str(q.get("error_message", "Unknown Error")).replace("\n", " ")
            formatted.append(f"   ERROR: {error_msg}")

    return "\n".join(formatted)


def run_agent_on_question(question: str) -> AgentState:
    """(Unchanged)"""
    rate_limit_callback = RateLimitingCallbackHandler(delay_seconds=5)
    input_state = create_initial_state(question)

    try:
        response_state = app.invoke(
            input_state,
            config={"callbacks": [rate_limit_callback]},
        )
        return response_state
    except Exception as e:
        logger.error(f"Agent execution failed for question '{question}': {e}")
        return {
            "final_answer": f"Error: {e}",
            "error": str(e),
            "executed_queries": [],
            "validation_errors": [str(e)],
            "messages": [],
        }


def main():
    """Main function to run the SIMPLE evaluation script."""
    logger.info("--- Starting SIMPLE (V3) Agent Evaluation ---")

    output_dir = "eval_results"
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = os.path.join(output_dir, f"eval_report_simple_{timestamp}.csv")
    logger.info(f"Evaluation results will be saved to: {output_filename}")

    try:
        test_set_df = pd.read_csv("data/test_set_simple.csv")
        logger.info(
            f"Loaded {len(test_set_df)} questions from data/test_set_simple.csv"
        )
    except FileNotFoundError:
        logger.error(
            "FATAL: data/test_set_simple.csv not found. Please create it first."
        )
        return

    all_predictions_with_state = []
    logger.info("Running agent on all simple questions...")

    for index, row in tqdm(test_set_df.iterrows(), total=test_set_df.shape[0]):
        question = row["question"]
        ground_truth = row["ground_truth_answer"]
        final_state = run_agent_on_question(question)
        executed_sql = format_sql_queries(final_state.get("executed_queries", []))

        react_agent_handoff = ""
        if final_state.get("messages"):
            react_agent_handoff = str(final_state["messages"][-1].content)

        synthesized_answer = final_state.get("synthesized_answer", "N/A")

        all_predictions_with_state.append(
            {
                "question_id": row.get("question_id", index),
                "question": question,
                "ground_truth_answer": ground_truth,
                "predicted_answer": final_state.get(
                    "final_answer", "Error: No final_answer"
                ),
                "enhanced_query": final_state.get("enhanced_query", ""),
                "query_type": final_state.get("query_type", ""),
                "selected_tables": str(final_state.get("selected_tables", [])),
                "executed_sql": executed_sql,
                "validation_errors": str(final_state.get("validation_errors", [])),
                "react_agent_handoff": react_agent_handoff,
                "synthesized_answer": synthesized_answer,
            }
        )

    logger.info("Starting LLM-as-a-judge evaluation for all questions...")
    eval_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
    eval_chain = QAEvalChain.from_llm(llm=eval_llm)

    examples = [
        {"query": p["question"], "answer": p["ground_truth_answer"]}
        for p in all_predictions_with_state
    ]
    predictions_list = [
        {"result": p["predicted_answer"]} for p in all_predictions_with_state
    ]

    eval_rate_limiter = RateLimitingCallbackHandler(delay_seconds=5)
    results = eval_chain.evaluate(
        examples,
        predictions_list,
        question_key="query",
        answer_key="answer",
        prediction_key="result",
        callbacks=[eval_rate_limiter],
    )

    total_questions = len(results)
    correct_answers = 0
    detailed_results_list = []

    logger.info("\n--- Detailed Simple Evaluation Results ---")
    for i, result in enumerate(results):
        turn_data = all_predictions_with_state[i]
        grade_string = result.get("results", "ERROR").strip()

        # --- FIXED: Stricter check for correctness ---
        is_correct = grade_string.strip().upper() == "CORRECT"

        if is_correct:
            correct_answers += 1
            grade = "CORRECT"
        else:
            logger.error(f"❌ FAILED - Q: {turn_data['question']}")
            logger.error(f"  - Ground Truth: {turn_data['ground_truth_answer']}")
            logger.error(f"  - Prediction:   {turn_data['predicted_answer']}")
            logger.error(f"  - LLM Grade:    {grade_string}")
            logger.error(f"  - SQL Executed: {turn_data['executed_sql']}")
            logger.error(f"  - Agent Handoff: {turn_data['react_agent_handoff']}")
            logger.error(f"  - Synthesizer:   {turn_data['synthesized_answer']}")
            grade = "INCORRECT"

        turn_data["grade"] = grade
        turn_data["llm_judge_feedback"] = grade_string
        detailed_results_list.append(turn_data)

    results_df = pd.DataFrame(detailed_results_list)
    results_df.to_csv(output_filename, index=False, encoding="utf-8")
    logger.info(f"✅ Detailed simple eval report saved to {output_filename}")

    if total_questions > 0:
        accuracy = (correct_answers / total_questions) * 100
        logger.info("\n" + "=" * 40)
        logger.info("         SIMPLE EVALUATION SUMMARY (V3)")
        logger.info("=" * 40)
        logger.info(f"  Total Questions: {total_questions}")
        logger.info(f"  Correct Answers: {correct_answers}")
        logger.info(f"  Accuracy:        {accuracy:.2f}%")
        logger.info("=" * 40)
    else:
        logger.warning("No results to evaluate.")


if __name__ == "__main__":
    main()
