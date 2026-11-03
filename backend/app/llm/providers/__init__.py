"""Provider registry: LLM_PROVIDER in .env selects the implementation."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.llm.errors import LLMError
from app.llm.providers.base import LLMProvider, ProviderStatus

PROVIDERS = ("ollama", "gemini", "anthropic", "groq", "openrouter")


def create_provider(name: str, settings=None) -> LLMProvider:
    settings = settings or get_settings()
    name = name.strip().lower()
    if name in ("groq", "openrouter"):
        from app.llm.providers.openai_compat import PRESETS, OpenAICompatProvider

        return OpenAICompatProvider(settings, PRESETS[name])
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


def build_provider(settings=None) -> LLMProvider:
    """LLM_PROVIDER, wrapped in a chain with the LLM_FALLBACKS backups when any are set."""
    settings = settings or get_settings()
    main = create_provider(settings.llm_provider, settings)
    names = [n.strip().lower() for n in settings.llm_fallbacks.split(",") if n.strip()]
    backups = [create_provider(n, settings) for n in dict.fromkeys(names) if n != main.name]
    if not backups:
        return main
    from app.llm.providers.chain import ChainProvider

    return ChainProvider([main, *backups])


@lru_cache
def get_provider() -> LLMProvider:
    return build_provider()


__all__ = ["LLMProvider", "ProviderStatus", "PROVIDERS", "build_provider", "create_provider", "get_provider"]
