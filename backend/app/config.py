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
    # Empty = the provider's default model (ollama: qwen2.5:3b, gemini: gemini-3.5-flash,
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
    # Used when the main model stays overloaded ("high demand") after retries; empty = no fallback.
    gemini_fallback_model: str = "gemini-flash-lite-latest"
    # Groq / OpenRouter (OpenAI-style APIs with free plans); used directly or as backups.
    groq_api_key: str = ""
    groq_model: str = ""  # empty = openai/gpt-oss-120b
    openrouter_api_key: str = ""
    openrouter_model: str = ""  # empty = a free NVIDIA Nemotron model (only ":free" models are allowed)
    # Backup providers, tried in order when the main one is used up, overloaded or refuses,
    # e.g. "groq,openrouter". Empty = no backups.
    llm_fallbacks: str = ""

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
    rerank_candidates: int = 24  # fused candidates the re-ranker re-reads (its cost grows with this)
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
    # Free-book finder: Project Gutenberg (its official OPDS catalog feed and downloads).
    catalog_url: str = "https://www.gutenberg.org"

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Accounts ---
    # Sessions live in PostgreSQL; the browser only holds a random token in an HttpOnly cookie.
    session_hours: int = 12  # signed in without "remember me" (renewed while in use)
    remember_days: int = 30  # with "remember me"
    # "auto": Secure cookies when the request came over HTTPS (plain http:// on the LAN can't use them).
    cookie_secure: str = "auto"  # auto | true | false
    password_min_length: int = 10
    reset_token_minutes: int = 30
    verify_token_hours: int = 48
    require_email_verification: bool = False
    # Rate limits (per IP address and per email): attempts per window.
    login_rate_limit: int = 10  # per 15 minutes
    signup_rate_limit: int = 5  # per hour
    reset_rate_limit: int = 5  # per hour
    lockout_after_failures: int = 5  # failed logins in a row before the account is briefly locked
    # Email: "console" prints messages (reset links...) to the backend's terminal; "smtp" sends them.
    email_backend: str = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "BookMind <no-reply@localhost>"
    smtp_tls: bool = True
    app_base_url: str = ""  # links in emails; empty = the address the request came to
    # The owner of everything created before accounts existed (and the first admin).
    admin_email: str = "admin@localhost"
    admin_password: str = ""  # empty = set it with scripts/create_admin.py
    # Per-user quotas (0 = unlimited).
    max_books_per_user: int = 50
    daily_message_limit: int = 300


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    return s
