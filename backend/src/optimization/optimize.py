import dspy
import json
import os
import sys
from dspy.teleprompt import BootstrapFewShot, MIPROv2
from dspy.evaluate import Evaluate

# Add src to path to import modules
sys.path.append(os.path.join(os.path.dirname(__file__), '../../src'))

from agent.dspy_modules import SQLGeneratorModule, SQLGeneratorSignature
from agent.dspy_config import init_dspy
from agent.sql_agent import get_detailed_schema_info

def load_dataset(path="backend/data/golden_dataset.json"):
    with open(path, 'r') as f:
        data = json.load(f)

    # Transform to DSPy Examples
    examples = []
    for item in data:
        # We need schema for the input. For optimization, we can use a static schema
        # or load it dynamically if we had table names in the dataset.
        # For this demo, we'll assume a standard schema (e.g. core tables).
        schema = get_detailed_schema_info(["FantasyOwners_LLM", "FantasySeasons_LLM"])

        examples.append(dspy.Example(
            question=item['question'],
            db_schema=schema,
            sql_query=item['sql']
        ).with_inputs('question', 'db_schema'))
    return examples

def validate_sql(example, prediction, trace=None):
    # exact match or semantic match
    # For SQL, usually execution accuracy is best, but here we do string match for simplicity in this demo script
    return prediction.sql_query.strip() == example.sql_query.strip()

def main():
    print("Initializing DSPy...")
    init_dspy()

    print("Loading dataset...")
    try:
        trainset = load_dataset()
    except FileNotFoundError:
        print("Dataset not found. Skipping optimization.")
        return

    print(f"Loaded {len(trainset)} examples.")

    # Define the module to optimize
    sql_gen = SQLGeneratorModule()

    # Define Teleprompter
    # We use BootstrapFewShot for speed/demo purposes, MIPROv2 is better for production
    print("Starting optimization...")
    teleprompter = BootstrapFewShot(metric=validate_sql, max_bootstrapped_demos=2)

    # Compile
    compiled_sql_gen = teleprompter.compile(sql_gen, trainset=trainset)

    print("Optimization complete.")

    # Save artifact
    output_path = "backend/data/compiled_sql_generator.json"
    compiled_sql_gen.save(output_path)
    print(f"Saved compiled artifact to {output_path}")

if __name__ == "__main__":
    main()
