import json
import os
from eval_config import GOLDEN_DATASET

def extract_failures():
    """
    Read exported log files from the 'logs/' directory.
    Filter for failures (negative feedback) and extract user queries.
    """
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        print(f"No logs directory found at {logs_dir}. Please export logs from the app first.")
        # Create it just in case
        os.makedirs(logs_dir, exist_ok=True)
        return []

    print(f"Scanning {logs_dir} for failure logs...")
    
    unique_queries = set()
    
    for filename in os.listdir(logs_dir):
        # 1. Check failures-for-teacher files
        if "failures-for-teacher" in filename and filename.endswith(".json"):
            path = os.path.join(logs_dir, filename)
            try:
                with open(path, 'r') as f:
                    failures = json.load(f)
                    for item in failures:
                        if 'question' in item:
                            unique_queries.add(item['question'])
            except Exception as e:
                print(f"Error reading {filename}: {e}")
        
        # 2. Also check all-feedback files
        elif "all-feedback" in filename and filename.endswith(".json"):
            path = os.path.join(logs_dir, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    if 'failures' in data:
                        for f_item in data['failures']:
                            if 'question' in f_item:
                                unique_queries.add(f_item['question'])
            except Exception as e:
                print(f"Error reading {filename}: {e}")

    unique_queries_list = list(unique_queries)
    print(f"Extracted {len(unique_queries_list)} unique failure queries.")
    
    # Save to a temporary file for the Teacher
    output_path = "suite/evaluation/extracted_failures.json"
    with open(output_path, 'w') as f:
        json.dump(unique_queries_list, f, indent=2)
        
    print(f"Failures saved to {output_path}")
    return unique_queries_list

if __name__ == "__main__":
    extract_failures()
