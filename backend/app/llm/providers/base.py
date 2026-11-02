"""The provider-agnostic LLM interface.

Every feature talks to an `LLMProvider` (through app/llm/client.py); providers only
implement transport: streaming chat and a raw JSON call. Validation, salvage and retry
of JSON output are shared (app/llm/structured.py).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from app.config import Settings
from app.llm.structured import generate_validated, json_instructions

T = TypeVar("T", bound=BaseModel)

TRUNCATED_NOTE = "\n\n_(Answer truncated: it hit the length limit.)_"


@dataclass
class ProviderStatus:
    ok: bool
    message: str  # human-readable; tells the user exactly what to do when not ok


class LLMProvider(ABC):
    name: str = "base"
    default_model: str = ""
    local: bool = False  # runs on this machine (affects defaults like context size)

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ---- configuration -------------------------------------------------
    @property
    def model(self) -> str:
        return self.settings.llm_model or self.default_model

    @property
    def fast_model(self) -> str:
        return self.settings.llm_fast_model or self.model

    @property
    def max_input_chars(self) -> int:
        """Book text that fits in one request, leaving room for instructions and the answer."""
        return 160_000

    @property
    def default_top_k(self) -> int:
        return 8

    def configured(self) -> bool:
        """Static configuration present (e.g. an API key). Reachability is `check()`."""
        return True

    def not_configured_message(self) -> str:
        return f"The {self.name} provider is not configured."

    async def check(self) -> ProviderStatus:
        return ProviderStatus(True, f"{self.name} ({self.model})")

    async def aclose(self) -> None:  # noqa: B027 - optional hook
        pass

    # ---- generation ----------------------------------------------------
    @abstractmethod
    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        effort: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield text deltas for a chat ([{role: user|assistant, content}]). Raises LLMError."""

    @abstractmethod
    async def _json_call(
        self, system: str, user: str, schema: type[BaseModel], *, model: str, max_tokens: int,
        effort: str | None,
    ) -> Any:
        """One raw JSON-mode request. Returns the reply text (or an already-parsed object)."""

    async def generate_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        effort: str | None = None,
    ) -> T:
        """Structured output validated against `schema`, with salvage + retry."""
        system = f"{system}\n\n{json_instructions(schema)}"

        async def raw(sys_prompt: str, user_prompt: str) -> Any:
            return await self._json_call(sys_prompt, user_prompt, schema, model=model or self.fast_model,
                                         max_tokens=max_tokens, effort=effort)

        return await generate_validated(raw, system, user, schema, self.settings.llm_json_retries)
