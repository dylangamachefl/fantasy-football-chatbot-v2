import json
import os
import argparse
from tqdm import tqdm
from langchain_ollama import ChatOllama
import eval_config

def judge():
    parser = argparse.ArgumentParser(description="Grade captured frontend results.")
    parser.add_argument(
        "--input",
        type=str,
        default="eval_results/raw_frontend_results.json",
        help="Path to raw results JSON",
    )
    parser.add_argument('--predictions', '-p', required=True, help='Path to predictions JSON file (output of benchmark_optimized.py)')
    parser.add_argument('--test-set', '-t', default='shared/test.json', help='Path to test dataset (ground truth)')
    parser.add_argument('--output', '-o', default='suite/evaluation/judge_output.json', help='Path to output file for judge results')
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

    grades = []
    print("Starting grading loop...")
    for i in tqdm(range(len(data)), desc="Grading"):
        try:
            question = data[i]["question"]
            expected = data[i]["ground_truth_answer"]
            actual = data[i]["actual_answer"]
            
            # Direct LLM call with structured output
            prompt = f"""Grade the following answer to a question.

Question: {question}
Expected Answer: {expected}
Actual Answer: {actual}

Determine if the actual answer is correct, incorrect, or partially correct.
Respond in JSON format: {{"grade": "correct" | "incorrect" | "partial", "explanation": "..."}}""" 
            
            response = eval_llm.invoke(prompt)
            response_text = response.content.strip()
            
            # Try to parse as JSON
            try:
                grade_obj = json.loads(response_text)
                grade = grade_obj.get("grade", "ERROR").upper()
            except json.JSONDecodeError:
                # Fallback to text parsing
                grade = response_text.upper()
            
            grades.append({"results": grade, "explanation": grade_obj.get("explanation", "") if isinstance(grade, dict) else ""})
        except Exception as e:
            print(f"Grading failed for item {i}: {e}")
            grades.append({"results": "ERROR", "explanation": str(e)})

    # Aggregate results with strict grade parsing
    correct_count = 0
    partial_count = 0
    incorrect_count = 0
    
    for i, grade_result in enumerate(grades):
        # Parse grade as exact lowercase enum value
        grade = grade_result.get("results", "").strip().lower()
        data[i]["grade"] = grade
        
        # Exact matching on enum values
        if grade == "correct":
            correct_count += 1
        elif grade == "partial":
            partial_count += 1
        elif grade == "incorrect":
            incorrect_count += 1
        else:
            # Unexpected value - log warning and count as incorrect
            print(f"Warning: Unexpected grade value '{grade_result.get('results')}' for item {i}, counting as incorrect")
            incorrect_count += 1
            data[i]["grade"] = "incorrect"

    accuracy = (correct_count / len(data)) * 100 if data else 0
    
    final_output = {
        "summary": {
            "total": len(data),
            "correct": correct_count,
            "partial": partial_count,
            "incorrect": incorrect_count,
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
