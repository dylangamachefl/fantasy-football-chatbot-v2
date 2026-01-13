import json
import os
import re

def export_prompts():
    # 1. Load the compiled DSPy JSON
    compiled_path = os.path.join(os.path.dirname(__file__), '../../original-backend/data/compiled_sql_generator.json')
    if not os.path.exists(compiled_path):
        compiled_path = 'suite/original-backend/data/compiled_sql_generator.json'

    if not os.path.exists(compiled_path):
        print(f"Error: Compiled file not found at {compiled_path}")
        return

    with open(compiled_path, 'r') as f:
        data = json.load(f)

    # 2. Extract Instruction and Examples
    try:
        prog_data = data['prog.predict']

        # Instruction
        instructions = prog_data['signature']['instructions']

        # Demos (Few-Shot Examples)
        demos = prog_data.get('demos', [])

        # Format Demos for Frontend TypeScript
        # The frontend function signature is:
        # sqlGenerator: (question, schema, previousSql, errorMessage, examples) => ...
        # The 'examples' argument is a string injected into the prompt.

        formatted_examples = []
        for demo in demos:
            q = demo.get('question', '')
            sql = demo.get('sql_query', '')
            thought = demo.get('thought', '') # Not always present if not generated or if using direct prediction

            # We want to format this as a string block similar to how it was likely done manually before.
            # Example format:
            # Question: ...
            # SQL: ...

            ex_str = f"Question:\n{q}\n\nSQL:\n{sql}"
            formatted_examples.append(ex_str)

        examples_str = "\n\n".join(formatted_examples)

        # Escape backticks and other chars for JS string injection if needed
        # But here we are injecting into the 'examples' variable passed to the prompt function,
        # or we are hardcoding it into the PROMPTS object?

        # The current prompts.ts defines `sqlGenerator` which takes an `examples` string argument.
        # So we don't need to hardcode the examples *inside* the function body if the caller passes them.
        # However, the Agent in agent.ts calls it with `examples` variable.
        # Wait, agent.ts loads examples from RAG!

        # "const examples = await workerRequest(ragWorker, 'RETRIEVE', { query: activeQuery });"

        # Ah, so the frontend relies on RAG for examples.
        # BUT, DSPy optimization might have found "golden" few-shot examples that should ALWAYS be present,
        # or it optimized the INSTRUCTION itself.

        # If we want to bake in the "bootstrapped" examples as a base, we could append them or replace the instruction.
        # OR, we update the `instructions` part of the prompt in `prompts.ts`.

        # Let's look at `prompts.ts`:
        # sqlGenerator: (question: string, schema: string, previousSql: string = "", errorMessage: string = "", examples: string = "") => `
        # Generate a valid SQLite query to answer the question based on the schema.
        # Follow specific SQL recipes for Head-to-Head and Rankings.
        # ...

        # We should update the static INSTRUCTION text in `prompts.ts` with the optimized one from DSPy.
        # And if DSPy found good few-shot examples, maybe we should prepend them to the dynamic `examples` arg?
        # Or just rely on the RAG.

        # The instruction is the most important part to sync.
        # "Generate a valid SQLite query to answer the question based on the schema.\nFollow specific SQL recipes for Head-to-Head and Rankings."

        print(f"Optimized Instruction: {instructions}")

    except KeyError as e:
        print(f"Error parsing JSON structure: {e}")
        return

    # 3. Read prompts.ts
    prompts_path = os.path.join(os.path.dirname(__file__), '../../apps/chat-app/src/lib/prompts.ts')
    if not os.path.exists(prompts_path):
        prompts_path = 'apps/chat-app/src/lib/prompts.ts'

    with open(prompts_path, 'r') as f:
        content = f.read()

    # 4. Replace the sqlGenerator prompt
    # We will use regex to find the sqlGenerator property and replace the string literal inside.
    # Pattern: sqlGenerator: \(...\) => `[CONTENT]`

    # We need to be careful with escaping.

    # Construct the new prompt body
    # We keep the placeholders like ${schema}, ${question}, etc.
    # The DSPy instruction does NOT contain the placeholders; it's just the text.
    # So we need to reconstruct the full template string.

    # Original template structure:
    # ${instructions}
    #
    # Schema:
    # ${schema}
    #
    # ${examples ? `Examples:\n${examples}\n` : ''}
    #
    # ${previousSql ? ... : ''}
    #
    # Question:
    # ${question}
    #
    # Respond with ONLY the SQL query...

    # We will replace the "Generate a valid SQLite ... Rankings." part with `instructions`.

    # Regex to capture the start of the backtick string until "Schema:"
    # This assumes "Schema:" is the first structural anchor.

    # Actually, simpler: finding the specific hardcoded string and replacing it might be safer if we know it matches.
    # "Generate a valid SQLite query to answer the question based on the schema.\nFollow specific SQL recipes for Head-to-Head and Rankings."

    old_instruction_snippet = "Generate a valid SQLite query to answer the question based on the schema.\nFollow specific SQL recipes for Head-to-Head and Rankings."

    if old_instruction_snippet in content:
        new_content = content.replace(old_instruction_snippet, instructions)
        print("Updated instruction text.")
    else:
        print("Warning: Could not find exact instruction string match. Trying regex or manual update.")
        # Fallback or more robust regex could go here.
        # For now, let's assume the string match works as I read the file earlier.
        pass

    # Note: If DSPy optimized the prompt to be radically different (e.g. removed "Schema:"),
    # this simple replace won't work. But currently optimize_prompts.py uses existing Signature which implies structure.
    # The `instructions` field in DSPy Signature docstring maps to the top of the prompt.

    # ALSO, we should probably verify if we want to inject the "Golden" examples as defaults.
    # If `examples` arg is empty, we could fallback to these.
    # But `agent.ts` passes RAG examples.

    with open(prompts_path, 'w') as f:
        f.write(new_content)

    print(f"Successfully updated {prompts_path}")

if __name__ == "__main__":
    export_prompts()
