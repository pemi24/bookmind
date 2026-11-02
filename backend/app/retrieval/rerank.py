"""Cross-encoder re-ranking of retrieval candidates (local, CPU)."""
from __future__ import annotations

import logging
import math
import threading
from functools import lru_cache

from app.config import get_settings

log = logging.getLogger(__name__)


class Reranker:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import CrossEncoder

                from app.retrieval.embeddings import load_offline_first

                log.info("Loading re-ranker %s ...", self.model_name)
                self._model = load_offline_first(CrossEncoder, self.model_name, max_length=512)
        return self._model

    def score(self, query: str, texts: list[str]) -> list[float]:
        """Relevance probabilities in [0, 1] (blocking)."""
        if not texts:
            return []
        logits = self._load().predict([(query, t[:2000]) for t in texts], show_progress_bar=False)
        return [1 / (1 + math.exp(-float(x))) for x in logits]


@lru_cache
def get_reranker() -> Reranker | None:
    s = get_settings()
    return Reranker(s.rerank_model) if s.rerank_enabled else None
