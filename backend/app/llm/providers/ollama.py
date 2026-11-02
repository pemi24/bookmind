"""Ollama (local, offline, no API key). Talks to Ollama's HTTP API directly.

JSON output uses Ollama's `format` (a JSON Schema enforced by constrained decoding),
plus the shared validation/retry layer for anything the grammar can't guarantee.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.llm.errors import LLMError
from app.llm.providers.base import TRUNCATED_NOTE, LLMProvider, ProviderStatus
from app.llm.structured import inline_schema

_INSTALL_HINT = "Install it from https://ollama.com/download and make sure it is running (see README)."


class OllamaProvider(LLMProvider):
    name = "ollama"
    default_model = "qwen2.5:3b"
    local = True

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(settings)
        self.host = settings.ollama_host.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.host, transport=transport,
            timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=5.0),
        )

    @property
    def max_input_chars(self) -> int:
        # ~3.5 chars/token, keeping ~2,500 tokens for instructions and the answer.
        return max(4000, int((self.settings.ollama_num_ctx - 2500) * 3.5))

    @property
    def default_top_k(self) -> int:
        return 5

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---- errors --------------------------------------------------------
    def _not_running(self) -> LLMError:
        return LLMError(f"Ollama isn't running at {self.host}. {_INSTALL_HINT}", 503)

    def _http_error(self, status: int, body: bytes | str, model: str) -> LLMError:
        text = body.decode(errors="replace") if isinstance(body, bytes) else body
        try:
            text = json.loads(text).get("error", text)
        except (ValueError, AttributeError):
            pass
        if status == 404 or "not found" in text.lower():
            return LLMError(f"The model '{model}' isn't downloaded in Ollama. Run:  ollama pull {model}", 503)
        if "memory" in text.lower():
            return LLMError(f"Ollama ran out of memory loading '{model}'. Use a smaller model "
                            "(e.g. LLM_MODEL=qwen2.5:1.5b) or lower OLLAMA_NUM_CTX.", 503)
        return LLMError(f"Ollama error ({status}): {text[:300]}", 502)

    def _options(self, max_tokens: int, temperature: float) -> dict:
        return {"temperature": temperature, "num_ctx": self.settings.ollama_num_ctx,
                "num_predict": min(max_tokens, self.settings.ollama_num_ctx // 2)}

    # ---- generation ----------------------------------------------------
    async def stream_chat(self, system, messages, *, model=None, max_tokens=4096, effort=None) -> AsyncIterator[str]:
        model = model or self.model
        body = {"model": model, "stream": True, "keep_alive": self.settings.ollama_keep_alive,
                "messages": [{"role": "system", "content": system}, *messages],
                "options": self._options(max_tokens, self.settings.llm_temperature)}
        try:
            async with self._client.stream("POST", "/api/chat", json=body) as r:
                if r.status_code != 200:
                    raise self._http_error(r.status_code, await r.aread(), model)
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    if d.get("error"):
                        raise self._http_error(500, d["error"], model)
                    chunk = (d.get("message") or {}).get("content", "")
                    if chunk:
                        yield chunk
                    if d.get("done") and d.get("done_reason") == "length":
                        yield TRUNCATED_NOTE
        except httpx.ConnectError as e:
            raise self._not_running() from e
        except httpx.TimeoutException as e:
            raise LLMError("The local model took too long to answer. Try again, use a smaller model, "
                           "or raise LLM_TIMEOUT_SECONDS.", 504) from e

    async def _json_call(self, system: str, user: str, schema: type[BaseModel], *, model: str, max_tokens: int,
                         effort: str | None) -> Any:
        body = {"model": model, "stream": False, "keep_alive": self.settings.ollama_keep_alive,
                "format": inline_schema(schema),
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "options": self._options(max_tokens, 0.0)}
        try:
            r = await self._client.post("/api/chat", json=body)
        except httpx.ConnectError as e:
            raise self._not_running() from e
        except httpx.TimeoutException as e:
            raise LLMError("The local model took too long. Try again or use a smaller model.", 504) from e
        if r.status_code != 200:
            raise self._http_error(r.status_code, r.content, model)
        return (r.json().get("message") or {}).get("content", "")

    # ---- health --------------------------------------------------------
    async def check(self) -> ProviderStatus:
        try:
            r = await self._client.get("/api/tags", timeout=5.0)
            r.raise_for_status()
        except httpx.HTTPError:
            return ProviderStatus(False, f"Ollama isn't running at {self.host}. {_INSTALL_HINT}")
        installed = {m.get("name", "") for m in r.json().get("models", [])}
        missing = [m for m in dict.fromkeys([self.model, self.fast_model]) if not _has_model(installed, m)]
        if missing:
            cmds = "  ".join(f"ollama pull {m}" for m in missing)
            return ProviderStatus(False, f"Ollama is running but the model isn't downloaded. Run:  {cmds}")
        return ProviderStatus(True, f"Ollama · {self.model}")


def _has_model(installed: set[str], model: str) -> bool:
    if model in installed:
        return True
    if ":" not in model:  # "llama3.1" means "llama3.1:latest"
        return f"{model}:latest" in installed
    return False
