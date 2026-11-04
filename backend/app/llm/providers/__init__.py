"""Provider registry: LLM_PROVIDER in .env selects the implementation."""
from __future__ import annotations

from contextvars import ContextVar
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
    # Backups use their own default models: LLM_MODEL names a model of the main provider.
    plain = settings.model_copy(update={"llm_model": "", "llm_fast_model": ""})
    backups = [create_provider(n, plain) for n in dict.fromkeys(names) if n != main.name]
    if not backups:
        return main
    from app.llm.providers.chain import ChainProvider

    return ChainProvider([main, *backups])


@lru_cache
def get_provider() -> LLMProvider:
    return build_provider()


# The signed-in user's own choice ({"provider", "model"} from their settings), set per request.
# Background jobs started by a request inherit it (asyncio copies context into new tasks).
user_choice: ContextVar[tuple[str, str] | None] = ContextVar("bookmind_llm_choice", default=None)


@lru_cache(maxsize=16)
def _provider_for(name: str, model: str) -> LLMProvider:
    s = get_settings()
    # Same backups as the server's own setup, behind the user's choice.
    return build_provider(s.model_copy(update={"llm_provider": name, "llm_model": model,
                                               "llm_fast_model": "" if model else s.llm_fast_model}))


def current_provider() -> LLMProvider:
    """The provider for this request: the user's choice when they made one, else the server's."""
    choice = user_choice.get()
    s = get_settings()
    if not choice or (choice[0] == s.llm_provider.strip().lower() and choice[1] in ("", s.llm_model)):
        return get_provider()
    return _provider_for(*choice)


def choice_from_settings(settings: dict | None) -> tuple[str, str] | None:
    name = str((settings or {}).get("llm_provider") or "").strip().lower()
    if name not in PROVIDERS:
        return None
    return name, str((settings or {}).get("llm_model") or "").strip()


__all__ = ["LLMProvider", "ProviderStatus", "PROVIDERS", "build_provider", "choice_from_settings", "create_provider",
           "current_provider", "get_provider", "user_choice"]
