"""The single entry point features use for text generation.

It forwards to the provider selected by LLM_PROVIDER (Ollama by default, or Gemini /
Anthropic; see app/llm/providers/). Features never import a provider SDK directly.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TypeVar

from pydantic import BaseModel

from app.llm.errors import LLMError
from app.llm.providers import LLMProvider, ProviderStatus, get_provider

T = TypeVar("T", bound=BaseModel)

__all__ = ["LLMError", "complete_json", "complete_text", "llm_configured", "not_configured_message",
           "provider", "provider_status", "stream_text"]


def provider() -> LLMProvider:
    return get_provider()


def llm_configured() -> bool:
    return provider().configured()


def not_configured_message() -> str:
    return provider().not_configured_message()


async def provider_status() -> ProviderStatus:
    return await provider().check()


async def stream_text(
    system: str,
    messages: list[dict],
    *,
    model: str | None = None,
    effort: str | None = None,
    max_tokens: int = 4096,
) -> AsyncIterator[str]:
    """Yield text deltas. Raises LLMError with a user-facing message on failure."""
    async for chunk in provider().stream_chat(system, messages, model=model, max_tokens=max_tokens, effort=effort):
        yield chunk


async def complete_text(
    system: str, user: str, *, model: str | None = None, effort: str | None = None, max_tokens: int = 4096
) -> str:
    parts = [c async for c in stream_text(system, [{"role": "user", "content": user}],
                                           model=model, effort=effort, max_tokens=max_tokens)]
    return "".join(parts).strip()


async def complete_json(
    system: str,
    user: str,
    schema: type[T],
    *,
    model: str | None = None,
    effort: str | None = None,
    max_tokens: int = 4096,
) -> T:
    """Structured output, validated against `schema` (with salvage + retries for small models)."""
    return await provider().generate_json(system, user, schema, model=model, max_tokens=max_tokens, effort=effort)
