"""Central configuration. Every tunable lives here and can be overridden in backend/.env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings,
                                   file_secret_settings):
        # backend/.env wins over inherited process variables, so a stray ANTHROPIC_API_KEY or
        # DATABASE_URL in the shell can't silently replace the project's configuration.
        # Variables not present in .env still come from the environment. Set
        # BOOKMIND_ENV_OVERRIDE=1 to let the environment win (the test suite does this).
        if os.environ.get("BOOKMIND_ENV_OVERRIDE") == "1":
            return init_settings, env_settings, dotenv_settings, file_secret_settings
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    # --- Database ---
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/bookmind"
    db_pool_size: int = 10
    db_max_overflow: int = 10

    # --- LLM provider (see app/llm/providers/) ---
    llm_provider: str = "ollama"  # ollama (local, default) | gemini | anthropic
    # Empty = the provider's default model (ollama: qwen2.5:3b, gemini: gemini-2.5-flash,
    # anthropic: claude-opus-5-5).
    llm_model: str = ""
    # Model for bulk/background jobs (entity extraction, timeline, quizzes). Empty = LLM_MODEL.
    llm_fast_model: str = ""
    llm_temperature: float = 0.2  # ollama / gemini (Anthropic's current models don't accept it)
    llm_timeout_seconds: float = 600.0  # local models on CPU can be slow
    llm_max_retries: int = 2  # network/overload retries (cloud providers)
    llm_json_retries: int = 2  # extra attempts when a model returns invalid JSON
    # Follow-up questions: "llm" rewrites them into a standalone search query with the model,
    # "heuristic" adds the previous question to the search (no extra model call), "auto" picks
    # heuristic for local models and llm for cloud ones.
    query_rewrite: str = "auto"

    # Ollama (local)
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_num_ctx: int = 8192  # context window (tokens); larger = more RAM
    ollama_keep_alive: str = "30m"  # keep the model loaded between requests

    # Google Gemini
    gemini_api_key: str = ""

    # Anthropic (optional)
    anthropic_api_key: str = ""
    llm_chat_effort: str = "low"  # low | medium | high | xhigh | max
    llm_task_effort: str = "low"
    llm_refusal_fallback: bool = True  # re-route a policy-declined request to another model

    # --- Embeddings (swappable, see app/retrieval/embeddings.py) ---
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embedding_batch_size: int = 32
    embedding_query_instruction: str = "Represent this sentence for searching relevant passages: "

    # --- Re-ranking ---
    rerank_enabled: bool = True
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L6-v2"

    # --- Chunking (approximate tokens; 1 token ~= 4 chars of English) ---
    # bge-small embeds the first 512 model tokens; 500/700 keeps nearly all text in the vector.
    # Keyword search always covers the full chunk.
    chunk_target_tokens: int = 500
    chunk_max_tokens: int = 700
    chunk_overlap_tokens: int = 80

    # --- Retrieval ---
    retrieval_candidates: int = 40  # per search arm (vector / keyword)
    # Passages handed to the LLM. 0 = auto: 5 for local models (small context, CPU prompt
    # processing is slow), 8 for cloud models.
    retrieval_top_k: int = 0
    rrf_k: int = 60
    hnsw_ef_search: int = 100

    # --- Uploads ---
    upload_dir: Path = BACKEND_DIR / "data" / "uploads"
    max_upload_mb: int = 200

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    return s
