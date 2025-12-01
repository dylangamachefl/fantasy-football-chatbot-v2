import os
import sys
import pandas as pd
import logging
import uuid
import argparse
import time
from datetime import datetime
from tqdm import tqdm
from dotenv import load_dotenv
from langchain_classic.evaluation.qa import QAEvalChain
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver

# --- IMPORT WORKFLOW ---
sys.path.append(os.path.join(os.path.dirname(__file__), "../backend"))
from src.agent.workflow import workflow
from src.agent.state import AgentState

# --- SETUP ---
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("evals")
logger.setLevel(logging.INFO)
load_dotenv()

# --- COMPILE GRAPH WITH MEMORY ---
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)


class RateLimitingCallbackHandler(BaseCallbackHandler):
    """Callback to add a delay between LLM calls to avoid rate limiting."""

    def __init__(self, delay_seconds: int = 5):
        self.delay_seconds = delay_seconds

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs) -> None:
        time.sleep(self.delay_seconds)

    def on_chat_model_start(self, serialized: dict, messages: list, **kwargs) -> None:
        time.sleep(self.delay_seconds)


def extract_last_turn_sql(messages: list) -> str:
    """Extracts ONLY the SQL executed in the most recent turn."""
    if not messages:
        return "No messages."
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.get("name") == "sql_db_query":
                    return tc["args"].get("query", "No query found in args")
    return "No SQL executed this turn."


def run_conversation_turn(question: str, thread_id: str) -> AgentState:
    """Runs a single turn of the conversation using the persistent thread_id."""
    # FIX: Increased delay to 5s to stay safely under 15 RPM
    rate_limit = RateLimitingCallbackHandler(delay_seconds=5)
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [rate_limit],
    }
    input_payload = {"messages": [HumanMessage(content=question)], "input": question}
    try:
        final_state = app.invoke(input_payload, config=config)
        return final_state
    except Exception as e:
        logger.error(f"Turn failed: {e}")
        return None


def generate_debug_report(all_results, output_filename):
    """Generates a clean Markdown report."""
    with open(output_filename, "w", encoding="utf-8") as f:
        failures = []
        successes = []

        for r in all_results:
            grade_text = str(r.get("grade", "")).upper()
            if "INCORRECT" in grade_text:
                failures.append(r)
            elif "CORRECT" in grade_text:
                successes.append(r)
            else:
                failures.append(r)

        total = len(all_results)
        correct = len(successes)
        accuracy = (correct / total) * 100 if total > 0 else 0

        f.write(f"# 📊 Eval Report: {correct}/{total} ({accuracy:.1f}%)\n\n")

        if failures:
            f.write("## ❌ FAILURE ANALYSIS\n")
            for r in failures:
                f.write(f"### 🔴 {r['conversation_id']} - Turn {r['turn_id']}\n")
                f.write(f"**User Q:** `{r['question']}`\n")
                f.write(f"**Enhanced Q:** `{r.get('enhanced_query', 'N/A')}`\n")
                f.write(f"**Router Tables:** `{r.get('selected_tables', 'N/A')}`\n")
                f.write(f"**SQL Executed:**\n```sql\n{r['sql_executed']}\n```\n")
                f.write(f"**Prediction:** {r['prediction']}\n")
                f.write(f"**Ground Truth:** {r['ground_truth']}\n")
                f.write(f"**Judge Feedback:** {r.get('grade', 'N/A')}\n")
                f.write("---\n")
        else:
            f.write("## 🎉 PERFECT SCORE! No failures to report.\n")

        f.write("\n## ✅ Success Log\n")
        for r in successes:
            f.write(f"- **{r['conversation_id']} T{r['turn_id']}:** {r['question']}\n")

    print(f"\n📝 Debug report generated: {output_filename}")


