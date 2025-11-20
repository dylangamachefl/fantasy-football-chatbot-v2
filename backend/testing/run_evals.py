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
# Configure logging to suppress verbose output from libraries
logging.basicConfig(level=logging.WARNING)
# Set a specific logger for our eval script
logger = logging.getLogger("evals")
logger.setLevel(logging.INFO)

load_dotenv()


# --- In run_evals.py ---
# --- REPLACE the entire class with this ---


class RateLimitingCallbackHandler(BaseCallbackHandler):
    """
    A custom callback to enforce a delay before EACH LLM call.
    It implements BOTH on_llm_start (for legacy chains like QAEvalChain)
    and on_chat_model_start (for our modern agent).
    """

    def __init__(self, delay_seconds: int = 5):
        self.delay_seconds = delay_seconds
        logger.info(
            f"[Callback] Rate Limiter initialized with a {self.delay_seconds}s delay."
        )

    def _rate_limit(self, event_name: str) -> None:
        """Helper function to log and sleep."""
        logger.info(
            f"[Callback] Triggered by {event_name}. Waiting for {self.delay_seconds} seconds..."
        )
        time.sleep(self.delay_seconds)
        logger.info("[Callback] ...Resuming.")

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs) -> None:
        """Called by legacy chains (like QAEvalChain)."""
        self._rate_limit("on_llm_start")

    def on_chat_model_start(
        self, serialized: dict, messages: list[list[BaseMessage]], **kwargs
    ) -> None:
        """Called by modern chat models (like our agent)."""
        self._rate_limit("on_chat_model_start")


# --- The NEW way for run_evals.py ---
from graph_builder import app  # <-- Import our NEW compiled langgraph app
from langchain_core.messages import HumanMessage


def run_agent_on_question(question: str):
    """
    A simplified, non-Streamlit function to run the AGENT GRAPH
    for a single question.
    """
    rate_limit_callback = RateLimitingCallbackHandler(delay_seconds=5)  #
    # Our new graph takes a state dictionary as input
    input_state = {
        "input": question,
        "history": [],  # Evals should be stateless
        "agent_scratchpad": [],  # Always start with a clean scratchpad
    }

    try:
        # We invoke the entire graph, not just one function
        response = app.invoke(
            input_state,
            # We pass our callbacks here for LangSmith tracing
            config={"callbacks": [rate_limit_callback]},
        )
        # The final answer is now in 'final_answer' from our AgentState
        return response.get("final_answer", "Error: No final_answer key found.")
    except Exception as e:
        logger.error(f"Agent execution failed for question '{question}': {e}")
        return f"Error: {e}"


def main():
    """
    Main function to run the evaluation script and save the results.
    """
    logger.info("--- Starting Baseline Evaluation ---")

    # --- 1. SETUP FILENAME AND DIRECTORY ---
    output_dir = "eval_results"
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = os.path.join(output_dir, f"eval_report_{timestamp}.csv")
    logger.info(f"Evaluation results will be saved to: {output_filename}")

    try:
        test_set_df = pd.read_csv("data/test_set.csv")
        logger.info(f"Loaded {len(test_set_df)} questions from test_set.csv")
    except FileNotFoundError:
        logger.error("FATAL: test_set.csv not found. Please create it first.")
        return

    predictions = []
    logger.info("Running agent on all questions...")

    for index, row in tqdm(test_set_df.iterrows(), total=test_set_df.shape[0]):
        question = row["question"]
        predicted_answer = run_agent_on_question(question)
        predictions.append(
            {
                "question": question,
                "ground_truth_answer": row["ground_truth_answer"],
                "predicted_answer": predicted_answer,
            }
        )

    logger.info("Starting LLM-as-a-judge evaluation...")

    eval_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
    eval_chain = QAEvalChain.from_llm(llm=eval_llm)

    examples = []
    for pred in predictions:
        examples.append(
            {"query": pred["question"], "answer": pred["ground_truth_answer"]}
        )

    eval_rate_limiter = RateLimitingCallbackHandler(delay_seconds=5)

    results = eval_chain.evaluate(
        examples,
        [{"result": p["predicted_answer"]} for p in predictions],
        question_key="query",
        answer_key="answer",
        prediction_key="result",
        callbacks=[eval_rate_limiter],
    )

    total_questions = len(results)
    correct_answers = 0

    # --- 2. COLLECT DETAILED RESULTS FOR SAVING ---
    detailed_results_list = []

    logger.info("\n--- Detailed Evaluation Results ---")
    for i, result in enumerate(results):
        question = predictions[i]["question"]
        truth = predictions[i]["ground_truth_answer"]
        prediction = predictions[i]["predicted_answer"]
        grade_string = result.get("results", "ERROR").strip()

        is_correct = "correct" in grade_string.lower()

        if is_correct:
            correct_answers += 1
            logger.info(f"✅ PASSED - Q: {question}")
            grade = "CORRECT"
        else:
            logger.error(f"❌ FAILED - Q: {question}")
            logger.error(f"  - Ground Truth: {truth}")
            logger.error(f"  - Prediction:   {prediction}")
            logger.error(f"  - LLM Grade:    {grade_string}")
            grade = "INCORRECT"

        detailed_results_list.append(
            {
                "question": question,
                "ground_truth_answer": truth,
                "predicted_answer": prediction,
                "grade": grade,
                "llm_judge_feedback": grade_string,
            }
        )

    # --- 3. SAVE THE RESULTS DATAFRAME TO CSV ---
    results_df = pd.DataFrame(detailed_results_list)
    results_df.to_csv(output_filename, index=False, encoding="utf-8")
    logger.info(f"✅ Detailed evaluation report saved to {output_filename}")

    if total_questions > 0:
        accuracy = (correct_answers / total_questions) * 100
        logger.info("\n" + "=" * 40)
        logger.info("           EVALUATION SUMMARY")
        logger.info("=" * 40)
        logger.info(f"  Total Questions: {total_questions}")
        logger.info(f"  Correct Answers: {correct_answers}")
        logger.info(f"  Accuracy: {accuracy:.2f}%")
        logger.info("=" * 40)
    else:
        logger.warning("No results to evaluate.")


if __name__ == "__main__":
    main()
