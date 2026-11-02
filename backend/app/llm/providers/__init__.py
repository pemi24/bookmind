"""Provider registry: LLM_PROVIDER in .env selects the implementation."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.llm.errors import LLMError
from app.llm.providers.base import LLMProvider, ProviderStatus

PROVIDERS = ("ollama", "gemini", "anthropic")


def create_provider(name: str, settings=None) -> LLMProvider:
    settings = settings or get_settings()
    name = name.strip().lower()
    if name == "ollama":
        from app.llm.providers.ollama import OllamaProvider

        return OllamaProvider(settings)
    if name == "gemini":
        from app.llm.providers.gemini import GeminiProvider

        return GeminiProvider(settings)
    if name == "anthropic":
        from app.llm.providers.anthropic import AnthropicProvider

        return AnthropicProvider(settings)
    raise LLMError(f"Unknown LLM_PROVIDER '{name}'. Use one of: {', '.join(PROVIDERS)}.", 503)


@lru_cache
def get_provider() -> LLMProvider:
    return create_provider(get_settings().llm_provider)


__all__ = ["LLMProvider", "ProviderStatus", "PROVIDERS", "create_provider", "get_provider"]
