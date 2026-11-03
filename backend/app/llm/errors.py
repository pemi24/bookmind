"""Errors raised by the LLM layer (any provider)."""
from __future__ import annotations


class LLMError(Exception):
    """An LLM failure with a message that is safe to show to the user.

    `retry_after`: seconds until the provider will accept requests again, when known. A provider
    chain (LLM_FALLBACKS) uses it to skip a provider whose free quota is used up until it resets.
    """

    def __init__(self, message: str, status: int = 502, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.retry_after = retry_after
