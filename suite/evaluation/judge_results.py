import json
import os
import argparse
from tqdm import tqdm
from langchain_ollama import ChatOllama
from langchain_classic.evaluation.qa import QAEvalChain
import eval_config

def judge():
    parser = argparse.ArgumentParser(description="Grade captured frontend results.")
    parser.add_argument(
        "--input",
        type=str,
        default="eval_results/raw_frontend_results.json",
        help="Path to raw results JSON",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="eval_results/final_judged_results.json",
        help="Path to save judged results",
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Input file {args.input} not found.")
        return

    with open(args.input, 'r') as f:
        data = json.load(f)

    print(f"Grading {len(data)} results with Ollama ({eval_config.JUDGE_MODEL})...")
    
    eval_llm = ChatOllama(
        model=eval_config.JUDGE_MODEL,
        base_url=eval_config.OLLAMA_BASE_URL,
        temperature=eval_config.JUDGE_TEMPERATURE
    )
    eval_chain = QAEvalChain.from_llm(llm=eval_llm)

    examples = [{"query": r["question"], "answer": r["ground_truth_answer"]} for r in data]
    predictions = [{"result": r["actual_answer"]} for r in data]
    
    grades = []
    print("Starting grading loop...")
    for i in tqdm(range(len(examples)), desc="Grading"):
        try:
             res = eval_chain.evaluate(
                 [examples[i]], 
                 [predictions[i]], 
                 question_key="query", 
                 answer_key="answer", 
                 prediction_key="result"
             )
             grades.extend(res)
        except Exception as e:
             print(f"Grading failed for item {i}: {e}")
             grades.append({"results": "ERROR"})

    # Aggregate results
    correct_count = 0
    for i, grade in enumerate(grades):
        result_text = grade.get("results", "ERROR").strip().upper()
        data[i]["grade"] = result_text
        if "CORRECT" in result_text and "INCORRECT" not in result_text:
            correct_count += 1

    accuracy = (correct_count / len(data)) * 100 if data else 0
    
    final_output = {
        "summary": {
            "total": len(data),
            "correct": correct_count,
            "accuracy": accuracy,
            "model": eval_config.JUDGE_MODEL
        },
        "results": data
    }

    with open(args.output, 'w') as f:
        json.dump(final_output, f, indent=2)

    print(f"✅ Grading complete. Accuracy: {accuracy:.2f}%")
    print(f"Final results saved to {args.output}")

if __name__ == "__main__":
    judge()
