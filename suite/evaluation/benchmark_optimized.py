import json
import dspy
from suite.evaluation.dspy_signatures import IntentRouter, TableRouterSignature, SQLGeneratorSignature
from suite.evaluation.eval_config import (
    SCHEMA_FILE, 
    JUDGE_MODEL, 
    OLLAMA_BASE_URL
)

# Use test dataset for unbiased evaluation
TEST_DATASET = "shared/test.json"

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

def main():
    # 1. Setup DSPy
    lm = dspy.LM(f'ollama_chat/{JUDGE_MODEL}', api_base=OLLAMA_BASE_URL)
    dspy.settings.configure(lm=lm)

    # 2. Load Compiled Artifact
    compiled_path = "suite/evaluation/compiled_fantasy_agent.json"
    with open(compiled_path, 'r') as f:
        artifacts = json.load(f)

    # 3. Initialize Modules
    intent_router = dspy.Predict(IntentRouter)
    intent_router.load_state(artifacts['intent_router'])

    table_router = dspy.Predict(TableRouterSignature)
    table_router.load_state(artifacts['table_router'])

    sql_generator = dspy.ChainOfThought(SQLGeneratorSignature)
    sql_generator.load_state(artifacts['sql_generator'])

    # 4. Load Dataset
    with open(TEST_DATASET, 'r') as f:
        golden_data = json.load(f)
    
    print(f"Loaded {len(golden_data)} test examples from {TEST_DATASET}")

    schema_str = load_schema_string()
    table_descriptions = load_table_descriptions()

    results = []
    print(f"Benchmarking {len(golden_data)} examples...")

    # Evaluate on full test set (no limiting)
    for item in golden_data:
        question = item['question']
        print(f"\nProcessing: {question}")

        # Intent
        intent_pred = intent_router(question=question)
        print(f"Pred Intent: {intent_pred.intent}")

        # Table Routing (if SQL)
        if intent_pred.intent.lower() == 'sql_query':
            table_pred = table_router(question=question, table_descriptions=table_descriptions)
            print(f"Pred Tables: {table_pred.selected_tables}")

            # SQL Generation
            sql_pred = sql_generator(
                question=question, 
                db_schema=schema_str,
                examples="",
                previous_sql="",
                error_message=""
            )
            print(f"Pred SQL: {sql_pred.sql_query}")

            results.append({
                "question": question,
                "gold_intent": item.get('intent'),
                "pred_intent": intent_pred.intent,
                "gold_sql": item.get('sql'),
                "pred_sql": sql_pred.sql_query,
                "gold_tables": item.get('selected_tables'),
                "pred_tables": table_pred.selected_tables
            })
        else:
            results.append({
                "question": question,
                "gold_intent": item.get('intent'),
                "pred_intent": intent_pred.intent
            })

    # Summary
    correct_intents = sum(1 for r in results if str(r.get('gold_intent')).lower() == str(r.get('pred_intent')).lower())
    print(f"\nIntent Accuracy: {correct_intents}/{len(results)}")

    with open("suite/evaluation/benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
