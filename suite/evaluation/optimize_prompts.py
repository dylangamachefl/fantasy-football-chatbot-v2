import json
import os
import dspy
from dspy.teleprompt import BootstrapFewShot
from dspy_signatures import SQLGeneratorSignature
from langfuse import Langfuse
from eval_config import (
    GOLDEN_DATASET, 
    SCHEMA_FILE, 
    JUDGE_MODEL, 
    OLLAMA_BASE_URL,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LANGFUSE_HOST
)

# Initialize Langfuse
langfuse = Langfuse(
    public_key=LANGFUSE_PUBLIC_KEY,
    secret_key=LANGFUSE_SECRET_KEY,
    host=LANGFUSE_HOST
)

# --- 1. Setup DSPy ---
def init_dspy():
    print(f"Initializing DSPy with Ollama model={JUDGE_MODEL}")
    # Using Ollama as the LM for optimization (acting as teacher/optimizer)
    lm = dspy.OllamaLocal(model=JUDGE_MODEL, base_url=OLLAMA_BASE_URL, temperature=0)
    dspy.settings.configure(lm=lm)

# --- 2. Load Data ---
def load_dataset():
    if not os.path.exists(GOLDEN_DATASET):
        raise FileNotFoundError(f"Golden dataset not found at {GOLDEN_DATASET}")

    with open(GOLDEN_DATASET, 'r') as f:
        raw_data = json.load(f)

    # Load Schema
    schema_str = load_schema_string()

    examples = []
    for item in raw_data:
        # Input: question, schema
        # Output: sql_query
        ex = dspy.Example(
            question=item['question'],
            db_schema=schema_str,
            examples="", # Placeholder for examples during training
            previous_sql="",
            error_message="",
            reasoning=item.get('reasoning', ""),
            sql_query=item['sql']
        ).with_inputs('question', 'db_schema', 'examples', 'previous_sql', 'error_message')
        examples.append(ex)

    # Load Logs from 'logs/' directory (Feedback Integration)
    logs_dir = "logs"
    if os.path.exists(logs_dir):
        print(f"Searching for logs in {logs_dir}...")
        for filename in os.listdir(logs_dir):
            if filename.endswith(".json"):
                with open(os.path.join(logs_dir, filename), 'r') as f:
                    try:
                        log_data = json.load(f)
                        # The logs exported by Logger.ts successes are a list of objects
                        # with 'question' and 'sql' fields.
                        items = []
                        if isinstance(log_data, list):
                            items = log_data
                        elif isinstance(log_data, dict) and 'successes' in log_data:
                            items = log_data['successes']
                        
                        for item in items:
                            if 'question' in item and 'sql' in item:
                                ex = dspy.Example(
                                    question=item['question'],
                                    db_schema=schema_str,
                                    examples="",
                                    previous_sql="",
                                    error_message="",
                                    reasoning=item.get('reasoning', ""),
                                    sql_query=item['sql']
                                ).with_inputs('question', 'db_schema', 'examples', 'previous_sql', 'error_message')
                                examples.append(ex)
                                print(f"Added feedback example: {item['question']}")
                    except Exception as e:
                        print(f"Error reading log file {filename}: {e}")

    return examples

def load_schema_string():
    if not os.path.exists(SCHEMA_FILE):
        raise FileNotFoundError(f"Schema file not found at {SCHEMA_FILE}")

    with open(SCHEMA_FILE, 'r') as f:
        schema_data = json.load(f)

    tables = schema_data.get('tables', [])
    filtered_schema_parts = ["DATABASE SCHEMA:\n"]
    for t in tables:
        filtered_schema_parts.append(f"Table: {t['table_name']}\nColumns: {json.dumps(t['columns'])}\n")
    
    return '\n'.join(filtered_schema_parts)

# --- 3. Define Metric ---
def validate_sql(example, pred, trace=None):
    gold_sql = " ".join(example.sql_query.lower().split())
    pred_sql = " ".join(pred.sql_query.lower().split())
    return gold_sql == pred_sql

# --- 4. Main Optimization ---
def optimize():
    init_dspy()
    
    # Load Golden Dataset (Core)
    trainset = load_dataset()
    
    # Load Silver Dataset (Feedback Loop - Phase 5.3)
    silver_count = 0
    logs_dir = "logs"
    if os.path.exists(logs_dir):
        print(f"Scanning {logs_dir} for silver examples...")
        for filename in os.listdir(logs_dir):
            if "successes-golden" in filename and filename.endswith(".json"):
                with open(os.path.join(logs_dir, filename), 'r') as f:
                    try:
                        silver_data = json.load(f)
                        for item in silver_data:
                            if 'question' in item and 'sql' in item:
                                ex = dspy.Example(
                                    question=item['question'],
                                    db_schema=load_schema_string(), # Context needed for training
                                    examples="",
                                    previous_sql="",
                                    error_message="",
                                    reasoning=item.get('reasoning', ""),
                                    sql_query=item['sql']
                                ).with_inputs('question', 'db_schema', 'examples', 'previous_sql', 'error_message')
                                trainset.append(ex)
                                silver_count += 1
                    except Exception as e:
                        print(f"Error loading silver file {filename}: {e}")
    
    print(f"Total trainset size: {len(trainset)} ({silver_count} silver examples added).")

    # Define the module as a simple Predict or ChainOfThought
    module = dspy.ChainOfThought(SQLGeneratorSignature)

    # Compile
    teleprompter = BootstrapFewShot(metric=validate_sql, max_bootstrapped_demos=4, max_labeled_demos=4)

    print("Starting optimization...")
    compiled_program = teleprompter.compile(module, trainset=trainset)

    # Save compiled program
    output_path = "suite/evaluation/compiled_sql_generator.json"
    compiled_program.save(output_path)
    print(f"Optimization complete. Saved to {output_path}")

if __name__ == "__main__":
    optimize()
