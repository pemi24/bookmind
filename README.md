# BookMind — chat with any book

Upload a book (PDF, EPUB, DOCX, TXT, Markdown) and ask questions about it. Answers are grounded
only in the book's text, stream in real time, and cite clickable chapter/page sources that open
a reader with the passage highlighted.

* **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2 (async) + Alembic, psycopg 3
* **Database**: PostgreSQL 16+ with **pgvector** — installed natively, no Docker
* **AI**: any of **Ollama** (local, free, fully offline — the default), **Google Gemini** or
  **Anthropic Claude**, selected in `.env`; local `sentence-transformers` for embeddings and
  re-ranking (free, offline after the first download). **No API key is required.**
* **Frontend**: React + Vite + Tailwind, light/dark mode

How it works: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Features**
* **Library** — upload several books (drag and drop), live indexing progress, re-index, delete.
* **Find free books** — search **Project Gutenberg**, **Standard Ebooks** (carefully edited editions)
  and **Internet Archive** at once and add a book in a click; results are labelled by source and
  one busy site doesn't stop the others. Internet Archive results are limited to items the Archive
  itself marks as out of copyright and not loan-only.
* **Grounded chat** — hybrid search (pgvector + full-text, re-ranked), streamed answers whose
  sources stay tucked away until you click **Sources**; each citation opens the **reader** at the
  highlighted passage. Follow-ups, saved history, and **edit / resend / retry** for any question.
  Before answering "the book doesn't say", BookMind searches again with other wordings (other
  names, the book's own vocabulary) and answers from what that finds.
* **Search your library** — passages from every book at once, or one answer drawn from all of them.
* **Answer styles** — normal, ELI5, student, expert, analogy.
* **Spoiler guard** — "I've read up to chapter N", or **Follow my reading** to track the furthest
  chapter you've actually read in the reader; enforced in every database query.
* **Talk to a character** (fiction) and **compare books** (citations from each book).
* **Summaries** — short / medium / detailed, per chapter or whole book.
* **Study** — generated quizzes (multiple choice, true/false, short answer) with scoring,
  explanations and source links; flashcards with spaced repetition (SM-2), **exportable to Anki**.
* **Essay helper** — give a thesis, get an outline (sections, counter-argument, conclusion) backed
  by quotes that are checked word for word against the book; export to Markdown or save to notes.
* **Explore** — characters, places, terms and themes with a relationship graph (fiction) or
  concept map (non-fiction); **Timeline** of key events.
* **Quote finder** — verbatim quotes about a topic (each verified against the text), copy/share.
* **Notes & highlights** — save answers, quotes or reader highlights, tag them, export to
  Markdown or PDF. **Import Kindle highlights** (and the notes you typed on them) from a Kindle's
  `My Clippings.txt`.
* **Reader** — full text with search, page markers and font size. Select text to highlight it
  in one of four colours and add your own note; highlights stay drawn in the text (click one to
  edit or delete it). **Side-by-side translation** into any language, chapter by chapter (saved
  once translated).
* **Reading progress** — resumes at the paragraph where you stopped; the library shows how far
  you've got, with a "Start over" option. Jumping to a cited passage never moves your bookmark.
* **Reading stats** — time read per day, streaks, books finished, quiz scores, flashcard progress.
* **Install on your phone** — open BookMind from an iPhone or Android phone on the same Wi-Fi and
  add it to the home screen (see §5).
* Suggested starter questions, dark/light mode, responsive layout, voice input and read-aloud
  (browser speech APIs).

---

## 1. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.11 – 3.13 | `python --version` |
| Node.js | 20.19+ or 22.12+ | `node --version` |
| PostgreSQL | 16, 17 or 18 | see below |
| pgvector | 0.8+ | see below |
| Ollama | 0.5+ | `ollama --version` (see §3) |
| Tesseract OCR | optional | only for scanned PDFs |

About 2 GB of disk for Python packages (PyTorch, CPU-only), ~150 MB for the embedding models
(downloaded once on first start) and 2–5 GB for an Ollama model.
A Gemini or Anthropic API key is optional, only if you prefer a cloud model (§3).

---

## 2. Install PostgreSQL + pgvector

### Windows

1. **PostgreSQL**: download the installer from https://www.postgresql.org/download/windows/
   (EDB). Keep the default port **5432**, remember the password you set for the `postgres` user.
   Stack Builder at the end is optional.
2. **pgvector** must be compiled for *your* PostgreSQL version:
   1. Install **Visual Studio 2022 Build Tools** (https://visualstudio.microsoft.com/visual-cpp-build-tools/)
      with the **"Desktop development with C++"** workload.
   2. Open **"x64 Native Tools Command Prompt for VS 2022"** *as Administrator* (Start menu → right-click
      → Run as administrator).
   3. Run (replace `18` with your PostgreSQL major version):
      ```bat
      set "PGROOT=C:\Program Files\PostgreSQL\18"
      cd %TEMP%
      git clone --branch v0.8.1 https://github.com/pgvector/pgvector.git
      cd pgvector
      nmake /F Makefile.win
      nmake /F Makefile.win install
      ```
   **Common Windows pitfalls**
   * Using the plain or *x86* developer prompt → `LNK1112: module machine type 'x64' conflicts…`. Use the
     **x64** Native Tools prompt.
   * Not running as Administrator → `Access is denied` when copying into `Program Files`.
   * `PGROOT` pointing at a different PostgreSQL version than the running server → `could not load
     library "vector.dll"`. Rebuild with the right path (`nmake /F Makefile.win clean` first).
   * `nmake` not found → you are not in the Native Tools prompt.
   * `psql` is not on PATH by default: use `"C:\Program Files\PostgreSQL\18\bin\psql.exe"` or add
     that folder to PATH.

### macOS (Homebrew)

```bash
brew install postgresql@17 pgvector
brew services start postgresql@17
```
Homebrew's `pgvector` formula targets Homebrew's PostgreSQL versions; if `CREATE EXTENSION vector`
says it is not available, build from source instead:
`git clone --branch v0.8.1 https://github.com/pgvector/pgvector.git && cd pgvector && make && make install`
(with the right `pg_config` first on your PATH, e.g. `export PATH="$(brew --prefix postgresql@17)/bin:$PATH"`).

Homebrew creates a superuser named after your macOS user with no password. Either use that in
`DATABASE_URL` (`postgresql+psycopg://YOURNAME@localhost:5432/bookmind`) or create a password user
(next section).

### Linux (Debian / Ubuntu)

```bash
sudo apt install -y postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh   # official PGDG repo (newer versions)
sudo apt install -y postgresql-17 postgresql-17-pgvector
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'choose-a-password';"
```
Fedora/RHEL: `sudo dnf install postgresql-server pgvector` (or the PGDG repo), then
`sudo postgresql-setup --initdb && sudo systemctl enable --now postgresql`.

### Create a database user (optional, recommended)

You can use the `postgres` superuser on a personal laptop. To use a dedicated user instead:
```sql
-- psql -U postgres
CREATE USER bookmind WITH PASSWORD 'choose-a-password';
CREATE DATABASE bookmind OWNER bookmind;
\c bookmind
CREATE EXTENSION IF NOT EXISTS vector;   -- needs a superuser the first time
```

### Verify pgvector

```bash
psql -U postgres -h localhost -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname='vector'; SELECT '[1,2,3]'::vector <=> '[1,2,4]'::vector;"
```
You should see a version (e.g. `0.8.1`) and a small distance (~0.0085). The setup script below runs
the same check.

---

## 3. Install the AI model (Ollama — local, free, no API key)

[Ollama](https://ollama.com) runs open models on your own machine. It installs natively (no
Docker) and serves an API on `http://127.0.0.1:11434`.

**Windows** — download and run `OllamaSetup.exe` from https://ollama.com/download. It starts
automatically in the background (tray icon) and on every login.

**macOS** — download the app from https://ollama.com/download (or `brew install ollama` and then
`brew services start ollama`).

**Linux**
```bash
curl -fsSL https://ollama.com/install.sh | sh     # installs a systemd service
sudo systemctl enable --now ollama
```

**Pull a model** (once; needs internet only for this download):
```bash
ollama pull qwen2.5:3b
```

| Your RAM | Suggested `LLM_MODEL` | Download |
|---|---|---|
| 8 GB | `qwen2.5:3b` (default) or `llama3.2:3b` | ~2 GB |
| 16 GB | `llama3.1:8b` or `qwen2.5:7b` | ~5 GB |
| 32 GB+ / GPU | `qwen2.5:14b` | ~9 GB |

Larger models write better answers and more reliable JSON (quizzes, explorer) but are slower on a
CPU. Without a GPU, expect a few seconds before the first word and a few words per second.

**Verify:**
```bash
ollama list                                   # the model should be listed
curl http://127.0.0.1:11434/api/tags          # Ollama answers
cd backend && python scripts/check_llm.py     # BookMind's own check
```
BookMind also checks this at startup, prints a clear warning in the backend window, and shows a
banner in the app until Ollama is running and the model is pulled (no restart needed).

**Cloud models instead (optional).** Set in `backend/.env`:
```ini
LLM_PROVIDER=gemini          # key: https://aistudio.google.com/apikey
GEMINI_API_KEY=...
# or
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
```

---

## 4. Configure

```bash
cp backend/.env.example backend/.env      # Windows: copy backend\.env.example backend\.env
```
Edit `backend/.env`:
```ini
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/bookmind
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:3b
```
URL-encode special characters in the password (`@`→`%40`, `:`→`%3A`, `/`→`%2F`, `#`→`%23`).
All other settings (context size, chunk sizes, retrieval depth, upload limit) are optional; see
`.env.example`. Values in `backend/.env` take precedence over variables set in your shell.

Everything runs offline once the embedding models (first start) and the Ollama model are
downloaded.

---

## 5. Run

**One command** (installs dependencies on first run, sets up the database, starts both servers and
opens the browser):

* Windows: double-click **`start.bat`** (or run it from a terminal)
* macOS / Linux: `./start.sh` (run `chmod +x start.sh` once)

Then open http://localhost:5173 and upload `samples/alice-in-wonderland.txt`.

### On your phone (iPhone / Android)

BookMind still runs on your computer; the phone just opens it over your home Wi-Fi.

1. Start it in LAN mode: **`start.bat lan`** (Windows) or **`./start.sh --lan`** (macOS/Linux).
   This builds the app and prints an address such as `http://192.168.1.20:8000`. Inside BookMind,
   **Use on your phone** (bottom of the sidebar) shows the same address with a QR code to scan.
2. On the phone (same Wi-Fi), open that address.
   * **iPhone**: in Safari tap **Share → Add to Home Screen**.
   * **Android**: in Chrome tap **⋮ → Add to Home screen** (or **Install app**).
3. Open BookMind from the home-screen icon; it runs full screen like an app.

Notes: the first time, Windows asks whether Python may use the network — allow it for **private
networks**. Anyone on the same Wi-Fi can open your library while LAN mode runs, so only use it on
a network you trust. Browsers only enable offline caching (the service worker) over HTTPS or on
the computer itself; over plain `http://` the home-screen app works but needs the computer to be on.

### Manual steps (what the scripts do)

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_db.py          # creates DB, enables pgvector, runs `alembic upgrade head`
python run.py                       # API on http://127.0.0.1:8000  (docs: /docs)

cd ../frontend
npm install
npm run dev                         # UI on http://localhost:5173
```
`python scripts/setup_db.py --check` only verifies the connection and pgvector.
Always start the API with `python run.py` (not bare `uvicorn`) — on Windows it selects the event
loop that psycopg's async driver requires.

---

## 6. Sample books

`samples/` contains public-domain books from Project Gutenberg:
* `alice-in-wonderland.txt` / `.epub` — Lewis Carroll (fiction, 12 chapters)
* `the-art-of-war.txt` — Sun Tzu, tr. Lionel Giles (non-fiction; useful for cross-book comparison)

---

## 7. Tests and evaluation

```bash
cd backend
pytest                                   # all tests (needs PostgreSQL; creates a bookmind_test DB)
python scripts/eval_retrieval.py         # retrieval quality on Alice: hit@1, hit@k, MRR (no LLM calls)
python scripts/check_llm.py              # is the AI model ready? (Ollama running, model pulled)
python scripts/stress_large_book.py      # index a generated 1,000-page PDF, measure API responsiveness
```
The test suite needs no AI model, API key or network: features are tested with a scripted
fake model, and the Ollama/Gemini providers against mocked HTTP. It covers parsing (TXT, EPUB,
DOCX, Markdown, PDF headers/footers), chunking, hybrid retrieval and the spoiler guard, every
feature endpoint, JSON validation and retries, and error handling (corrupt or scanned files,
oversized uploads, database down, AI model unreachable). `stress_large_book.py` runs against
the running backend (start it first); the test book is deleted afterwards.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `password authentication failed for user` | Wrong password in `DATABASE_URL`, or special characters not URL-encoded. |
| `fe_sendauth: no password supplied` | `DATABASE_URL` has no password; add one. |
| `connection refused` / `could not connect to server` | PostgreSQL isn't running. Windows: `services.msc` → `postgresql-x64-NN` → Start. macOS: `brew services start postgresql@17`. Linux: `sudo systemctl start postgresql`. Check the port (`port` in `postgresql.conf`). |
| `extension "vector" is not available` / `could not open extension control file …vector.control` | pgvector isn't installed for *this* server version. Reinstall/rebuild it against the right PostgreSQL (see §2). |
| `could not load library "…vector.dll"` (Windows) | Built for a different PostgreSQL version or architecture. Rebuild from the **x64** Native Tools prompt with the correct `PGROOT`. |
| `permission denied to create extension "vector"` | Run `CREATE EXTENSION vector;` once as `postgres` in the `bookmind` database; afterwards a normal user is fine. |
| `database "bookmind" does not exist` | Run `python scripts/setup_db.py`. |
| `relation "books" does not exist` | Migrations not applied: `cd backend && alembic upgrade head`. |
| `Database was migrated with EMBEDDING_DIM=…` | You changed `EMBEDDING_DIM` after setup. Restore it, or create a fresh database and re-index. |
| Backend crashes on Windows with `ProactorEventLoop` / `Psycopg cannot use the 'ProactorEventLoop'` | Start with `python run.py`, not `uvicorn ...`. |
| `type "vector" does not exist` during migration | The extension wasn't created in *this* database; `setup_db.py` does it, or run `CREATE EXTENSION vector;` in it. |
| "Ollama isn't running at http://127.0.0.1:11434" | Start Ollama: Windows/macOS — open the Ollama app (tray/menu-bar icon); Linux — `sudo systemctl start ollama`, or run `ollama serve` in a terminal. Check with `curl http://127.0.0.1:11434/api/tags`. If it runs elsewhere, set `OLLAMA_HOST`. |
| "The model 'X' isn't downloaded… Run: ollama pull X" | Run that command (`ollama list` shows what you have), or set `LLM_MODEL` to a model you already pulled. |
| "Ollama ran out of memory" / the PC freezes while answering | Use a smaller model (`LLM_MODEL=qwen2.5:1.5b` or `llama3.2:3b`) or lower `OLLAMA_NUM_CTX` (e.g. 4096). Close other heavy apps. |
| Answers are very slow with Ollama | Normal on a CPU-only laptop for the first answer (the model loads) — later ones are faster (`OLLAMA_KEEP_ALIVE` keeps it loaded). Use a smaller model, or a cloud provider. |
| "The AI model kept returning malformed data" (quizzes, explorer) | Small models occasionally fail structured output even after retries. Try again, raise `LLM_JSON_RETRIES`, or use a bigger model. |
| Answers have no `[1]` citation chips | Small models sometimes forget to cite; the passages used are still shown under the answer. A larger model cites more reliably. |
| "GEMINI_API_KEY is not set" / "ANTHROPIC_API_KEY is not set" | Only when `LLM_PROVIDER` is `gemini`/`anthropic`: add the key to `backend/.env` and restart the backend — or switch back to `LLM_PROVIDER=ollama`. |
| "Gemini model '…' is unavailable" | Google retires older models (often for new API keys first). Set `LLM_MODEL` in `backend/.env` to a current one from https://ai.google.dev/gemini-api/docs/models and restart the backend. |
| "rate-limiting" / "overloaded" messages | Cloud providers only; temporary — wait and retry. Gemini requests are retried automatically and then switch to `GEMINI_FALLBACK_MODEL` (default `gemini-flash-lite-latest`). |
| "Google's content filter stopped this answer" | Gemini's filter occasionally blocks harmless book passages, more often with the lighter fallback model. Rephrase, retry later (when the main model isn't overloaded), or use Ollama / Anthropic. |
| Phone can't open the LAN address | Same Wi-Fi network (not guest Wi-Fi or mobile data)? Allow Python through the firewall for private networks (Windows Security → Firewall → Allow an app). Try the other addresses `start.bat lan` prints. If `backend/.env` sets `HOST`, remove that line. |
| "Find free books" says a library is busy or slow | That site is temporarily overloaded; the other sources still answer. Try again in a minute (results are cached for an hour). |
| A book I want isn't in "Find free books" | These libraries only carry books that are free to share — mostly books out of copyright (in the US, published before ~1930). Newer books must be uploaded from your own copy. |
| Answers say "the book doesn't say" although it does | BookMind already searches a second time with other wordings. Rephrase with the names the book uses (e.g. "Abram" in Genesis), ask a narrower question, or open the reader's search. For whole-book questions, generating a whole-book summary (Summaries tab) gives the AI an overview to work from. |
| Kindle import: "No Kindle highlights found" | Choose `My Clippings.txt` from the Kindle's `documents` folder (connect it by USB). Highlights from a different edition still import; they just may not show inside the reader text. |
| Translation is slow (Ollama) | Each chapter is translated paragraph by paragraph by your AI model; on a CPU-only laptop a long chapter can take many minutes. It's saved once done. A cloud provider is much faster. |
| Scanned PDF warning | Install Tesseract (Windows: https://github.com/UB-Mannheim/tesseract/wiki, macOS: `brew install tesseract`, Linux: `apt install tesseract-ocr`) and click Re-index. |
| First start is slow | The embedding and re-ranking models (~150 MB) download once into the Hugging Face cache. |
| Backend takes minutes to start / indexing sits at "Loading embedding model" (Windows) | Antivirus real-time scanning of the thousands of files in `backend\.venv` (PyTorch especially) can make imports 10–50× slower. Check with `python -X importtime -c "import app.main"`. If you trust the folder, add `backend\.venv` and `%USERPROFILE%\.cache\huggingface` as Windows Security → Virus & threat protection → Exclusions. |
