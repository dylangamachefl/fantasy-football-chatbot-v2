# Evaluation Suite Configuration

# The local LLM model to be used as the judge/evaluator via Ollama
JUDGE_MODEL = "llama3"

# Common settings for Ollama
OLLAMA_BASE_URL = "http://localhost:11434"
JUDGE_TEMPERATURE = 0

# Paths
SHARED_DIR = "shared"
GOLDEN_DATASET = f"{SHARED_DIR}/golden_dataset.json"
SCHEMA_FILE = f"{SHARED_DIR}/schema.json"
DEFAULT_CONV_FILE = f"{SHARED_DIR}/test_set_conversations.csv"
OUTPUT_DIR = "eval_results"
PROMPTS_TS_PATH = "apps/chat-app/src/lib/prompts.ts"
