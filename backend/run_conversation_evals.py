import os
import pandas as pd
import logging
import uuid
from dotenv import load_dotenv
from langchain_classic.evaluation.qa import QAEvalChain
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from tqdm import tqdm
import time
from datetime import datetime

# --- SETUP ---
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("evals")
logger.setLevel(logging.INFO)
load_dotenv()

# --- IMPORT WORKFLOW (Not 'app') ---
# We need the raw workflow so we can compile it with MemorySaver here
from graph_builder import workflow
from agent_state import AgentState

# --- COMPILE GRAPH WITH MEMORY ---
# This ensures the eval script behaves exactly like the Streamlit App
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
    """
    Extracts ONLY the SQL executed in the most recent turn.
    """
    if not messages:
        return "No messages."

    # Look backwards from the end
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.get("name") == "sql_db_query":
                    return tc["args"].get("query", "No query found in args")

    return "No SQL executed this turn."


def run_conversation_turn(question: str, thread_id: str) -> AgentState:
    """
    Runs a single turn of the conversation using the persistent thread_id.
    """
    # 1. Initialize the Limiter
    rate_limit = RateLimitingCallbackHandler(
        delay_seconds=5
    )  # Set to 5s or 10s if hitting 429s

    # 2. Add it to the Config (THIS WAS MISSING)
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [rate_limit],  # <--- CRITICAL FIX
    }

    input_payload = {"messages": [HumanMessage(content=question)], "input": question}

    try:
        # The callbacks will now propagate to the Enhancer, Router, SQL Agent, and Responder
        final_state = app.invoke(input_payload, config=config)
        return final_state
    except Exception as e:
        logger.error(f"Turn failed: {e}")
        return None


def generate_debug_report(all_results, output_filename):
    """
    Generates a clean Markdown report.

    IMPROVEMENTS:
    1. Correctly detects "INCORRECT" grades.
    2. Includes 'selected_tables' to debug the Router.
    3. Formats SQL for readability.
    """
    with open(output_filename, "w", encoding="utf-8") as f:
        # --- SEPARATE PASS/FAIL ---
        failures = []
        successes = []

        for r in all_results:
            grade_text = str(r.get("grade", "")).upper()
            # CHECK FOR FAILURE FIRST
            if "INCORRECT" in grade_text:
                failures.append(r)
            elif "CORRECT" in grade_text:
                successes.append(r)
            else:
                # ambiguous grades count as failures for debugging purposes
                failures.append(r)

        total = len(all_results)
        correct = len(successes)
        accuracy = (correct / total) * 100 if total > 0 else 0

        f.write(f"# 📊 Eval Report: {correct}/{total} ({accuracy:.1f}%)\n\n")

        # --- FAILURE ANALYSIS (The most important part) ---
        if failures:
            f.write("## ❌ FAILURE ANALYSIS\n")
            f.write(
                "> **INSTRUCTIONS:** Copy this entire section and paste it into the Chatbot to debug logic.\n\n"
            )

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

        # --- SUCCESS SUMMARY ---
        f.write("\n## ✅ Success Log\n")
        for r in successes:
            f.write(f"- **{r['conversation_id']} T{r['turn_id']}:** {r['question']}\n")

    print(f"\n📝 Debug report generated: {output_filename}")


# ... (Keep extract_last_turn_sql and run_conversation_turn as they were) ...


def main():
    # ... (Keep the Setup, Loading, and Inference loops exactly as they were) ...

    # [PASTE AFTER THE INFERENCE LOOP, REPLACING THE GRADING SECTION]

    # 4. LLM JUDGE (Grading)
    logger.info("Grading results (Sequentially)...")

    eval_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
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
            time.sleep(5)  # Rate limit safety
        except Exception as e:
            logger.error(f"Grading failed for index {i}: {e}")
            grades.append({"results": "ERROR"})
            time.sleep(10)

    # 5. SAVE REPORT (WITH FIXED LOGIC)
    correct_count = 0
    for i, grade in enumerate(grades):
        result_text = grade.get("results", "ERROR").strip()
        all_results[i]["grade"] = result_text

        # --- FIX: Check for INCORRECT first ---
        upper_res = result_text.upper()

        if "INCORRECT" in upper_res:
            logger.warning(
                f"❌ Failed {all_results[i]['conversation_id']} (T{all_results[i]['turn_id']})"
            )
        elif "CORRECT" in upper_res:
            correct_count += 1
        else:
            # If unknown (e.g. ERROR), treat as fail
            logger.warning(
                f"⚠️  Unknown Grade {all_results[i]['conversation_id']}: {result_text}"
            )

    results_df = pd.DataFrame(all_results)
    results_df.to_csv(output_filename, index=False)

    # Use the fixed report generator
    debug_filename = output_filename.replace(".csv", "_DEBUG.md")
    generate_debug_report(all_results, debug_filename)

    accuracy = (correct_count / len(all_results)) * 100
    logger.info(f"✅ Done. Accuracy: {accuracy:.2f}%")
    logger.info(f"Saved to {output_filename}")


