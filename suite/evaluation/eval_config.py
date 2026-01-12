# Evaluation Suite Configuration

# The local LLM model to be used as the judge/evaluator via Ollama
JUDGE_MODEL = "llama3"

# Common settings for Ollama
OLLAMA_BASE_URL = "http://localhost:11434"
JUDGE_TEMPERATURE = 0

# Paths
DEFAULT_CONV_FILE = "suite/original-backend/data/test_set_conversations.csv"
OUTPUT_DIR = "eval_results"
