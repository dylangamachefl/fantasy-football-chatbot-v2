import json
import os
import dspy
from dspy.teleprompt import BootstrapFewShot
from dspy_signatures import IntentRouter, TableRouterSignature, SQLGeneratorSignature
from eval_config import (
    GOLDEN_DATASET, 
    SCHEMA_FILE, 
    JUDGE_MODEL, 
    OLLAMA_BASE_URL
)

# --- 1. Setup DSPy ---
def init_dspy():
    print(f"Initializing DSPy with Ollama model={JUDGE_MODEL}")
    lm = dspy.LM(f'ollama_chat/{JUDGE_MODEL}', api_base=OLLAMA_BASE_URL)
    dspy.settings.configure(lm=lm)

# --- 2. Load Data ---
def load_dataset():
    if not os.path.exists(GOLDEN_DATASET):
        raise FileNotFoundError(f"Golden dataset not found at {GOLDEN_DATASET}")

    with open(GOLDEN_DATASET, 'r') as f:
        raw_data = json.load(f)

    schema_str = load_schema_string()
    table_descriptions = load_table_descriptions()

    intent_examples = []
    table_examples = []
    sql_examples = []

    for item in raw_data:
        # Intent Router Examples
        if 'intent' in item:
            intent_examples.append(dspy.Example(
                question=item['question'],
                intent=item['intent']
            ).with_inputs('question'))
        
        # Table Router Examples
        if 'selected_tables' in item:
            table_examples.append(dspy.Example(
                question=item['question'],
                table_descriptions=table_descriptions,
                selected_tables=item['selected_tables'],
                is_sql_query=True if item.get('sql') != 'NONE' else False
            ).with_inputs('question', 'table_descriptions'))

        # SQL Generator Examples
        if item.get('sql') and item['sql'] != 'NONE':
            sql_examples.append(dspy.Example(
                question=item['question'],
                db_schema=schema_str,
                examples="",
                previous_sql="",
                error_message="",
                reasoning=item.get('reasoning', ""),
                sql_query=item['sql']
            ).with_inputs('question', 'db_schema', 'examples', 'previous_sql', 'error_message'))

    # Load Logs from 'logs/' directory (Feedback Integration - Silver Data)
    logs_dir = "logs"
    if os.path.exists(logs_dir):
        print(f"Searching for silver examples in {logs_dir}...")
        for filename in os.listdir(logs_dir):
            if "successes-golden" in filename and filename.endswith(".json"):
                with open(os.path.join(logs_dir, filename), 'r') as f:
                    try:
                        silver_data = json.load(f)
                        for item in silver_data:
                            if 'question' in item and 'sql' in item:
                                sql_examples.append(dspy.Example(
                                    question=item['question'],
                                    db_schema=schema_str,
                                    examples="",
                                    previous_sql="",
                                    error_message="",
                                    reasoning=item.get('reasoning', ""),
                                    sql_query=item['sql']
                                ).with_inputs('question', 'db_schema', 'examples', 'previous_sql', 'error_message'))
                    except Exception as e:
                        print(f"Error loading silver file {filename}: {e}")

    return intent_examples, table_examples, sql_examples

def load_schema_string():
    with open(SCHEMA_FILE, 'r') as f:
        schema_data = json.load(f)
    tables = schema_data.get('tables', [])
    parts = ["DATABASE SCHEMA:\n"]
    for t in tables:
        parts.append(f"Table: {t['table_name']}\nColumns: {json.dumps(t['columns'])}\n")
    return '\n'.join(parts)

def load_table_descriptions():
    with open(SCHEMA_FILE, 'r') as f:
        schema_data = json.load(f)
    return '\n'.join([f"{t['table_name']}: {t['description']}" for t in schema_data.get('tables', [])])

# --- 3. Define Metrics ---
def intent_metric(example, pred, trace=None):
    return example.intent.lower() == pred.intent.lower()

def table_metric(example, pred, trace=None):
    gold_tables = set(example.selected_tables)
    pred_tables = set(pred.selected_tables) if isinstance(pred.selected_tables, list) else set()
    return gold_tables == pred_tables

def validate_sql(example, pred, trace=None):
    gold_sql = " ".join(example.sql_query.lower().split())
    pred_sql = " ".join(pred.sql_query.lower().split())
    return gold_sql == pred_sql

# --- 4. Main Optimization ---
def optimize():
    init_dspy()
    intent_set, table_set, sql_set = load_dataset()
    
    compiled_artifacts = {}

    # 1. Optimize Intent Router
    print(f"Optimizing Intent Router ({len(intent_set)} examples)...")
    intent_tp = BootstrapFewShot(metric=intent_metric, max_bootstrapped_demos=3, max_labeled_demos=3)
    intent_prog = intent_tp.compile(dspy.Predict(IntentRouter), trainset=intent_set)
    compiled_artifacts['intent_router'] = intent_prog.dump_state()

    # 2. Optimize Table Router
    print(f"Optimizing Table Router ({len(table_set)} examples)...")
    table_tp = BootstrapFewShot(metric=table_metric, max_bootstrapped_demos=3, max_labeled_demos=3)
    table_prog = table_tp.compile(dspy.Predict(TableRouterSignature), trainset=table_set)
    compiled_artifacts['table_router'] = table_prog.dump_state()

    # 3. Optimize SQL Generator
    print(f"Optimizing SQL Generator ({len(sql_set)} examples)...")
    sql_tp = BootstrapFewShot(metric=validate_sql, max_bootstrapped_demos=4, max_labeled_demos=4)
    sql_prog = sql_tp.compile(dspy.ChainOfThought(SQLGeneratorSignature), trainset=sql_set)
    compiled_artifacts['sql_generator'] = sql_prog.dump_state()

    # Save Unified Artifact
    output_path = "suite/evaluation/compiled_fantasy_agent.json"
    with open(output_path, 'w') as f:
        json.dump(compiled_artifacts, f, indent=2)
    
    print(f"Optimization complete. Unified artifact saved to {output_path}")

if __name__ == "__main__":
    optimize()
