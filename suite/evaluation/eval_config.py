import os
from dotenv import load_dotenv

# Evaluation Suite Configuration

# Load from project root .env
# __file__ is suite/evaluation/eval_config.py
# Root is two levels up
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

# The local LLM model to be used as the judge/evaluator via Ollama

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
