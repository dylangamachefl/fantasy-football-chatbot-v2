import json
import os
import requests
from eval_config import GOLDEN_DATASET, SCHEMA_FILE, OLLAMA_BASE_URL

# Configuration for the Teacher
TEACHER_MODEL = "qwen3:8b"

def load_schema():
    with open(SCHEMA_FILE, 'r') as f:
        return json.load(f)

def generate_golden_entry(question, schema):
    """
    Use the Teacher model (Ollama) to generate a 'Golden' entry for a query.
    """
    prompt = f"""
    You are an expert SQL Generator and Fantasy Football Analyst.
    Your task is to take a user question and generate a 'Golden' entry for a dataset.
    
    USER QUESTION: "{question}"
    
    DATABASE SCHEMA:
    {json.dumps(schema, indent=2)}
    
    CORE ENTITY MAP:
    - MANAGERS: Tracked for Championships, Career Wins, Final Standings, Draft Value.
    - PLAYERS: Tracked for Points, Passing/Rushing/Receiving Stats, Weekly Performance.
    
    You must output a JSON object with the following fields:
    1. "question": The original user query.
    2. "reasoning": A step-by-step logical chain identifying the correct table and entity relationships.
    3. "sql": The exact SQLite query to answer the question. If no SQL is needed (e.g., lore), use "NONE".
    4. "category": One of [weekly_performance, seasonal_leaders, matchup_history, draft_analytics, standings_titles, manager_career, league_lore].
    5. "intent": One of ['sql_query', 'conversational', 'league_rules', 'league_history'].
    6. "selected_tables": A list of table names from schema.json required for the query.
    7. "answer": A natural language answer template or the direct answer if it's lore.
    
    RESPONSE FORMAT:
    ```json
    {{
      "question": "...",
      "reasoning": "...",
      "sql": "...",
      "category": "...",
      "intent": "...",
      "selected_tables": ["table1", "table2"],
      "answer": "..."
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
        return json.loads(result['response'])
    except Exception as e:
        print(f"Error generating golden entry for '{question}': {e}")
        return None

def main():
    failures_path = "suite/evaluation/extracted_failures.json"
    if not os.path.exists(failures_path):
        print(f"No failures found at {failures_path}. Run extract_failures.py first.")
        return
        
    with open(failures_path, 'r') as f:
        failed_queries = json.load(f)
        
    schema = load_schema()
    
    new_entries = []
    print(f"Processing {len(failed_queries)} failed queries with Teacher ({TEACHER_MODEL})...")
    
    for query in failed_queries:
        print(f"Generating for: {query}")
        entry = generate_golden_entry(query, schema)
        if entry:
            new_entries.append(entry)
            
    if not new_entries:
        print("No new entries generated.")
        return
        
    # Load existing golden dataset
    if os.path.exists(GOLDEN_DATASET):
        with open(GOLDEN_DATASET, 'r') as f:
            golden_data = json.load(f)
    else:
        golden_data = []
        
    # Merge and save
    # To avoid exact duplicates by question
    existing_questions = {item['question'] for item in golden_data}
    added_count = 0
    for entry in new_entries:
        if entry['question'] not in existing_questions:
            golden_data.append(entry)
            added_count += 1
            
    with open(GOLDEN_DATASET, 'w') as f:
        json.dump(golden_data, f, indent=2)
        
    print(f"Added {added_count} new entries to {GOLDEN_DATASET}.")

if __name__ == "__main__":
    main()
