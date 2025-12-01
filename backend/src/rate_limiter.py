import time
import logging
from src.config.llm_config import LLM_PROVIDER

logger = logging.getLogger(__name__)

def throttle(seconds: int = 5):
    """
    Sleeps for a specified duration if the LLM provider is remote.

    This function checks the globally configured LLM_PROVIDER.
    If the provider is local (e.g., "ollama", "llamacpp"), it does nothing.
    Otherwise (e.g., "gemini", "openai"), it sleeps for the specified seconds
    to prevent hitting rate limits.
    """
    # Normalize provider string
    provider = LLM_PROVIDER.lower()

    local_providers = ["ollama", "llamacpp", "local"]

    if provider in local_providers:
        # Local provider, no throttling needed
        return

    logger.info(f"Throttling for {seconds} seconds (Provider: {LLM_PROVIDER})...")
    time.sleep(seconds)
