"""Errors raised by the LLM layer (any provider)."""
from __future__ import annotations


class LLMError(Exception):
    """An LLM failure with a message that is safe to show to the user."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
