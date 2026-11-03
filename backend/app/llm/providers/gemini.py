"""Google Gemini via the REST API (no extra SDK). Needs GEMINI_API_KEY."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.llm.errors import LLMError
from app.llm.providers.base import TRUNCATED_NOTE, LLMProvider, ProviderStatus

API = "https://generativelanguage.googleapis.com/v1beta"
log = logging.getLogger(__name__)
# Short retries for "busy" answers before giving up (the free tier often has brief demand spikes).
_RETRY_STATUSES = (429, 500, 502, 503, 504)
_RETRY_DELAYS = (2.0, 5.0)
_RETRIES = len(_RETRY_DELAYS)
# Models whose free *daily* quota is used up -> time.monotonic() when to try them again.
_exhausted: dict[str, float] = {}


def _daily_quota_reset(body: bytes) -> float | None:
    """Seconds until a used-up per-day quota resets (Google's retryDelay), or None for other 429s."""
    try:
        details = json.loads(body).get("error", {}).get("details", [])
    except (ValueError, AttributeError):
        return None
    if not any("PerDay" in (v.get("quotaId") or "") for d in details for v in d.get("violations", [])):
        return None
    delay = next((d.get("retryDelay") for d in details if d.get("retryDelay")), "3600s")
    try:
        return max(float(str(delay).rstrip("s")), 60.0)
    except ValueError:
        return 3600.0


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
            if reset := _daily_quota_reset(body):
                return LLMError(f"Gemini's free daily quota for {self.model} is used up (it resets in about "
                                f"{reset / 3600:.0f} h).", 429, retry_after=reset)
            return LLMError("Gemini is rate-limiting requests (or the free quota is used up). Try again later.", 429,
                            retry_after=60)
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
        failure: tuple[int, bytes] = (503, b"")
        try:
            for m in self._models(model):
                for attempt in range(_RETRIES + 1):
                    async with self._client.stream("POST", f"/models/{m}:streamGenerateContent",
                                                   params={"alt": "sse"}, json=body) as r:
                        if r.status_code == 200:
                            async for chunk in self._read_stream(r):
                                yield chunk
                            return
                        failure = (r.status_code, await r.aread())
                    if not await self._should_retry(m, *failure, attempt):
                        break  # nothing was shown yet, so retrying can't duplicate text
                if failure[0] not in _RETRY_STATUSES:
                    break  # a bad request or key won't work on another model either
        except httpx.ConnectError as e:
            raise LLMError("Can't reach Gemini. Check your internet connection.", 503) from e
        except httpx.TimeoutException as e:
            raise LLMError("Gemini timed out. Please try again.", 504) from e
        raise self._error(*failure)

    @property
    def fast_model(self) -> str:
        # Side tasks (rewording follow-ups, alternative search queries) use the light model, keeping the
        # main model's small free daily quota for answers.
        return self.settings.llm_fast_model or self.settings.gemini_fallback_model.strip() or self.model

    def _models(self, model: str) -> list[str]:
        """The requested model, then the fallback; a model whose daily quota is used up is skipped."""
        fallback = self.settings.gemini_fallback_model.strip()
        # With a provider chain (LLM_FALLBACKS), the next provider takes over instead.
        if self.settings.llm_fallbacks.strip():
            fallback = ""
        models = [model, fallback] if fallback and fallback != model else [model]
        now = time.monotonic()
        usable = [m for m in models if _exhausted.get(m, 0.0) <= now]
        return usable or models[-1:]

    async def _should_retry(self, model: str, status: int, body: bytes, attempt: int) -> bool:
        """Busy/overloaded answers ("high demand" spikes are common on the free tier) get short retries.
        A used-up *daily* quota is not retried: the model is set aside until Google's reset time."""
        text = body[:400].decode(errors="replace")
        log.warning("Gemini %s HTTP %s (attempt %d): %s", model, status, attempt + 1, text[:200])
        if status == 429 and (until := _daily_quota_reset(body)):
            _exhausted[model] = time.monotonic() + until
            log.warning("Gemini %s: free daily quota used up; using the fallback model for %.1f h", model, until / 3600)
            return False
        if status not in _RETRY_STATUSES or attempt >= _RETRIES:
            return False
        await asyncio.sleep(_RETRY_DELAYS[attempt])
        return True

    @staticmethod
    async def _read_stream(r: httpx.Response) -> AsyncIterator[str]:
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
                # Google's filter sometimes trips on harmless book passages (often with the lighter models).
                raise LLMError("Google's content filter stopped this answer, which can happen even with harmless "
                               "passages. Try rephrasing the question, or use another AI provider in backend/.env.", 422)
            if reason == "MAX_TOKENS":
                yield TRUNCATED_NOTE

    async def _json_call(self, system: str, user: str, schema: type[BaseModel], *, model: str, max_tokens: int,
                         effort: str | None) -> Any:
        self._guard()
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0,
                                 "maxOutputTokens": max(max_tokens, 8192)},
        }
        for m in self._models(model):
            for attempt in range(_RETRIES + 1):
                try:
                    r = await self._client.post(f"/models/{m}:generateContent", json=body)
                except httpx.ConnectError as e:
                    raise LLMError("Can't reach Gemini. Check your internet connection.", 503) from e
                except httpx.TimeoutException as e:
                    raise LLMError("Gemini timed out. Please try again.", 504) from e
                if r.status_code == 200 or not await self._should_retry(m, r.status_code, r.content, attempt):
                    break
            if r.status_code == 200 or r.status_code not in _RETRY_STATUSES:
                break
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
