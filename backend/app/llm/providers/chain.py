"""A provider chain (LLM_FALLBACKS): the main provider, then backups, used in order.

A request moves on to the next provider when the current one is used up, rate-limited,
overloaded, times out, refuses the content or finds the request too large, as long as no
text has been shown yet (a half-written answer is never mixed with another provider's).
A provider that reported when it will accept requests again (e.g. a used-up free daily
quota) is skipped until then, so later requests don't waste time on it.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any, TypeVar

from pydantic import BaseModel

from app.llm.errors import LLMError
from app.llm.providers.base import LLMProvider, ProviderStatus

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# Failures another provider can do better on (not e.g. a bad API key or a malformed request).
_MOVE_ON = {413, 422, 429, 502, 503, 504}
# A provider that says "try again in a few seconds" is waited for rather than skipped.
BRIEF_WAIT_SECONDS = 20.0


class ChainProvider(LLMProvider):
    def __init__(self, providers: list[LLMProvider]) -> None:
        super().__init__(providers[0].settings)
        self.providers = providers
        self.primary = providers[0]
        self._resting: dict[str, float] = {}  # provider name -> time.monotonic() when to try it again

    # The main provider decides prompt sizes and is what the app reports; backups shrink requests
    # to their own limits when they're used.
    name = property(lambda self: self.primary.name)
    model = property(lambda self: self.primary.model)
    fast_model = property(lambda self: self.primary.fast_model)
    local = property(lambda self: self.primary.local)
    max_input_chars = property(lambda self: self.primary.max_input_chars)
    default_top_k = property(lambda self: self.primary.default_top_k)

    def configured(self) -> bool:
        return any(p.configured() for p in self.providers)

    def not_configured_message(self) -> str:
        return self.primary.not_configured_message()

    async def aclose(self) -> None:
        for p in self.providers:
            await p.aclose()

    async def check(self) -> ProviderStatus:
        main = await self.primary.check()
        backups = [p for p in self.providers[1:] if p.configured()]
        names = ", ".join(p.name.capitalize() for p in backups)
        if main.ok:
            return ProviderStatus(True, main.message + (f" (backups: {names})" if names else ""))
        for p in backups:
            if (st := await p.check()).ok:
                return ProviderStatus(True, f"{st.message}; main provider unavailable: {main.message}")
        return main

    # ---- routing -------------------------------------------------------
    def _usable(self) -> list[LLMProvider]:
        now = time.monotonic()
        ready = [p for p in self.providers if p.configured() and self._resting.get(p.name, 0.0) <= now]
        if ready:
            return ready
        # Everything is resting: try whichever comes back first rather than failing outright.
        configured = [p for p in self.providers if p.configured()]
        return sorted(configured, key=lambda p: self._resting.get(p.name, 0.0))[:1]

    def _model_for(self, p: LLMProvider, model: str | None) -> str | None:
        """Model names belong to one provider: map the main provider's model/fast model to the backup's."""
        if p is self.primary or model is None:
            return model
        return p.fast_model if model == self.primary.fast_model and model != self.primary.model else p.model

    def _rest(self, p: LLMProvider, e: LLMError) -> None:
        if e.retry_after:
            self._resting[p.name] = time.monotonic() + e.retry_after
        log.warning("%s unavailable (%s): %s; trying the next provider", p.name, e.status, e.message)

    async def stream_chat(self, system, messages, *, model=None, max_tokens=4096, effort=None) -> AsyncIterator[str]:
        last: LLMError | None = None
        for p in self._usable():
            for attempt in range(2):
                started = False
                try:
                    async for chunk in p.stream_chat(system, messages, model=self._model_for(p, model),
                                                     max_tokens=max_tokens, effort=effort):
                        started = True
                        yield chunk
                    return
                except LLMError as e:
                    if started or e.status not in _MOVE_ON:
                        raise
                    last = e
                    if attempt == 0 and await self._brief_wait(e):
                        continue  # a per-minute limit that clears in seconds: same provider, not a slower one
                    self._rest(p, e)
                    break
        raise last or LLMError(self.not_configured_message(), 503)

    async def generate_json(self, system: str, user: str, schema: type[T], *, model: str | None = None,
                            max_tokens: int = 4096, effort: str | None = None) -> T:
        last: LLMError | None = None
        for p in self._usable():
            for attempt in range(2):
                try:
                    return await p.generate_json(system, user, schema, model=self._model_for(p, model),
                                                 max_tokens=max_tokens, effort=effort)
                except LLMError as e:
                    if e.status not in _MOVE_ON:
                        raise
                    last = e
                    if attempt == 0 and await self._brief_wait(e):
                        continue
                    self._rest(p, e)
                    break
        raise last or LLMError(self.not_configured_message(), 503)

    @staticmethod
    async def _brief_wait(e: LLMError) -> bool:
        """Wait out a rate limit that clears within a few seconds (e.g. Groq's per-minute token limit)."""
        if e.status == 429 and e.retry_after is not None and e.retry_after <= BRIEF_WAIT_SECONDS:
            await asyncio.sleep(e.retry_after + 0.5)
            return True
        return False

    async def _json_call(self, *a: Any, **kw: Any) -> Any:  # pragma: no cover - generate_json is overridden
        raise NotImplementedError