def main():
    parser = argparse.ArgumentParser(description="Run conversational evals.")
    parser.add_argument(
        "--file",
        type=str,
        default="data/test_set_conversations.csv",
        help="Path to input CSV file",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Fail script if accuracy is below this %%",
    )
    parser.add_argument(
        "--output_dir", type=str, default="eval_results", help="Folder to save results"
    )
    args = parser.parse_args()

    logger.info("--- Starting Conversational Eval ---")

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = os.path.join(args.output_dir, f"eval_conv_{timestamp}.csv")

    try:
        df = pd.read_csv(args.file)
        if "conversation_id" not in df.columns:
            logger.error("❌ CSV missing 'conversation_id' column.")
            sys.exit(1)
    except FileNotFoundError:
        logger.error(f"CSV file not found: {args.file}")
        sys.exit(1)

    grouped = df.groupby("conversation_id")
    all_results = []

    for conv_id, group in tqdm(grouped, desc="Conversations"):
        thread_id = str(uuid.uuid4())
        group = group.sort_values("turn_id")

        for _, row in group.iterrows():
            question = row["question"]
            ground_truth = row["ground_truth_answer"]

            state = run_conversation_turn(question, thread_id)

            predicted_answer = "Error"
            sql_executed = "N/A"
            selected_tables = "N/A"
            enhanced_query = "N/A"

            if state:
                predicted_answer = state["messages"][-1].content
                sql_executed = extract_last_turn_sql(state["messages"])
                selected_tables = str(state.get("selected_tables", []))
                enhanced_query = state.get("input", "N/A")

            all_results.append(
                {
                    "conversation_id": conv_id,
                    "turn_id": row["turn_id"],
                    "question": question,
                    "enhanced_query": enhanced_query,
                    "ground_truth": ground_truth,
                    "prediction": predicted_answer,
                    "sql_executed": sql_executed,
                    "selected_tables": selected_tables,
                }
            )

    logger.info("Grading results...")

    # FIX: Initialize Rate Limit Handler for the Judge
    # 5 seconds delay ensures we stay under the 15 RPM limit
    judge_rate_limit = RateLimitingCallbackHandler(delay_seconds=5)

    # FIX: Attach the callback to the Judge LLM
    eval_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite", temperature=0, callbacks=[judge_rate_limit]
    )
    eval_chain = QAEvalChain.from_llm(llm=eval_llm)

    examples = [
        {"query": r["question"], "answer": r["ground_truth"]} for r in all_results
    ]
    predictions = [{"result": r["prediction"]} for r in all_results]
    grades = []

    for i in tqdm(range(len(examples)), desc="Grading"):
        try:
            single_result = eval_chain.evaluate(
                [examples[i]],
                [predictions[i]],
                question_key="query",
                answer_key="answer",
                prediction_key="result",
            )
            grades.extend(single_result)
            # The rate limiter inside the LLM handles the sleep now,
            # but we can keep a tiny buffer if needed, or remove this explicit sleep.
        except Exception as e:
            logger.error(f"Grading failed for index {i}: {e}")
            grades.append({"results": "ERROR"})
            time.sleep(5)

    correct_count = 0
    for i, grade in enumerate(grades):
        result_text = grade.get("results", "ERROR").strip().upper()
        all_results[i]["grade"] = result_text

        # FIX: Strict checking order
        if "INCORRECT" in result_text:
            pass  # Failure
        elif "CORRECT" in result_text:
            correct_count += 1

    results_df = pd.DataFrame(all_results)
    results_df.to_csv(output_filename, index=False)
    debug_filename = output_filename.replace(".csv", "_DEBUG.md")
    generate_debug_report(all_results, debug_filename)

    accuracy = (correct_count / len(all_results)) * 100
    logger.info(f"✅ Done. Accuracy: {accuracy:.2f}%")
    logger.info(f"Saved to {output_filename}")

    if args.threshold > 0 and accuracy < args.threshold:
        logger.error(
            f"❌ FAILED: Accuracy {accuracy:.2f}% is below threshold {args.threshold}%"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
