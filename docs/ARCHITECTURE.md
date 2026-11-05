# BookMind architecture

```
 Browser (React + Vite + Tailwind)
   │  REST (JSON)  ·  SSE: indexing progress, streamed answers
   ▼
 FastAPI (async, single process)               PostgreSQL 16+ (native) + pgvector
   ├─ auth/, api/auth.py  accounts, sessions  ─┐   users, sessions, auth_tokens
   ├─ api/books.py   upload, library, reader   │   books, chapters, chunks(vector + tsvector)
   ├─ api/chat.py    grounded chat (SSE)       ├─▶ conversations, messages, citations
   ├─ ingestion/     background indexing task  │   notes, summaries, quizzes, flashcards
   ├─ retrieval/     hybrid search + rerank    │   entities, relations, timeline_events
   ├─ tts/, api/tts.py  voices, read-aloud     │   audio_cache (+ files in data/tts_cache/)
   └─ llm/           provider layer + prompts  ┘
        │  LLM_PROVIDER
        ▼
   Ollama (local, default) │ Gemini │ Anthropic     sentence-transformers (local CPU):
                                                      bge-small embeddings, MiniLM re-ranker
```

## Ingestion (`app/ingestion/`)

Runs as an asyncio background task; CPU work goes to worker threads, so the API and UI stay
responsive. Books are indexed one at a time (others show "Queued"). Progress is written to
`books.progress` / `books.status_message` by a small flusher loop and streamed to the browser by
`GET /api/books/{id}/progress` (SSE).

1. **Parse** (`parsers/`): each format becomes `pages -> paragraphs` plus optional explicit
   headings. PDF: PyMuPDF text blocks, outline (bookmarks) as chapters, Tesseract OCR for image-only
   pages when installed (otherwise a warning). EPUB: spine documents + TOC titles. DOCX: heading
   styles. TXT/MD: blank-line paragraphs, `#` headings. Formats without pages get synthetic
   ~2,000-character pages (`pages_estimated = true`).
2. **Clean** (`cleaning.py`): Unicode NFKC (ligatures), soft hyphens, page-number lines, running
   headers/footers (short lines repeated at the top/bottom of ≥30% of pages), Project Gutenberg
   license header/footer. End-of-line hyphenation is repaired during parsing.
3. **Chapters** (`chapters.py`): explicit headings → regex heading detection ("CHAPTER IV",
   "Part Two", "XII. The End", "Prologue"…) → fixed 15-page sections as a last resort. Tiny sections
   (table-of-contents lines, title pages) are merged into the next chapter. Each chapter keeps its
   cleaned full text plus a `page_map` (`[[char_offset, page], …]`).
4. **Chunk** (`chunking.py`): per chapter, sentence units, ~500 target / 700 max tokens (estimated
   as chars/4), ending at a paragraph break when possible, ~80 tokens of overlap. Each chunk is an
   *exact slice* of the chapter text (`char_start`/`char_end`), which is what makes precise
   highlighting in the reader possible; pages come from the `page_map`.
5. **Embed + store**: batches of 64 go through the embedding provider (chapter title prefixed for
   context) and are inserted into `chunks`. A re-index replaces all chapters/chunks in one
   transaction. Postgres computes `tsv` (`to_tsvector('english', text)`, a generated column).
6. **Profile** (best effort, needs a working model): the LLM classifies fiction/non-fiction and writes
   6–8 suggested starter questions.

## Retrieval (`app/retrieval/hybrid.py`)

For one book:

1. **Vector arm**: `ORDER BY embedding <=> query_vec LIMIT 40` on the HNSW index
   (`vector_cosine_ops`, m=16, ef_construction=64). `hnsw.ef_search=100` and
   `hnsw.iterative_scan=relaxed_order` (pgvector ≥ 0.8) make filtered searches return enough rows.
2. **Keyword arm**: `tsv @@ to_tsquery('english', 'w1 | w2 | …')` ranked by `ts_rank_cd`, on the GIN
   index. OR-semantics so partial matches still rank.
3. **Reciprocal Rank Fusion** (k=60) merges both lists into ≤40 candidates.
4. **Re-rank** with a local cross-encoder (`ms-marco-MiniLM-L-6-v2`); the top 8 go to the LLM.

**Spoiler guard** is a `WHERE chapter_position <= N` in *both* arms, so later passages are never
fetched; the prompt additionally tells the model not to speculate. **Compare mode** retrieves per
book (top 5 each) so every book is represented.

Tune it with `scripts/eval_retrieval.py` (hit@1, hit@k, MRR on sample questions; no LLM cost).

