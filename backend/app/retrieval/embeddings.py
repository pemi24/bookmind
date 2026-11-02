"""Embedding providers (swappable).

To add a provider: subclass EmbeddingProvider, register it in `_PROVIDERS`, and set
EMBEDDING_PROVIDER / EMBEDDING_MODEL / EMBEDDING_DIM in .env. Changing the dimension
requires a new migration (see docs/ARCHITECTURE.md) and re-indexing all books.
"""
from __future__ import annotations

import logging
import os
import threading
from abc import ABC, abstractmethod
from functools import lru_cache

from app.config import get_settings

log = logging.getLogger(__name__)


def load_offline_first(cls, name: str, **kwargs):
    """Load a Hugging Face model from the local cache without touching the network; download
    it only if it isn't cached yet. Keeps the app fully offline after the first run (and
    avoids slow Hub checks on flaky connections)."""
    try:
        return cls(name, device="cpu", local_files_only=True, **kwargs)
    except Exception:  # noqa: BLE001 - not cached yet (or incomplete): fetch it once
        log.info("Model %s not in the local cache; downloading it (one time).", name)
        return cls(name, device="cpu", **kwargs)


class EmbeddingProvider(ABC):
    name: str
    dim: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed passages (blocking; call from a worker thread)."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a search query (blocking)."""


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str, dim: int, query_instruction: str, batch_size: int) -> None:
        self.name = model_name
        self.dim = dim
        self.query_instruction = query_instruction
        self.batch_size = batch_size
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                import torch
                from sentence_transformers import SentenceTransformer

                # Leave a core free so the UI/API stay responsive during indexing.
                torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
                log.info("Loading embedding model %s (first run downloads it)...", self.name)
                self._model = load_offline_first(SentenceTransformer, self.name)
                get_dim = getattr(self._model, "get_embedding_dimension", None) or \
                    self._model.get_sentence_embedding_dimension  # renamed in sentence-transformers 6
                actual = get_dim()
                if actual != self.dim:
                    raise RuntimeError(
                        f"Embedding model {self.name} has dimension {actual}, but EMBEDDING_DIM={self.dim}. "
                        "Fix .env (and re-run migrations on a fresh database)."
                    )
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vecs = model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False)
        return vecs.tolist()

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        vec = model.encode([self.query_instruction + text], normalize_embeddings=True, show_progress_bar=False)
        return vec[0].tolist()


_PROVIDERS = {"sentence-transformers": SentenceTransformerProvider}


@lru_cache
def get_embedder() -> EmbeddingProvider:
    s = get_settings()
    cls = _PROVIDERS.get(s.embedding_provider)
    if cls is None:
        raise RuntimeError(f"Unknown EMBEDDING_PROVIDER '{s.embedding_provider}'. Options: {list(_PROVIDERS)}")
    return cls(s.embedding_model, s.embedding_dim, s.embedding_query_instruction, s.embedding_batch_size)
