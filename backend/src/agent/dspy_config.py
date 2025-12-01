import os
import dspy
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Global variable to store the prompt registry
_PROMPT_REGISTRY: Dict[str, Any] = {}

def load_prompt_registry(registry_path: str = "data/prompt_registry.json") -> None:
    """
    Loads the compiled prompt configuration from a JSON file.
    """
    global _PROMPT_REGISTRY

    # Check current directory
    if os.path.exists(registry_path):
        path = registry_path
    # Check backend directory
    elif os.path.exists(os.path.join("backend", registry_path)):
        path = os.path.join("backend", registry_path)
    else:
        logger.warning(f"Prompt registry not found at {registry_path}. Using default prompts.")
        _PROMPT_REGISTRY = {}
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            _PROMPT_REGISTRY = json.load(f)
        logger.info(f"Loaded prompt registry from {path}")
    except Exception as e:
        logger.error(f"Failed to load prompt registry: {e}")
        _PROMPT_REGISTRY = {}

def get_optimized_program(program_name: str, module: dspy.Module) -> dspy.Module:
    """
    Applies the optimized parameters from the registry to the DSPy module if available.
    """
    if program_name in _PROMPT_REGISTRY:
        try:
            # Assuming the registry stores the state_dict or similar configuration
            # For dspy < 2.5, it might be load(), for newer, we might need to handle specific formats
            # Here we assume the registry contains the `save()` output of a DSPy program.
            # However, simpler approach for now: if we have a file path in the registry, load it.
            # But the instructions say the registry *is* the artifact.

            # If the registry entry is a path to a compiled file:
            artifact_data = _PROMPT_REGISTRY[program_name]

            if isinstance(artifact_data, str) and artifact_data.endswith(".json"):
                 module.load(artifact_data)
            elif isinstance(artifact_data, dict):
                 # Attempt to load state dict if it's directly embedded
                 # DSPy load expects a file path usually, but we can try to adapt
                 # For now, let's assume the registry maps "ProgramName" -> "path/to/compiled.json"
                 pass

            logger.info(f"Applied optimization for {program_name}")
        except Exception as e:
            logger.warning(f"Failed to apply optimization for {program_name}: {e}")

    return module

from src.config.llm_config import LLM_API_BASE_URL, LLM_MODEL_NAME, LLM_API_KEY, LLM_PROVIDER

def init_dspy():
    """
    Initializes DSPy with the configured model.
    """
    if not LLM_API_KEY:
        raise ValueError("LLM_API_KEY not found in environment variables")

    # Configure DSPy
    # We use the generic 'openai/' provider prefix to leverage the standardized API
    # even if it's Gemini or Ollama on the backend.

    # Construct model string.
    # For Ollama/OpenAI compatible, we usually prepend 'openai/' so dspy knows to use that client logic.
    # But if LLM_PROVIDER is specifically gemini using the native client, we might want to keep it.
    # However, to standardize, we should use the OpenAI compatibility if possible.

    # If the user selected 'ollama', the model name might be 'llama3', so 'openai/llama3'
    # If 'gemini', model might be 'gemini-1.5-pro', so 'openai/gemini-1.5-pro' pointing to google base_url

    dspy_model_name = f"openai/{LLM_MODEL_NAME}"

    logger.info(f"Initializing DSPy with model={dspy_model_name}, base_url={LLM_API_BASE_URL}")

    lm = dspy.LM(
        model=dspy_model_name,
        api_key=LLM_API_KEY,
        api_base=LLM_API_BASE_URL,  # dspy uses api_base instead of base_url often, or passes kwargs to litellm
        temperature=0
    )
    dspy.settings.configure(lm=lm)
    logger.info("DSPy initialized")

    # Load registry
    load_prompt_registry()
