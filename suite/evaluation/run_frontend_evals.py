import os
import sys
import pandas as pd
import logging
import uuid
import argparse
import time
import asyncio
from datetime import datetime
from tqdm import tqdm
from playwright.sync_api import sync_playwright
from langchain_ollama import ChatOllama
from langchain_classic.evaluation.qa import QAEvalChain
import eval_config

# --- SETUP ---
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("frontend-evals")
logger.setLevel(logging.INFO)

def run_frontend_eval():
    parser = argparse.ArgumentParser(description="Run frontend conversational evals.")
    parser.add_argument(
        "--file",
        type=str,
        default="suite/original-backend/data/test_set_conversations.csv",
        help="Path to input CSV file",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:5173",
        help="URL of the frontend app",
    )
    parser.add_argument(
        "--output_dir", type=str, default="eval_results", help="Folder to save results"
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = os.path.join(args.output_dir, f"eval_frontend_{timestamp}.csv")

    try:
        df = pd.read_csv(args.file)
    except FileNotFoundError:
        logger.error(f"CSV file not found: {args.file}")
        sys.exit(1)

    all_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        grouped = df.groupby("conversation_id")
        
        for conv_id, group in tqdm(grouped, desc="Conversations"):
            page = browser.new_page()
            page.goto(args.url)
            
            # Wait for app to be ready (Agent.init sets status to idle and adds "System Ready.")
            # We look for the status indicator to show "Ready"
            page.wait_for_selector('[data-testid="status-indicator"]:has-text("Ready")', timeout=120000)
            
            group = group.sort_values("turn_id")
            
            for _, row in group.iterrows():
                question = row["question"]
                ground_truth = row["ground_truth_answer"]
                
                # Interact with chat input
                chat_input = page.locator('[data-testid="chat-input"]')
                chat_input.fill(question)
                chat_input.press("Enter")
                
                # Wait for thinking process to finish (status returns to idle)
                # We wait for the new assistant message to appear
                # This depends on the exact DOM structure. Using data-testid
                messages = page.locator('[data-testid="message-assistant"]')
                current_count = messages.count()
                
                # Poll for new message
                timeout = 90 # Increased timeout for local LLM
                start_time = time.time()
                while messages.count() <= all_results_count_in_this_page(all_results, conv_id):
                    time.sleep(1)
                    if time.time() - start_time > timeout:
                        break
                
                predicted_answer = messages.last.locator('[data-testid="message-content-assistant"]').inner_text() if messages.count() > 0 else "Timeout/Error"
                
                all_results.append({
                    "conversation_id": conv_id,
                    "turn_id": row["turn_id"],
                    "question": question,
                    "ground_truth": ground_truth,
                    "prediction": predicted_answer,
                })
            
            page.close()
            
        browser.close()

    logger.info(f"Grading results with Ollama ({eval_config.JUDGE_MODEL})...")
    eval_llm = ChatOllama(
        model=eval_config.JUDGE_MODEL,
        base_url=eval_config.OLLAMA_BASE_URL,
        temperature=eval_config.JUDGE_TEMPERATURE
    )
    eval_chain = QAEvalChain.from_llm(llm=eval_llm)

    examples = [{"query": r["question"], "answer": r["ground_truth"]} for r in all_results]
    predictions = [{"result": r["prediction"]} for r in all_results]
    
    grades = []
    for i in tqdm(range(len(examples)), desc="Grading"):
        try:
             res = eval_chain.evaluate([examples[i]], [predictions[i]], question_key="query", answer_key="answer", prediction_key="result")
             grades.extend(res)
        except Exception as e:
             logger.error(f"Grading failed: {e}")
             grades.append({"results": "ERROR"})

    correct_count = 0
    for i, grade in enumerate(grades):
        result_text = grade.get("results", "ERROR").strip().upper()
        all_results[i]["grade"] = result_text
        if "CORRECT" in result_text and "INCORRECT" not in result_text:
            correct_count += 1

    results_df = pd.DataFrame(all_results)
    results_df.to_csv(output_filename, index=False)
    logger.info(f"✅ Done. Accuracy: {(correct_count/len(all_results))*100:.2f}%")
    logger.info(f"Saved to {output_filename}")

def all_results_count_in_this_page(results, conv_id):
    return len([r for r in results if r['conversation_id'] == conv_id])

if __name__ == "__main__":
    run_frontend_eval()
