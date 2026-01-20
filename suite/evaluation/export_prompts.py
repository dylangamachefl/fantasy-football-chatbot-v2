import json
import os
import re
import shutil
from eval_config import PROMPTS_TS_PATH

COMPILED_FILE = "suite/evaluation/compiled_sql_generator.json"

def export_prompts():
    if not os.path.exists(COMPILED_FILE):
        print(f"Compiled file {COMPILED_FILE} not found. Run optimization first.")
        return

    with open(COMPILED_FILE, 'r') as f:
        data = json.load(f)

    # Extract demos (few-shot examples)
    # The structure depends on how it was saved. 
    # DSPy 2.5+ usually has it in a predictable nested dict if saved via .save()
    
    demos = []
    # Try different common keys
    if 'predictor' in data and 'demos' in data['predictor']:
        demos = data['predictor']['demos']
    elif 'demos' in data:
        demos = data['demos']
    elif 'prog.predict' in data and 'demos' in data['prog.predict']:
        demos = data['prog.predict']['demos']
    
    print(f"Found {len(demos)} demos.")

    # Format demos as a string for injection
    examples_str = ""
    for i, demo in enumerate(demos):
        if 'question' in demo and 'sql_query' in demo:
            examples_str += f"Example {i+1}:\n"
            examples_str += f"Question: {demo['question']}\n"
            examples_str += f"SQL: {demo['sql_query']}\n\n"

    # Also extract optimized instruction if available
    instruction = ""
    if 'predictor' in data and 'signature' in data['predictor']:
        instruction = data['predictor']['signature'].get('instructions', "")
    elif 'prog.predict' in data and 'signature' in data['prog.predict']:
        instruction = data['prog.predict']['signature'].get('instructions', "")

    # Update the TypeScript file
    if not os.path.exists(PROMPTS_TS_PATH):
        print(f"Target file {PROMPTS_TS_PATH} not found.")
        return

    with open(PROMPTS_TS_PATH, 'r') as f:
        content = f.read()

    # 1. Inject/Replace OPTIMIZED_SQL_EXAMPLES
    marker_ex = "// --- OPTIMIZED EXAMPLES (DO NOT EDIT MANUALLY) ---"
    replacement_ex = f"{marker_ex}\nexport const OPTIMIZED_SQL_EXAMPLES = `{examples_str.strip()}`;\n{marker_ex}"

    if marker_ex in content:
        pattern = re.escape(marker_ex) + r".*?" + re.escape(marker_ex)
        content = re.sub(pattern, replacement_ex, content, flags=re.DOTALL)
    else:
        # Prepend to where PROMPTS is exported
        content = content.replace("export const PROMPTS =", f"{replacement_ex}\n\nexport const PROMPTS =")

    # 2. Inject/Replace OPTIMIZED_SQL_INSTRUCTION (Optional but good)
    if instruction:
        marker_inst = "// --- OPTIMIZED INSTRUCTION (DO NOT EDIT MANUALLY) ---"
        replacement_inst = f"{marker_inst}\nexport const OPTIMIZED_SQL_INSTRUCTION = `{instruction.strip()}`;\n{marker_inst}"
        
        if marker_inst in content:
            pattern = re.escape(marker_inst) + r".*?" + re.escape(marker_inst)
            content = re.sub(pattern, replacement_inst, content, flags=re.DOTALL)
        else:
            content = content.replace("export const PROMPTS =", f"{replacement_inst}\n\nexport const PROMPTS =")

    with open(PROMPTS_TS_PATH, 'w') as f:
        f.write(content)

    print(f"Successfully exported to {PROMPTS_TS_PATH}")

    # 3. Deploy Artifact to Public Assets
    ARTIFACT_DEST = "apps/chat-app/public/assets/artifacts/compiled_sql_generator.json"
    os.makedirs(os.path.dirname(ARTIFACT_DEST), exist_ok=True)
    shutil.copy2(COMPILED_FILE, ARTIFACT_DEST)
    print(f"Artifact deployed to {ARTIFACT_DEST}")

if __name__ == "__main__":
    export_prompts()
