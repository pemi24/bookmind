"""Providers with an OpenAI-style chat API and a free plan: Groq and OpenRouter.

Both are configured by a preset (address, key, default model, request limits). Requests are
sized to fit the provider (Groq's free plan allows ~8,000 tokens a minute, so chat prompts are
shortened with prompts.chat.fit_chat), and a used-up daily quota is reported with its reset
time so a provider chain can skip it until then.
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.llm.errors import LLMError
from app.llm.prompts.chat import fit_chat
from app.llm.providers.base import TRUNCATED_NOTE, LLMProvider, ProviderStatus


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    base_url: str
    default_model: str
    default_fast_model: str
    signup_url: str
    max_request_chars: int  # whole request (instructions + book text + question)
    max_answer_tokens: int
    top_k: int
    extra: dict = field(default_factory=dict)  # provider-specific request options
    backup_models: tuple[str, ...] = ()  # OpenRouter tries these itself if the first is busy


PRESETS = {
    "groq": Preset(
        "groq", "Groq", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "openai/gpt-oss-20b",
        "https://console.groq.com/keys",
        # Free plan: ~8,000 tokens per minute *including* the answer, so requests stay small.
        max_request_chars=16_000, max_answer_tokens=1200, top_k=6, extra={"reasoning_effort": "low"}),
    "openrouter": Preset(
        "openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3.5-lightning:free", "https://openrouter.ai/keys",
        max_request_chars=100_000, max_answer_tokens=4096, top_k=10, extra={"reasoning": {"effort": "low"}},
        backup_models=("nvidia/nemotron-3.5-super-vl:free", "google/gemma-4-31b-it:free")),
}

_DAILY = re.compile(r"per day|\b(?:RPD|TPD)\b|daily|free-models-per-day", re.I)


class OpenAICompatProvider(LLMProvider):
    def __init__(self, settings: Settings, preset: Preset, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(settings)
        self.preset = preset
        self.name = preset.key
        self.default_model = preset.default_model
        self._client = httpx.AsyncClient(
            base_url=preset.base_url, transport=transport,
            timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=10.0),
            headers={"Authorization": f"Bearer {self._key}", "X-Title": "BookMind"},
        )

    # ---- configuration -------------------------------------------------
    @property
    def _key(self) -> str:
        return getattr(self.settings, f"{self.preset.key}_api_key", "")

    @property
    def model(self) -> str:
        # LLM_MODEL names the main provider's model; backups use their own setting.
        own = getattr(self.settings, f"{self.preset.key}_model", "")
        if own:
            return own
        if self.settings.llm_provider == self.preset.key and self.settings.llm_model:
            return self.settings.llm_model
        return self.preset.default_model

    @property
    def fast_model(self) -> str:
        if self.settings.llm_provider == self.preset.key and self.settings.llm_fast_model:
            return self.settings.llm_fast_model
        return self.model if getattr(self.settings, f"{self.preset.key}_model", "") else self.preset.default_fast_model

    @property
    def max_input_chars(self) -> int:
        return max(4000, self.preset.max_request_chars - 6000)

    @property
    def default_top_k(self) -> int:
        return self.preset.top_k

    def configured(self) -> bool:
        return bool(self._key)

    def not_configured_message(self) -> str:
        return (f"{self.preset.key.upper()}_API_KEY is not set. Add it to backend/.env (create a free key at "
                f"{self.preset.signup_url}) and restart the backend.")

    async def aclose(self) -> None:
        await self._client.aclose()

    def _check_free(self, model: str) -> None:
        # OpenRouter bills paid models against account credits; BookMind only uses free ones.
        if self.preset.key == "openrouter" and not model.endswith(":free"):
            raise LLMError(f"OpenRouter model '{model}' isn't a free model. BookMind only uses models ending in "
                           "':free' (set OPENROUTER_MODEL in backend/.env).", 400)

    # ---- requests ------------------------------------------------------
    def _body(self, system: str, messages: list[dict], model: str, max_tokens: int, stream: bool) -> dict:
        self._check_free(model)
        try:
            system, messages = fit_chat(system, messages, self.preset.max_request_chars)
        except ValueError as e:
            raise LLMError(f"This request is too large for {self.preset.label}'s free plan.", 413) from e
        body: dict[str, Any] = {
            "model": model, "stream": stream, "temperature": self.settings.llm_temperature,
            "max_tokens": min(max_tokens, self.preset.max_answer_tokens),
            "messages": [{"role": "system", "content": system},
                         *({"role": m["role"], "content": m["content"]} for m in messages)],
            **self.preset.extra,
        }
        if self.preset.backup_models and model == self.preset.default_model:
            body["models"] = [model, *self.preset.backup_models]
        return body

    def _error(self, status: int, body: bytes, headers: httpx.Headers) -> LLMError:
        try:
            err = json.loads(body).get("error") or {}
            msg = err.get("message") or ""
            raw = json.dumps(err.get("metadata") or {})
        except (ValueError, AttributeError):
            msg, raw = body.decode(errors="replace")[:300], ""
        label = self.preset.label
        if status in (401, 403) and "agentic" not in msg:
            return LLMError(f"{label} rejected the API key. Check {self.preset.key.upper()}_API_KEY in backend/.env.", 503)
        if status == 404:
            return LLMError(f"{label} model '{self.model}' is unavailable: {msg[:160]}", 503)
        if status == 413 or "too large" in msg.lower():
            return LLMError(f"This request is too large for {label}'s free plan.", 413)
        if status == 429:
            retry = _retry_after(headers, msg)
            if _DAILY.search(msg + raw):
                return LLMError(f"{label}'s free daily limit is used up.", 429, retry_after=max(retry or 3600, 600))
            return LLMError(f"{label} is rate-limiting requests. Try again shortly.", 429,
                            retry_after=retry if retry is not None else 30)
        if status >= 500:
            return LLMError(f"{label} is temporarily unavailable.", 503, retry_after=30)
        return LLMError(f"{label} error ({status}): {msg[:200]}", 502)

    async def stream_chat(self, system, messages, *, model=None, max_tokens=4096, effort=None) -> AsyncIterator[str]:
        if not self.configured():
            raise LLMError(self.not_configured_message(), 503)
        body = self._body(system, messages, model or self.model, max_tokens, stream=True)
        try:
            async with self._client.stream("POST", "/chat/completions", json=body) as r:
                if r.status_code != 200:
                    raise self._error(r.status_code, await r.aread(), r.headers)
                async for line in r.aiter_lines():
                    if not line.startswith("data:") or line.strip() == "data: [DONE]":
                        continue
                    d = json.loads(line[5:])
                    if d.get("error"):  # OpenRouter reports mid-stream failures this way
                        raise self._error(int(d["error"].get("code") or 502), json.dumps(d).encode(), r.headers)
                    choice = (d.get("choices") or [{}])[0]
                    if text := (choice.get("delta") or {}).get("content"):
                        yield text
                    if choice.get("finish_reason") == "length":
                        yield TRUNCATED_NOTE
                    elif choice.get("finish_reason") == "content_filter":
                        raise LLMError(f"{self.preset.label}'s content filter stopped this answer.", 422)
        except httpx.ConnectError as e:
            raise LLMError(f"Can't reach {self.preset.label}. Check your internet connection.", 503) from e
        except httpx.TimeoutException as e:
            raise LLMError(f"{self.preset.label} timed out.", 504) from e

    async def _json_call(self, system: str, user: str, schema: type[BaseModel], *, model: str, max_tokens: int,
                         effort: str | None) -> Any:
        if not self.configured():
            raise LLMError(self.not_configured_message(), 503)
        body = self._body(system, [{"role": "user", "content": user}], model, max_tokens, stream=False)
        body["temperature"] = 0.0
        try:
            r = await self._client.post("/chat/completions", json=body)
        except httpx.ConnectError as e:
            raise LLMError(f"Can't reach {self.preset.label}. Check your internet connection.", 503) from e
        except httpx.TimeoutException as e:
            raise LLMError(f"{self.preset.label} timed out.", 504) from e
        if r.status_code != 200:
            raise self._error(r.status_code, r.content, r.headers)
        return ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""

    async def check(self) -> ProviderStatus:
        if not self.configured():
            return ProviderStatus(False, self.not_configured_message())
        try:
            r = await self._client.get("/models", timeout=10.0)
        except httpx.HTTPError:
            return ProviderStatus(False, f"Can't reach {self.preset.label}. Check your internet connection.")
        if r.status_code != 200:
            return ProviderStatus(False, self._error(r.status_code, r.content, r.headers).message)
        return ProviderStatus(True, f"{self.preset.label} · {self.model}")


def _retry_after(headers: httpx.Headers, msg: str) -> float | None:
    """Seconds to wait, from Retry-After or a "try again in 12m30s" style message."""
    try:
        if v := headers.get("retry-after"):
            return float(v)
    except ValueError:
        pass
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", msg)
    if m and any(m.groups()):
        h, mi, s = (float(x) if x else 0.0 for x in m.groups())
        return h * 3600 + mi * 60 + s
    return None
