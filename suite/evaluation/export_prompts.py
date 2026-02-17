import json
import os
import re
import shutil
from eval_config import PROMPTS_TS_PATH

COMPILED_FILE = "suite/evaluation/compiled_fantasy_agent.json"

def format_demos(demos, keys):
    formatted = ""
    for i, demo in enumerate(demos):
        formatted += f"Example {i+1}:\n"
        for key in keys:
            if key in demo:
                formatted += f"{key.replace('_', ' ').capitalize()}: {demo[key]}\n"
        formatted += "\n"
    return formatted.strip()

def export_prompts():
    if not os.path.exists(COMPILED_FILE):
        print(f"Compiled file {COMPILED_FILE} not found. Run optimization first.")
        return

    with open(COMPILED_FILE, 'r') as f:
        compiled_data = json.load(f)

    # Export to JSON instead of TypeScript template literals
    # This eliminates template injection vulnerabilities entirely
    output_path = "apps/chat-app/src/lib/optimized_prompts.json"
    
    with open(output_path, 'w') as f:
        json.dump(compiled_data, f, indent=2)
    
    print(f"\n✓ Exported optimized prompts to {output_path}")
    print("Import in TypeScript with: import optimizedPrompts from './optimized_prompts.json'")
    print("\nNo template injection risk - using JSON import instead of template literals.")

    # 1. Extract from Intent Router
    intent_data = compiled_data.get('intent_router', {})
    intent_demos = intent_data.get('demos', [])
    intent_examples_str = format_demos(intent_demos, ['question', 'intent'])
    intent_instruction = intent_data.get('signature', {}).get('instructions', "")

    # 2. Extract from Table Router
    table_data = compiled_data.get('table_router', {})
    table_demos = table_data.get('demos', [])
    table_examples_str = format_demos(table_demos, ['question', 'selected_tables'])
    table_instruction = table_data.get('signature', {}).get('instructions', "")

    # 3. Extract from SQL Generator
    sql_data = compiled_data.get('sql_generator', {})
    # Check both 'demos' and nested 'prog.predict'
    sql_demos = sql_data.get('demos', [])
    if not sql_demos and 'predictor' in sql_data:
        sql_demos = sql_data['predictor'].get('demos', [])
    
    sql_examples_str = format_demos(sql_demos, ['question', 'sql_query', 'reasoning'])
    sql_instruction = sql_data.get('signature', {}).get('instructions', "")
    if not sql_instruction and 'predictor' in sql_data:
        sql_instruction = sql_data['predictor'].get('signature', {}).get('instructions', "")

    # Update the TypeScript file
    if not os.path.exists(PROMPTS_TS_PATH):
        print(f"Target file {PROMPTS_TS_PATH} not found.")
        return

    with open(PROMPTS_TS_PATH, 'r') as f:
        content = f.read()

    def replace_or_inject(content, marker_name, value):
        marker = f"// --- OPTIMIZED {marker_name} (DO NOT EDIT MANUALLY) ---"
        replacement = f"{marker}\nexport const OPTIMIZED_{marker_name} = `{value.strip()}`;\n{marker}"
        if marker in content:
            pattern = re.escape(marker) + r".*?" + re.escape(marker)
            return re.sub(pattern, replacement, content, flags=re.DOTALL)
        else:
            # Prepend to where PROMPTS is exported
            return content.replace("export const PROMPTS =", f"{replacement}\n\nexport const PROMPTS =")

    content = replace_or_inject(content, "INTENT_EXAMPLES", intent_examples_str)
    content = replace_or_inject(content, "INTENT_INSTRUCTION", intent_instruction)
    content = replace_or_inject(content, "TABLE_EXAMPLES", table_examples_str)
    content = replace_or_inject(content, "TABLE_INSTRUCTION", table_instruction)
    content = replace_or_inject(content, "SQL_EXAMPLES", sql_examples_str)
    content = replace_or_inject(content, "SQL_INSTRUCTION", sql_instruction)

    with open(PROMPTS_TS_PATH, 'w') as f:
        f.write(content)

    print(f"Successfully exported to {PROMPTS_TS_PATH}")

    # 3. Deploy Artifact to Public Assets
    ARTIFACT_DEST = "apps/chat-app/public/assets/artifacts/compiled_fantasy_agent.json"
    os.makedirs(os.path.dirname(ARTIFACT_DEST), exist_ok=True)
    shutil.copy2(COMPILED_FILE, ARTIFACT_DEST)
    print(f"Artifact deployed to {ARTIFACT_DEST}")

if __name__ == "__main__":
    export_prompts()
