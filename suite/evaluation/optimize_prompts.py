import json
import os
import dspy
from dspy.teleprompt import BootstrapFewShot
from dspy_signatures import IntentRouter, TableRouterSignature, SQLGeneratorSignature, SQLValidatorSignature
from eval_config import (
    SCHEMA_FILE, 
    JUDGE_MODEL, 
    OLLAMA_BASE_URL
)
import sqlglot
from datetime import datetime

# Use training data only - fixes train/test leakage
TRAIN_DATASET = "shared/train.json"

# --- 1. Setup DSPy ---
def init_dspy():
    print(f"Initializing DSPy with Ollama model={JUDGE_MODEL}")
    lm = dspy.LM(f'ollama_chat/{JUDGE_MODEL}', api_base=OLLAMA_BASE_URL)
    dspy.settings.configure(lm=lm)

# --- 2. Load Data ---
def load_dataset():
    if not os.path.exists(TRAIN_DATASET):
        raise FileNotFoundError(f"Training dataset not found at {TRAIN_DATASET}. Run split_dataset.py first.")

    with open(TRAIN_DATASET, 'r') as f:
        raw_data = json.load(f)
    
    print(f"Loaded {len(raw_data)} training examples from {TRAIN_DATASET}")

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

    # Note: Silver data integration removed to keep training pipeline clean
    # User feedback logs should be separately validated before adding to golden dataset

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
    """Improved intent metric with canonicalization and alias mapping."""
    # Canonicalize both intents
    gold = example.intent.lower().strip()
    predicted = pred.intent.lower().strip()
    
    # Map known aliases
    alias_map = {
        'sql': 'sql_query',
        'query': 'sql_query',
        'conversation': 'conversational',
        'chat': 'conversational',
        'rules': 'league_rules',
        'history': 'league_history'
    }
    
    gold = alias_map.get(gold, gold)
    predicted = alias_map.get(predicted, predicted)
    
    return gold == predicted

def table_metric(example, pred, trace=None):
    """Improved table metric using F1 score instead of exact set match."""
    gold_tables = set(example.selected_tables)
    pred_tables = set(pred.selected_tables) if isinstance(pred.selected_tables, list) else set()
    
    if len(gold_tables) == 0 and len(pred_tables) == 0:
        return 1.0
    
    if len(gold_tables) == 0 or len(pred_tables) == 0:
        return 0.0
    
    # F1 score: 2 * |gold ∩ pred| / (|gold| + |pred|)
    intersection = len(gold_tables & pred_tables)
    f1_score = (2 * intersection) / (len(gold_tables) + len(pred_tables))
    
    return f1_score

def validate_sql(example, pred, trace=None):
    """Improved SQL validation using AST comparison via sqlglot."""
    try:
        # Parse both queries into ASTs
        gold_ast = sqlglot.parse_one(example.sql_query, read='sqlite')
        pred_ast = sqlglot.parse_one(pred.sql_query, read='sqlite')
        
        # Compare normalized SQL strings from ASTs
        gold_normalized = gold_ast.sql(dialect='sqlite', normalize=True)
        pred_normalized = pred_ast.sql(dialect='sqlite', normalize=True)
        
        return gold_normalized == pred_normalized
    except Exception as e:
        # Fallback to whitespace-normalized comparison if parsing fails
        print(f"SQL parsing failed, using fallback comparison: {e}")
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
    def validate_intent(example, pred, trace=None):
        return example.intent.lower() == pred.intent.lower()

    router_module = dspy.Predict(IntentRouter)
    teleprompter = BootstrapFewShot(metric=validate_intent, max_bootstrapped_demos=3)
    intent_prog = teleprompter.compile(router_module, trainset=intent_set)
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

    # 4. Optimize SQL Validator (optional but helps catch common errors)
    print("\n4. Optimizing SQL Validator...")
    # Create validation examples from SQL set
    validator_set = []
    for ex in sql_set:
        # Create a validation example with the correct SQL
        validator_set.append(dspy.Example(
            question=ex.question,
            sql_query=ex.sql_query,
            db_schema=ex.db_schema,
            is_valid=True,
            issues="",
            corrected_sql_query=ex.sql_query
        ).with_inputs('question', 'sql_query', 'db_schema'))
    
    validator_tp = BootstrapFewShot(metric=lambda ex, pred, trace: pred.is_valid == ex.is_valid, max_bootstrapped_demos=3)
    validator_prog = validator_tp.compile(dspy.ChainOfThought(SQLValidatorSignature), trainset=validator_set[:10])  # Limit for speed
    compiled_artifacts['sql_validator'] = validator_prog.dump_state()
    
    # Save Unified Artifact with metadata
    output_path = "suite/evaluation/compiled_fantasy_agent.json"
    final_output = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "train_size": len(intent_set),
            "max_demos_intent": 3,
            "max_demos_table": 3,
            "max_demos_sql": 4,
            "model": JUDGE_MODEL,
            "seed": 42
        },
        "artifacts": compiled_artifacts
    }
    
    with open(output_path, 'w') as f:
        json.dump(final_output, f, indent=2)
    
    print(f"Optimization complete. Unified artifact saved to {output_path}")
    print(f"Training set size: {len(intent_set)} intent, {len(table_set)} table, {len(sql_set)} SQL examples")

if __name__ == "__main__":
    optimize()
