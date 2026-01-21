import json
import os
import dspy
from collections import defaultdict
from dspy_signatures import IntentRouter
from eval_config import GOLDEN_DATASET, JUDGE_MODEL, OLLAMA_BASE_URL

def init_dspy():
    lm = dspy.LM(f'ollama_chat/{JUDGE_MODEL}', api_base=OLLAMA_BASE_URL)
    dspy.settings.configure(lm=lm)

def load_compiled_router():
    artifact_path = "suite/evaluation/compiled_fantasy_agent.json"
    if not os.path.exists(artifact_path):
        return None
    with open(artifact_path, 'r') as f:
        artifacts = json.load(f)
    
    router = dspy.Predict(IntentRouter)
    router.load_state(artifacts['intent_router'])
    return router

def generate_confusion_matrix():
    init_dspy()
    router = load_compiled_router()
    if not router:
        print("Compiled router not found. Run optimization first.")
        return

    with open(GOLDEN_DATASET, 'r') as f:
        data = json.load(f)

    matrix = defaultdict(lambda: defaultdict(int))
    intents = ["sql_query", "conversational", "league_rules", "league_history"]
    
    print(f"Evaluating router on {len(data)} examples...")
    for item in data:
        if 'intent' not in item: continue
        
        actual = item['intent'].lower()
        pred_output = router(question=item['question'])
        pred = pred_output.intent.lower()
        
        # Normalize predicted intent if it's not in our list
        if pred not in intents:
            # Simple heuristic or label as 'other'
            found = False
            for target in intents:
                if target in pred:
                    pred = target
                    found = True
                    break
            if not found: pred = "unknown"

        matrix[actual][pred] += 1

    # Print Matrix
    print("\nCONFUSION MATRIX")
    header = "Actual \\ Pred".ljust(20) + "".join([intent.rjust(15) for intent in intents])
    print(header)
    print("-" * len(header))
    
    for actual in intents:
        row = actual.ljust(20)
        for pred in intents:
            row += str(matrix[actual][pred]).rjust(15)
        print(row)

if __name__ == "__main__":
    generate_confusion_matrix()
