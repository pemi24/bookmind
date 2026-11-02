"""Google Gemini via the REST API (no extra SDK). Needs GEMINI_API_KEY."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.llm.errors import LLMError
from app.llm.providers.base import TRUNCATED_NOTE, LLMProvider, ProviderStatus

API = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-3.5-flash"

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(settings)
        self._client = httpx.AsyncClient(
            base_url=API, transport=transport,
            timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=10.0),
            headers={"x-goog-api-key": settings.gemini_api_key},
        )

    @property
    def default_top_k(self) -> int:
        # Large context and cheap input tokens: more passages lets answers recover from re-ranker misses.
        return 12

    def configured(self) -> bool:
        return bool(self.settings.gemini_api_key)

    def not_configured_message(self) -> str:
        return ("GEMINI_API_KEY is not set. Add it to backend/.env (get one at https://aistudio.google.com) "
                "and restart the backend, or use LLM_PROVIDER=ollama for a free local model.")

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _contents(messages: list[dict]) -> list[dict]:
        return [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in messages]

    def _error(self, status: int, body: bytes) -> LLMError:
        try:
            msg = json.loads(body)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            msg = body.decode(errors="replace")[:300]
        if status == 400 and "api key" in msg.lower():
            return LLMError("The Gemini API key was rejected. Check GEMINI_API_KEY in backend/.env.", 503)
        if status in (401, 403):
            return LLMError(f"Gemini refused the request (permission): {msg}", 503)
        if status == 404:
            # Includes Google's reason, e.g. a model retired for new API keys.
            return LLMError(f"Gemini model '{self.model}' is unavailable: {msg[:200]} "
                            "Set LLM_MODEL in backend/.env to a current model.", 503)
        if status == 429:
            return LLMError("Gemini is rate-limiting requests (or the free quota is used up). Try again later.", 429)
        if status >= 500:
            return LLMError("Gemini is temporarily unavailable. Please try again shortly.", 503)
        return LLMError(f"Gemini error ({status}): {msg}", 502)

    def _guard(self) -> None:
        if not self.configured():
            raise LLMError(self.not_configured_message(), 503)

    async def stream_chat(self, system, messages, *, model=None, max_tokens=4096, effort=None) -> AsyncIterator[str]:
        self._guard()
        model = model or self.model
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": self._contents(messages),
            # Thinking models count reasoning tokens against this limit, so keep it generous.
            "generationConfig": {"maxOutputTokens": max(max_tokens, 8192), "temperature": self.settings.llm_temperature},
        }
        try:
            async with self._client.stream("POST", f"/models/{model}:streamGenerateContent", params={"alt": "sse"},
                                           json=body) as r:
                if r.status_code != 200:
                    raise self._error(r.status_code, await r.aread())
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    d = json.loads(line[5:])
                    cand = (d.get("candidates") or [{}])[0]
                    for part in (cand.get("content") or {}).get("parts", []):
                        if part.get("text") and not part.get("thought"):
                            yield part["text"]
                    reason = cand.get("finishReason")
                    if reason in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
                        raise LLMError("Gemini declined to answer this request.", 422)
                    if reason == "MAX_TOKENS":
                        yield TRUNCATED_NOTE
        except httpx.ConnectError as e:
            raise LLMError("Can't reach Gemini. Check your internet connection.", 503) from e
        except httpx.TimeoutException as e:
            raise LLMError("Gemini timed out. Please try again.", 504) from e

    async def _json_call(self, system: str, user: str, schema: type[BaseModel], *, model: str, max_tokens: int,
                         effort: str | None) -> Any:
        self._guard()
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0,
                                 "maxOutputTokens": max(max_tokens, 8192)},
        }
        try:
            r = await self._client.post(f"/models/{model}:generateContent", json=body)
        except httpx.ConnectError as e:
            raise LLMError("Can't reach Gemini. Check your internet connection.", 503) from e
        except httpx.TimeoutException as e:
            raise LLMError("Gemini timed out. Please try again.", 504) from e
        if r.status_code != 200:
            raise self._error(r.status_code, r.content)
        cand = (r.json().get("candidates") or [{}])[0]
        return "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))

    async def check(self) -> ProviderStatus:
        if not self.configured():
            return ProviderStatus(False, self.not_configured_message())
        try:
            r = await self._client.get(f"/models/{self.model}", timeout=10.0)
        except httpx.HTTPError:
            return ProviderStatus(False, "Can't reach Gemini. Check your internet connection.")
        if r.status_code != 200:
            return ProviderStatus(False, self._error(r.status_code, r.content).message)
        return ProviderStatus(True, f"Gemini · {self.model}")
