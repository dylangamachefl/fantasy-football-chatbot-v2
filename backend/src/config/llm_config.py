
import os
from typing import Optional

def get_env_var(key: str, default: Optional[str] = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        raise ValueError(f"Environment variable '{key}' not set and no default provided.")
    return value

# Standardize LLM configuration
LLM_PROVIDER = get_env_var("LLM_PROVIDER", "gemini")  # Options: "gemini", "ollama", "openai"

# API Base URLs
# Default for Gemini (OpenAI compatible) or Native
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OLLAMA_BASE_URL = "http://ollama:11434/v1" # Docker internal DNS

# Determine active configuration
if LLM_PROVIDER == "ollama":
    LLM_API_BASE_URL = get_env_var("LLM_API_BASE_URL", OLLAMA_BASE_URL)
    LLM_MODEL_NAME = get_env_var("LLM_MODEL_NAME", "llama3")
    LLM_API_KEY = get_env_var("LLM_API_KEY", "ollama") # Ollama doesn't need a real key but client might expect one
elif LLM_PROVIDER == "gemini":
    # For Gemini via OpenAI compatibility or Native
    LLM_API_BASE_URL = get_env_var("LLM_API_BASE_URL", GEMINI_BASE_URL)
    LLM_MODEL_NAME = get_env_var("LLM_MODEL_NAME", "gemini-2.0-flash")
    LLM_API_KEY = get_env_var("GOOGLE_API_KEY") # Required for Gemini
else:
    # Generic OpenAI or other provider
    LLM_API_BASE_URL = get_env_var("LLM_API_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = get_env_var("LLM_MODEL_NAME", "gpt-4o")
    LLM_API_KEY = get_env_var("LLM_API_KEY")
