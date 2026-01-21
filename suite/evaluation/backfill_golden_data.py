import json
import os
import requests
from eval_config import GOLDEN_DATASET, SCHEMA_FILE, OLLAMA_BASE_URL

TEACHER_MODEL = "qwen3:8b"

def load_schema():
    with open(SCHEMA_FILE, 'r') as f:
        return json.load(f)

def enrich_entry(entry, schema):
    """
    Use the Teacher model to add missing 'intent' and 'selected_tables' to an existing entry.
    """
    question = entry['question']
    current_sql = entry.get('sql', 'NONE')
    
    prompt = f"""
    You are an expert SQL Generator and Fantasy Football Analyst.
    Your task is to enrich an existing golden entry with 'intent' and 'selected_tables'.
    
    USER QUESTION: "{question}"
    EXISTING SQL: "{current_sql}"
    
    DATABASE SCHEMA:
    {json.dumps(schema, indent=2)}
    
    Intents:
    - 'sql_query': Complex data needed from database.
    - 'conversational': Simple chit-chat or greeting.
    - 'league_rules': Questions about bylaws, scoring, or settings.
    - 'league_history': Narrative questions about the league's past or lore.

    You must output a JSON object with the following fields:
    1. "intent": One of the categories above.
    2. "selected_tables": A list of table names from the schema required for this question.
    3. "reasoning": A brief explanation of the intent and table selection.
    
    RESPONSE FORMAT:
    ```json
    {{
      "intent": "...",
      "selected_tables": ["table1", "table2"],
      "reasoning": "..."
    }}
    ```
    """
    
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": TEACHER_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            }
        )
        response.raise_for_status()
        result = response.json()
        enrichment = json.loads(result['response'])
        
        # Merge enrichment into entry
        entry['intent'] = enrichment.get('intent', 'sql_query')
        entry['selected_tables'] = enrichment.get('selected_tables', [])
        if 'reasoning' not in entry:
            entry['reasoning'] = enrichment.get('reasoning', "")
        
        return entry
    except Exception as e:
        print(f"Error enriching entry for '{question}': {e}")
        return entry

def main():
    if not os.path.exists(GOLDEN_DATASET):
        print(f"Golden dataset not found at {GOLDEN_DATASET}")
        return
        
    with open(GOLDEN_DATASET, 'r') as f:
        golden_data = json.load(f)
        
    schema = load_schema()
    
    print(f"Enriching {len(golden_data)} entries in {GOLDEN_DATASET}...")
    
    enriched_data = []
    for i, entry in enumerate(golden_data):
        # Only enrich if missing fields
        if 'intent' not in entry or 'selected_tables' not in entry:
            print(f"[{i+1}/{len(golden_data)}] Enriching: {entry['question']}")
            enriched_entry = enrich_entry(entry, schema)
            enriched_data.append(enriched_entry)
        else:
            enriched_data.append(entry)
            
    with open(GOLDEN_DATASET, 'w') as f:
        json.dump(enriched_data, f, indent=2)
        
    print(f"Enrichment complete. Updated {GOLDEN_DATASET}.")

if __name__ == "__main__":
    main()
