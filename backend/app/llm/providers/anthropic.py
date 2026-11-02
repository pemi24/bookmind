"""Anthropic Claude (optional provider). Needs ANTHROPIC_API_KEY."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import anthropic
from pydantic import BaseModel

from app.config import Settings
from app.llm.errors import LLMError
from app.llm.providers.base import TRUNCATED_NOTE, LLMProvider, ProviderStatus

log = logging.getLogger(__name__)

# Server-side refusal fallback: if a request is declined by a safety classifier, the API
# re-runs it on a fallback model inside the same call (LLM_REFUSAL_FALLBACK=false to disable).
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-opus-5-5"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._client: anthropic.AsyncAnthropic | None = None

    def configured(self) -> bool:
        return bool(self.settings.anthropic_api_key)

    def not_configured_message(self) -> str:
        return ("ANTHROPIC_API_KEY is not set. Add it to backend/.env and restart the backend, "
                "or use LLM_PROVIDER=ollama for a free local model.")

    def client(self) -> anthropic.AsyncAnthropic:
        if not self.configured():
            raise LLMError(self.not_configured_message(), 503)
        if self._client is None:
            s = self.settings
            self._client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key, max_retries=s.llm_max_retries,
                                                    timeout=s.llm_timeout_seconds)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()

    def translate_error(self, e: Exception) -> LLMError:
        if isinstance(e, LLMError):
            return e
        if isinstance(e, anthropic.AuthenticationError):
            return LLMError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in backend/.env.", 503)
        if isinstance(e, anthropic.PermissionDeniedError):
            return LLMError("This API key doesn't have access to the configured model.", 503)
        if isinstance(e, anthropic.NotFoundError):
            return LLMError(f"Model not found. Check LLM_MODEL in backend/.env ({self.model}).", 503)
        if isinstance(e, anthropic.RateLimitError):
            return LLMError("The AI service is rate-limiting requests. Wait a moment and try again.", 429)
        if isinstance(e, anthropic.BadRequestError):
            return LLMError(f"The AI service rejected the request: {e.message}", 400)
        if isinstance(e, anthropic.APIStatusError):
            if e.status_code == 529 or e.status_code >= 500:
                return LLMError("The AI service is temporarily overloaded. Please try again shortly.", 503)
            return LLMError(f"AI service error ({e.status_code}): {e.message}", 502)
        if isinstance(e, anthropic.APITimeoutError):
            return LLMError("The AI service timed out. Please try again.", 504)
        if isinstance(e, anthropic.APIConnectionError):
            return LLMError("Can't reach the AI service. Check your internet connection.", 503)
        log.exception("Unexpected LLM error", exc_info=e)
        return LLMError(f"Unexpected AI error: {e}", 500)

    def _common(self, model: str | None, effort: str | None) -> dict:
        s = self.settings
        kw: dict = {"model": model or self.model, "output_config": {"effort": effort or s.llm_chat_effort}}
        if s.llm_refusal_fallback:
            kw["betas"] = [_FALLBACK_BETA]
            kw["fallbacks"] = "default"
        return kw

    async def stream_chat(self, system, messages, *, model=None, max_tokens=16000, effort=None) -> AsyncIterator[str]:
        try:
            async with self.client().beta.messages.stream(
                system=system, messages=messages, max_tokens=max(max_tokens, 16000),
                cache_control={"type": "ephemeral"}, **self._common(model, effort),
            ) as stream:
                async for chunk in stream.text_stream:
                    yield chunk
                final = await stream.get_final_message()
        except Exception as e:  # noqa: BLE001
            raise self.translate_error(e) from e
        if final.stop_reason == "refusal":
            raise LLMError("The AI declined to answer this request.", 422)
        if final.stop_reason == "max_tokens":
            yield TRUNCATED_NOTE

    async def _json_call(self, system: str, user: str, schema: type[BaseModel], *, model: str, max_tokens: int,
                         effort: str | None) -> Any:
        # Native structured outputs; the shared layer still validates the result.
        try:
            resp = await self.client().beta.messages.parse(
                system=system, messages=[{"role": "user", "content": user}], max_tokens=max(max_tokens, 16000),
                output_format=schema, **self._common(model, effort or self.settings.llm_task_effort),
            )
        except Exception as e:  # noqa: BLE001
            raise self.translate_error(e) from e
        if resp.stop_reason == "refusal":
            raise LLMError("The AI declined this request.", 422)
        return resp.parsed_output.model_dump() if resp.parsed_output is not None else ""

    async def check(self) -> ProviderStatus:
        if not self.configured():
            return ProviderStatus(False, self.not_configured_message())
        try:
            await self.client().models.retrieve(self.model)
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(False, self.translate_error(e).message)
        return ProviderStatus(True, f"Anthropic · {self.model}")
