import os
import pandas as pd
import logging
from dotenv import load_dotenv
from langchain_classic.evaluation.qa import QAEvalChain
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, AIMessage
from tqdm import tqdm
import time
from datetime import datetime

# --- SETUP ---
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("evals")
logger.setLevel(logging.INFO)
load_dotenv()

# --- AGENT V2.0 IMPORTS (NEW) ---
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "../backend"))
from src.agent.workflow import app
from src.agent.state import AgentState
from src.rate_limiter import throttle


def extract_sql_from_messages(messages: list[BaseMessage]) -> str:
    """
    Parses the entire message history to find all tool calls and their results,
    then formats them into a readable SQL execution log.
    """
    if not messages:
        return "No messages in history."

    log_entries = []

    # Find all AIMessages with tool calls throughout the history
    tool_calls = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if "args" in tc and "query" in tc["args"]:
                    tool_calls.append({"id": tc["id"], "query": tc["args"]["query"]})

    # Find corresponding ToolMessages with results
    tool_results = {
        msg.tool_call_id: msg.content
        for msg in messages
        if isinstance(msg, ToolMessage)
    }

    if not tool_calls:
        return "No SQL queries were executed."

    for i, call in enumerate(tool_calls, 1):
        query_text = call["query"].replace("\n", " ")
        result = tool_results.get(call["id"], "Execution result not found.")
        success = "error" not in str(result).lower()
        status = "✓" if success else "✗"
        rows_returned = str(result).count("\n") if success and result else 0

        log_entries.append(f"{i}. {status} [Rows: {rows_returned}] {query_text}")
        if not success:
            error_msg = str(result).replace("\n", " ")
            log_entries.append(f"   ERROR: {error_msg}")

    return "\n".join(log_entries)


def run_agent_on_question(question: str) -> AgentState:
    """
    Initializes the agent with the user's question and runs the graph.
    """
    # Define the initial state for our new, simplified graph
    initial_state = AgentState(
        input=question, messages=[HumanMessage(content=question)], iteration_count=0
    )

    try:
        # Invoke the LangGraph app
        response_state = app.invoke(
            initial_state,
            config={"callbacks": []},
        )
        return response_state
    except Exception as e:
        logger.error(
            f"Agent execution failed for question '{question}': {e}", exc_info=True
        )
        # Return a mock state to prevent crashing the whole evaluation
        return {
            "messages": [AIMessage(content=f"Error: {e}")],
            "selected_tables": [],
            "table_selection_reasoning": "Agent crashed during execution.",
        }


def main():
    """Main function to run the evaluation script for the new agent."""
    logger.info("--- Starting Agent Evaluation (V2.0 Architecture) ---")

    output_dir = "eval_results"
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = os.path.join(output_dir, f"eval_report_v2_{timestamp}.csv")
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
    logger.info("Running agent on all test questions...")

    for index, row in tqdm(test_set_df.iterrows(), total=test_set_df.shape[0]):
        question = row["question"]
        ground_truth = row["ground_truth_answer"]

        final_state = run_agent_on_question(question)

        # The final answer is the content of the last message in the state
        predicted_answer = "Error: No final message found."
        if final_state.get("messages"):
            predicted_answer = final_state["messages"][-1].content

        # Extract relevant debug info from the new state
        executed_sql = extract_sql_from_messages(final_state.get("messages", []))

        all_predictions_with_state.append(
            {
                "question_id": row.get("question_id", index),
                "question": question,
                "ground_truth_answer": ground_truth,
                "predicted_answer": predicted_answer,
                "selected_tables": str(final_state.get("selected_tables", [])),
                "table_selection_reasoning": final_state.get(
                    "table_selection_reasoning", "N/A"
                ),
                "executed_sql": executed_sql,
            }
        )

    logger.info("Starting LLM-as-a-judge evaluation for all answers...")

    class JudgeRateLimiter(BaseCallbackHandler):
        def on_llm_start(self, *args, **kwargs):
            throttle()
        def on_chat_model_start(self, *args, **kwargs):
            throttle()

    eval_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
    eval_chain = QAEvalChain.from_llm(llm=eval_llm)

    examples = [
        {"query": p["question"], "answer": p["ground_truth_answer"]}
        for p in all_predictions_with_state
    ]
    predictions_list = [
        {"result": p["predicted_answer"]} for p in all_predictions_with_state
    ]

    results = eval_chain.evaluate(
        examples,
        predictions_list,
        question_key="query",
        answer_key="answer",
        prediction_key="result",
        callbacks=[JudgeRateLimiter()],
    )

    total_questions = len(results)
    correct_answers = 0
    detailed_results_list = []

    logger.info("\n--- Detailed Evaluation Results ---")
    for i, result in enumerate(results):
        turn_data = all_predictions_with_state[i]
        grade_string = result.get("results", "ERROR").strip()

        # Use the stricter check for correctness
        is_correct = grade_string.strip().upper() == "CORRECT"

        if is_correct:
            correct_answers += 1
            grade = "CORRECT"
        else:
            logger.error(f"❌ FAILED - Q: {turn_data['question']}")
            logger.error(f"  - Ground Truth: {turn_data['ground_truth_answer']}")
            logger.error(f"  - Prediction:   {turn_data['predicted_answer']}")
            logger.error(f"  - LLM Grade:    {grade_string}")
            logger.error(f"  - Reasoning:    {turn_data['table_selection_reasoning']}")
            logger.error(f"  - SQL Executed:\n{turn_data['executed_sql']}")
            grade = "INCORRECT"

        turn_data["grade"] = grade
        turn_data["llm_judge_feedback"] = grade_string
        detailed_results_list.append(turn_data)

    results_df = pd.DataFrame(detailed_results_list)
    results_df.to_csv(output_filename, index=False, encoding="utf-8")
    logger.info(f"✅ Detailed evaluation report saved to {output_filename}")

    if total_questions > 0:
        accuracy = (correct_answers / total_questions) * 100
        logger.info("\n" + "=" * 40)
        logger.info("        EVALUATION SUMMARY (V2.0)")
        logger.info("=" * 40)
        logger.info(f"  Total Questions: {total_questions}")
        logger.info(f"  Correct Answers: {correct_answers}")
        logger.info(f"  Accuracy:        {accuracy:.2f}%")
        logger.info("=" * 40)
    else:
        logger.warning("No results to evaluate.")


if __name__ == "__main__":
    main()
