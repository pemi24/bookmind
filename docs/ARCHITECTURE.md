# BookMind architecture

```
 Browser (React + Vite + Tailwind)
   │  REST (JSON)  ·  SSE: indexing progress, streamed answers
   ▼
 FastAPI (async, single process)               PostgreSQL 16+ (native) + pgvector
   ├─ api/books.py   upload, library, reader  ─┐   books, chapters, chunks(vector + tsvector)
   ├─ api/chat.py    grounded chat (SSE)       ├─▶ conversations, messages, citations
   ├─ ingestion/     background indexing task  │   notes, summaries, quizzes, flashcards
   ├─ retrieval/     hybrid search + rerank    │   entities, relations, timeline_events
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