## Answering (`app/api/chat.py`, `app/llm/`)

1. Load the last 10 messages of the conversation (stored in Postgres per book).
2. **Query rewriting**: for follow-ups, the LLM (cloud models) turns "what did he do next?" into a standalone
   search query using the conversation.
3. Retrieve passages (above) and send them to the browser immediately (`sources` event).
4. Prompt = system rules (`prompts/chat.py`: answer only from passages, cite `[n]`, say "I couldn't
   find that in the book" when unsupported; plus style / spoiler / persona / compare rules) +
   history + a user turn containing `<passages>` and the question.
5. Stream tokens to the browser (`delta` events). On completion, parse the `[n]` markers, store the
   assistant message with a snapshot of its sources, and insert `citations` rows for cited chunks.
6. The browser renders `[n]` as chips; clicking one opens the reader at that chapter and highlights
   `char_start..char_end`.

Errors (no key, rate limit, overload, network, refusal) become `error` events with a clear message.
Prompt caching is enabled on the stable prefix (system prompt + history).

## Changing models / dimensions

* LLM: `LLM_MODEL`, `LLM_FAST_MODEL`, `LLM_*_EFFORT` in `.env`.
* Embeddings: providers implement `EmbeddingProvider` in `retrieval/embeddings.py`. The vector
  column's dimension comes from `EMBEDDING_DIM` at migration time and is recorded in `app_meta`;
  the app refuses to start if `.env` disagrees. To switch dimension: create a new database (or write
  a migration that alters `chunks.embedding` and rebuilds the HNSW index), then re-index all books.

## LLM providers (`app/llm/`)

Features never call a model SDK directly. They use `app/llm/client.py` (`stream_text`,
`complete_text`, `complete_json`), which forwards to the `LLMProvider` selected by
`LLM_PROVIDER` (`app/llm/providers/`):

| Provider | Transport | JSON output |
|---|---|---|
| `ollama` (default) | HTTP API on `OLLAMA_HOST`, streamed NDJSON | `format` = JSON Schema (constrained decoding) |
| `gemini` | REST, streamed SSE (`GEMINI_API_KEY`) | `responseMimeType: application/json` |
| `anthropic` | official SDK (`ANTHROPIC_API_KEY`) | native structured outputs |

An `LLMProvider` implements `stream_chat` and a raw JSON call; `generate_json` is shared and
lives in `app/llm/structured.py`: extract the JSON object from the reply (code fences, prose,
trailing commas), coerce sloppy values (enum synonyms like "person" → `character`, "high" → 4),
drop invalid list items instead of failing the whole result, and otherwise re-ask the model
with the validation error (`LLM_JSON_RETRIES`). Every prompt also carries a compact example of
the expected JSON shape.

Providers also expose limits that adapt the pipeline to small local models:
`max_input_chars` (from `OLLAMA_NUM_CTX`) caps how much book text goes into one request
(chapters are split for summaries/analysis, quizzes use fewer passages), `default_top_k`
sends 5 passages to a local model instead of 8, background jobs run one request at a time
locally, follow-up questions use a cheap heuristic instead of an extra model call, and chat
history is trimmed. `check()` reports whether the provider is ready (Ollama running, model
pulled, key present); it runs at startup, in `/api/health`, and in `scripts/check_llm.py`.

To add a provider: subclass `LLMProvider` in `app/llm/providers/`, implement `stream_chat`,
`_json_call` and `check`, and register it in `providers/__init__.py`.

## Reading, library and export features

| Feature | Code | Notes |
|---|---|---|
| Highlights & reading progress | `api/notes.py`, `api/books.py` (`/reading`), migration 0003 | Highlights are notes with a `location` (chapter + char range), `color` and `comment`. Progress stores chapter **positions** (they survive re-indexing). |
| Resend / edit a question | `api/chat.py` (`resend_from`) | Deletes that user message and everything after it, so the old turn never reaches the follow-up history. |
| Second search before "not found" | `api/chat.py` (`_search_again`), `prompts/chat.py` (`admits_gap`), `prompts/query.py` (`ExpandOut`) | When an answer says the passages don't cover the question, the model proposes 3 alternative queries (other names/spellings, the book's vocabulary); new passages go first and the answer is regenerated (`reset` SSE event). The system prompt also carries a book overview (title, author, chapters within the spoiler limit, a cached whole-book summary). |
| Phone address | `app/network.py`, `GET /api/network` | LAN addresses (main interface first) with QR codes (segno), and whether the server listens on the network. |
| Search the whole library | `api/library.py` | `search_books` per ready book with each book's spoiler limit, merged by re-ranker score; `/ask` streams one answer from the top passages. |
| Find free books | `features/catalog.py`, `api/catalog.py` | Three sources searched concurrently (30 s cap each; a failing one is reported, the rest still answer): Project Gutenberg (OPDS search, EPUB/plain text), Standard Ebooks (OPDS search, EPUB), Internet Archive (advanced search limited to `possible-copyright-status:NOT_IN_COPYRIGHT`, not access-restricted, not lending collections; EPUB or OCR text). Downloads rebuild each source's own link from the id, re-check Archive items, and only follow redirects within the source's hosts. Cached 1 h, one retry when busy. |
| Kindle import | `features/kindle.py` | Parses `My Clippings.txt` (any Kindle language), attaches typed notes to their highlight by location, locates each highlight in the text with `TextIndex` (normalise once, exact match, else anchor on first/last words). Re-importing skips duplicates. |
| Anki export | `features/study.py` (`to_anki`) | Anki's plain-text import format with header lines (`#separator:tab`, `#html:true`, `#deck:…`, `#tags column:3`). |
| Essay helper | `features/essay.py`, `llm/prompts/essay.py` | Thesis → outline via `complete_json`; every quote is verified with `find_verbatim` and replaced by the book's own text, unverifiable ones dropped. |
| Side-by-side translation | `features/translate.py`, table `translations` (migration 0004) | Background job per (chapter, language); paragraphs (`text.split("\n\n")`, the reader's split) are translated in numbered batches and stored aligned; missing ones are retried singly, else kept in the original. |
| Reading stats | `features/stats.py`, table `activity_days` | The reader reports active reading time in 15 s ticks (visible page, input in the last 2 min); flashcard reviews are counted per day. Streak = consecutive days with ≥1 min of reading or any review. |
| Install on a phone | `frontend/public/` (manifest, `sw.js`, icons), `main.py` (serves `frontend/dist`) | `start.bat lan` / `./start.sh --lan` build the app and bind to `0.0.0.0`; the backend serves the built app with an SPA fallback. The service worker caches only the app shell, never `/api`. |

## Accounts and data isolation (`app/auth/`, `api/auth.py`, `api/account.py`, `api/admin.py`)

* **Users and sessions** (migration 0005): `users` (argon2 password hash, `settings` JSONB for theme
  and AI choice), `sessions` (SHA-256 of a random token, plus the SHA-256 of a CSRF token) and
  `auth_tokens` (single-use reset / verification links, also stored hashed). The browser gets two
  cookies: `bm_session` (HttpOnly, SameSite=Lax) and `bm_csrf`, which the app echoes in an
  `X-CSRF-Token` header on every POST/PUT/PATCH/DELETE. Signed-out POSTs (sign-in, sign-up, reset)
  must carry `X-Requested-With: BookMind`, which a cross-site form can't add.
* **Every route** except `/api/health` and `/api/auth/*` depends on `auth.deps.current_user`
  (routers declare it in `dependencies=`). Ownership checks live in `auth/scope.py` and answer 404,
  never 403, for anything that isn't yours.
* **Ownership in the schema**: `books`, `conversations`, `notes`, `quizzes`, `flashcards`,
  `entities` and `timeline_events` have `user_id` (NOT NULL from migration 0006, ON DELETE
  CASCADE); everything else is owned through its book. A `bookmind_set_owner` trigger fills the
  owner of child rows from their book and rejects a mismatch, so background jobs can't create
  rows with the wrong owner.
* **Retrieval** takes a required `user_id` and adds `book_id IN (the user's books)` to the vector
  and full-text SQL, so another account's passages are never even candidates.
* **AI choice per account**: `auth.deps` puts the user's provider/model in a context variable that
  `llm.providers.current_provider()` reads; background jobs started by a request inherit it. The
  server's `LLM_FALLBACKS` chain still sits behind the user's choice.
* **Files**: uploads go to `data/uploads/user-<id>/`; deleting an account removes its rows (cascade)
  and its files.
* **Abuse limits**: in-memory sliding-window rate limits per IP and per email (`auth/ratelimit.py`),
  a short database-backed lockout after repeated failures, `MAX_BOOKS_PER_USER` and
  `DAILY_MESSAGE_LIMIT`.
* **Upgrading**: migration 0005 creates the admin from `ADMIN_EMAIL` and gives it all existing data;
  `scripts/create_admin.py` sets its password. Both migrations downgrade cleanly.

## Listening / text-to-speech (`app/tts/`, `api/tts.py`, `frontend/src/audio/`)

* **Providers** (`tts/base.py`): `TTSProvider` with `info()` (available? why not? voices),
  `synthesize(text, voice, speed, volume)`, `stream(sentences, ...)` and `supports_streaming`.
  Voice ids are `provider:voice`. `TTS_PROVIDERS` lists the ones to offer; each also needs its own
  setup and is hidden otherwise:
  * `piper.py`: local ONNX voices from `PIPER_VOICES_DIR`. Synthesis runs on a small thread pool
    (ONNX Runtime releases the GIL), so the event loop never waits on it. Voices load on first use
    (seconds), the least recently used is unloaded beyond `PIPER_MAX_LOADED`, and the default voice
    is loaded at start-up.
  * `browser.py`: the browser's Web Speech voices. Listed and spoken by the frontend; always there.
  * `cloud.py`: OpenAI, ElevenLabs and Google (Gemini) over HTTP, only with their keys.
* **Fallback** (`tts/__init__.py`, `Registry.speak`): a missing voice or a failing provider falls
  back to the server's default voice, with a note the app shows; when nothing on the server can
  speak, the API answers 503 with `fallback: "browser"` and the app carries on with device voices.
* **Text** (`tts/text.py`): `clean_for_speech()` strips markdown, citation markers, URLs, code and
  emoji from chat replies; `split_sentences()` returns sentences with character offsets (handling
  abbreviations, initials and quotes, cutting very long sentences at commas). It is linear in the
  text's length, since the reader asks for whole chapters.
* **Playback** is sentence by sentence (`audio/queue.ts`): the app asks for a reply's or a
  chapter's sentences, then each sentence's audio, three ahead of the one playing, so speech
  starts after one sentence and runs without gaps. One `Audio` element is reused, clips are
  freed after playing, and only one thing plays at a time (`claimAudio`). Speed beyond what a
  provider supports is made up by the browser's playback rate; volume is always applied by the
  browser (the server is asked for volume 1.0, which keeps the cache simple).
* **The reader** (`audio/useBookPlayer.ts`, `components/ListenBar.tsx`) gets
  `/api/tts/chapters/{id}/sentences` (offsets and paragraph starts) and highlights the sentence being
  read with the CSS Custom Highlight API: a `Range` over the existing text nodes, so a long chapter
  is never re-rendered (a `<mark>` range is the fallback). The next chapter's sentences are
  queued a few sentences before the end. The listening position (`books.listen_position/offset`,
  migration 0007) is saved every few seconds and on pause; it is separate from the reading
  bookmark. Media Session handlers give lock-screen and headphone controls.
* **Cache** (`tts/cache.py`, migration 0008): `audio_cache` rows (user, provider, voice, speed,
  sha256 of the text, size, file path, last played) with the audio in
  `TTS_CACHE_DIR/user-<id>/`. A hit is served without synthesis and without counting toward
  `TTS_RATE_LIMIT`. Entries are per user (rows cascade with the account, files are deleted with
  it). `prune()` runs at start-up and whenever enough new audio was written: entries unused for
  `TTS_CACHE_MAX_AGE_DAYS`, then the least recently played until under 90% of `TTS_CACHE_MAX_MB`.
* **Audio format** (`tts/encode.py`): Piper and Google return raw 16-bit PCM; `pcm_audio()` turns
  it into CBR MP3 with `lameenc` (`TTS_AUDIO_FORMAT=mp3`, `TTS_MP3_BITRATE`, default 40 kbps:
  ~5 KB/s instead of WAV's ~44 KB/s), or WAV when lameenc is missing or `TTS_AUDIO_FORMAT=wav`.
  It runs on Piper's thread pool (Google: `asyncio.to_thread`), a few ms per sentence. An MP3
  encoder adds silence at both ends of each clip (576 samples of encoder delay, padding to a whole
  frame: 50-70 ms per sentence at 22 kHz); each file therefore starts with a LAME "Info" frame
  recording the exact delay and padding, which browsers use to drop it (measured in Chromium:
  decoded length equals the PCM length, and the silences between sentences match WAV). Cached
  entries keep their own MIME type, so WAV files saved earlier still play.
* **Preferences** (chat voice, reading voice, speed, pitch, volume, auto-read) live in
  `users.settings`. Every TTS endpoint requires sign-in; chapters and listening positions of other
  accounts' books answer 404. `TTS_MAX_CHARS` bounds a synthesis request.