if __name__ == "__main__":
    main()


def main():
    """Main function to run the conversational evaluation."""
    logger.info("--- Starting Conversational Eval (Explicit IDs) ---")

    output_dir = "eval_results"
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = os.path.join(output_dir, f"eval_conv_{timestamp}.csv")

    # 1. LOAD DATA
    try:
        df = pd.read_csv("data/test_set_conversations.csv")
        # Check for required column
        if "conversation_id" not in df.columns:
            logger.error("❌ CSV missing 'conversation_id' column. Please add it!")
            return
        logger.info(f"Loaded {len(df)} rows.")
    except FileNotFoundError:
        logger.error("CSV file not found.")
        return

    # 2. GROUP BY ID (Much safer now)
    # This works even if your CSV is shuffled!
    grouped = df.groupby("conversation_id")

    all_results = []

    logger.info(f"Evaluating {len(grouped)} conversations...")

    for conv_id, group in tqdm(grouped):
        # Create a fresh memory thread for this specific conversation
        thread_id = str(uuid.uuid4())

        # CRITICAL: Sort by turn_id so the conversation happens in order
        group = group.sort_values("turn_id")

        for _, row in group.iterrows():
            question = row["question"]
            ground_truth = row["ground_truth_answer"]

            # Run the Agent
            state = run_conversation_turn(question, thread_id)

            predicted_answer = "Error"
            sql_executed = "N/A"
            selected_tables = "N/A"
            enhanced_query = "N/A"  # <--- New Variable

            if state:
                predicted_answer = state["messages"][-1].content
                sql_executed = extract_last_turn_sql(state["messages"])
                selected_tables = str(state.get("selected_tables", []))

                # CAPTURE THE ENHANCED INPUT
                # Since node_query_enhancer overwrites state['input'], we can just grab it here.
                enhanced_query = state.get("input", "N/A")

            all_results.append(
                {
                    "conversation_id": conv_id,
                    "turn_id": row["turn_id"],
                    "question": question,
                    "enhanced_query": enhanced_query,  # <--- Add to dict
                    "ground_truth": ground_truth,
                    "prediction": predicted_answer,
                    "sql_executed": sql_executed,
                    "selected_tables": selected_tables,
                }
            )

    # ... inside main() ...

    # 4. LLM JUDGE (Grading) - SEQUENTIAL FIX
    logger.info("Grading results (Sequentially to avoid 429s)...")

    eval_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
    eval_chain = QAEvalChain.from_llm(llm=eval_llm)

    examples = [
        {"query": r["question"], "answer": r["ground_truth"]} for r in all_results
    ]
    predictions = [{"result": r["prediction"]} for r in all_results]

    grades = []

    # We loop manually instead of passing the whole list to .evaluate()
    # This guarantees we never hit the API with more than 1 request at a time.
    for i in tqdm(range(len(examples)), desc="Grading"):
        try:
            # Evaluate ONE pair
            single_result = eval_chain.evaluate(
                [examples[i]],
                [predictions[i]],
                question_key="query",
                answer_key="answer",
                prediction_key="result",
            )

            # Append result
            grades.extend(single_result)

            # STRICT SLEEP: Gemini Free Tier limit is ~15 RPM (1 req / 4 sec).
            # We sleep 5 seconds to be safe.
            time.sleep(5)

        except Exception as e:
            logger.error(f"Grading failed for index {i}: {e}")
            # Fallback grade so lists stay aligned
            grades.append({"results": "ERROR"})
            time.sleep(10)  # Sleep longer on error

    # 5. SAVE REPORT
    correct_count = 0
    for i, grade in enumerate(grades):
        result_text = grade.get("results", "ERROR").strip()
        all_results[i]["grade"] = result_text

        if "CORRECT" in result_text.upper():
            correct_count += 1
        else:
            logger.warning(
                f"❌ Failed {all_results[i]['conversation_id']} (T{all_results[i]['turn_id']})"
            )
            logger.warning(f"   Q: {all_results[i]['question']}")
            logger.warning(f"   Got: {all_results[i]['prediction']}")

    results_df = pd.DataFrame(all_results)
    results_df.to_csv(output_filename, index=False)
    debug_filename = output_filename.replace(".csv", "_DEBUG.md")
    generate_debug_report(all_results, debug_filename)

    accuracy = (correct_count / len(all_results)) * 100
    logger.info(f"✅ Done. Accuracy: {accuracy:.2f}%")
    logger.info(f"Saved to {output_filename}")


if __name__ == "__main__":
    main()
