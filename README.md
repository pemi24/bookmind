# BookMind — chat with any book

Upload a book (PDF, EPUB, DOCX, TXT, Markdown) and ask questions about it. Answers are grounded
only in the book's text, stream in real time, and cite clickable chapter/page sources that open
a reader with the passage highlighted.

* **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2 (async) + Alembic, psycopg 3
* **Database**: PostgreSQL 16+ with **pgvector** — installed natively, no Docker
* **AI**: any of **Ollama** (local, free, fully offline — the default), **Google Gemini**, **Groq**,
  **OpenRouter** or **Anthropic Claude**, selected in `.env`, with optional **backup providers** used
  automatically when one's free quota runs out; local `sentence-transformers` for embeddings and
  re-ranking (free, offline after the first download). **No API key is required.**
* **Frontend**: React + Vite + Tailwind, light/dark mode

How it works: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Features**
* **Accounts** — sign up with an email and password; every account has its own private library
  (books, chats, notes, quizzes, stats). Password reset, optional email verification, "sign out
  everywhere", a **Settings** page (name, email, password, theme, which AI to use), **download all
  your data** as a zip, and **delete your account**. An **Admin** page lists accounts and their
  usage (never their content).
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
* **Conversational, but grounded** — greetings, thanks and "what can you do?" get a friendly reply
  about the book right away (no search); questions unrelated to the book are politely declined with
  example questions; book questions are always answered from retrieved passages only. A quick rule
  check handles obvious messages and a one-word classification by the AI handles the rest
  (uncertain = treated as a book question).
* **Search your library** (the search bar on the Library page) — passages from every book at once, or one answer drawn from all of them.
* **Answer styles** — normal, ELI5, student, expert, analogy.
* **Spoiler guard** — "I've read up to chapter N", or **Follow my reading** to track the furthest
  chapter you've actually read in the reader; enforced in every database query.
* **Talk to a character** (any book: a novel's hero, a figure from history or scripture) and **compare books** (citations from each book).
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
  add it to the home screen, optionally over HTTPS for offline use (see §5).
* **Listen** — chat replies and the book itself read aloud by natural voices that run on your
  computer (Piper, free and offline), your device's own voices, or optional cloud voices. In the
  reader the sentence being read is highlighted and followed; skip by sentence, paragraph or
  chapter, set a sleep timer, and **Continue listening** where you stopped. Works from the lock
  screen and headphone buttons. Pick separate voices for chat and books in **Settings → Listening**
  (see §4).
* Suggested starter questions, dark/light mode, responsive layout, voice input (browser speech
  recognition).

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
A cloud API key (Gemini, Groq, OpenRouter or Anthropic) is optional, only if you prefer a cloud model (§4).

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

### Backup AI providers (free)

Free cloud plans have daily limits (Gemini's free `gemini-3.5-flash`: 20 requests a day). List
backups and BookMind moves to the next one when a quota runs out, a service is overloaded or an
answer is refused — before any text is shown, so answers are never mixed. A used-up daily quota
is skipped until it resets; a "try again in a few seconds" limit is simply waited out.

```ini
LLM_PROVIDER=gemini
LLM_FALLBACKS=groq,openrouter
GROQ_API_KEY=...         # https://console.groq.com/keys  — ~1,000 requests/day, answers in 1-2 s
OPENROUTER_API_KEY=...   # https://openrouter.ai/keys     — free models only (":free"), 50 requests/day
```

Groq's free plan also limits tokens per minute, so BookMind sends it shorter requests (fewer
passages, a shorter book memory). OpenRouter never charges a key whose account has no credits,
and BookMind refuses non-free OpenRouter models. Each provider receives your questions and the book
passages sent with them; check their privacy terms for private books.

### Voices for listening (text-to-speech)

Listening works with no API key. Two kinds of voices are always possible:

* **Piper** — natural neural voices that run on your computer, offline and free. The `piper-tts`
  package is in `requirements.txt` (the start scripts install it); the voices are downloaded once.
* **Your device's own voices** (the browser's speech engine) — nothing to install; BookMind falls
  back to them whenever a server voice can't speak.

Download the Piper voices (about 60 MB each) from the `backend` folder, with its virtual
environment active:

```bash
# Windows
cd backend
.venv\Scripts\activate
python scripts\download_voices.py

# macOS / Linux
cd backend
source .venv/bin/activate
python scripts/download_voices.py
```

That fetches the voices listed in `PIPER_VOICES` into `backend/data/voices`. The defaults are
American (Lessac, female; Ryan, male; Amy, female) and British (Alba, Scottish female; Northern
English, male). To see others — more accents, other languages — and add them:

```bash
python scripts/download_voices.py --list         # English and French voices, with sizes
python scripts/download_voices.py --list de es   # other languages
python scripts/download_voices.py fr_FR-siwis-medium
```
then add the name to `PIPER_VOICES` in `backend/.env` and restart. Prefer **medium** voices: on an
ordinary CPU they synthesize several times faster than real time, while **high** ones can be
slower than real time (reading would stutter). A voice takes a few seconds to load the first
time it's used (the default voice is loaded at start-up); up to `PIPER_MAX_LOADED` stay in memory
(~150 MB each). If `pip install piper-tts` fails on an unusual platform, BookMind still works with
the device's voices.

**Cloud voices (optional).** Each appears in the voice list only when its key is set:
```ini
OPENAI_API_KEY=...        # OpenAI voices (alloy, nova, onyx...), billed per character
ELEVENLABS_API_KEY=...    # your ElevenLabs voices, billed per character
TTS_GOOGLE_ENABLED=true   # Google's Gemini voices, using GEMINI_API_KEY
```
Google voices are off unless you turn them on because they share `GEMINI_API_KEY` with chat:
listening to a book would use up the free chat quota. Cloud voices receive the text being read.

**The audio cache.** Every sentence synthesized on the server is saved under
`backend/data/tts_cache/user-<id>/` (and listed in the `audio_cache` table), keyed by voice, speed
and a hash of the text. Hearing it again — re-reading a page, a voice preview, a reply — plays
at once and doesn't count toward the listening rate limit. Each account has its own entries, so
nobody gets another account's audio, and deleting an account deletes its audio. The cache is
capped by `TTS_CACHE_MAX_MB` (1000 MB, about 50 hours of Piper audio; the least recently played
files go first) and `TTS_CACHE_MAX_AGE_DAYS` (60). Set `TTS_CACHE_ENABLED=false` to turn it off.
Device voices are never cached (the browser speaks them itself). Speech made on the server (Piper,
Google) is sent and saved as MP3 (`TTS_AUDIO_FORMAT=mp3`, `TTS_MP3_BITRATE=40` kbps), about 9x
smaller than WAV and still gapless between sentences; this uses the small `lameenc` package from
`requirements.txt`. Without it, or with `TTS_AUDIO_FORMAT=wav`, clips stay uncompressed WAV
(~6 hours in 1000 MB).

---

## 5. Run

**One command** (installs dependencies on first run, sets up the database, starts both servers and
opens the browser):

* Windows: double-click **`start.bat`** (or run it from a terminal)
* macOS / Linux: `./start.sh` (run `chmod +x start.sh` once)

Then open http://localhost:5173, **create an account**, and upload `samples/alice-in-wonderland.txt`.

### Accounts and signing in

* **New install**: the first page is the sign-in page. Click **Create an account**; each account
  gets its own empty library.
* **Upgrading from a version without accounts**: everything you already had (books, chats, notes…)
  now belongs to the account `ADMIN_EMAIL` (default `admin@localhost`), which has no password yet.
  Set one, then sign in with it and change the email in **Settings** if you like:
  ```bash
  cd backend
  python scripts/create_admin.py                    # asks for the password twice
  python scripts/create_admin.py you@example.com    # or create / promote another address
  ```
  The same command fixes a forgotten admin password.
* **Forgot password**: by default BookMind doesn't send email. Click **Forgot password?**, and the
  reset link is printed in the backend's terminal window (look for the `EMAIL (dev mode…)` box).
  To really send email, set `EMAIL_BACKEND=smtp` and the `SMTP_…` settings (see `.env.example`).
* **Your account** (menu at the bottom of the sidebar → **Settings**): name, email, password, light
  / dark theme, which AI provider and model answer *your* questions (from those the server has keys
  for; the server's backups still apply), signed-in devices, **Download my data**, **Delete account**.
* **Admin** (same menu, admins only): every account with its number of books, storage and chats;
  suspend, reactivate, make admin, delete. Admins can't open other people's books or chats.
* **Limits** per account: `MAX_BOOKS_PER_USER` (50), `DAILY_MESSAGE_LIMIT` (300 questions per 24 h),
  `MAX_UPLOAD_MB` per file. Set any of them to 0 for no limit.
* **Security**: passwords are hashed with argon2; sessions live in PostgreSQL and the browser only
  holds a random token in an HttpOnly cookie (nothing in localStorage), with a CSRF token on every
  change. Repeated wrong passwords are rate-limited and briefly lock the account, and sign-in
  never reveals whether an email has an account. Every query is filtered by the signed-in account
  (other people's items simply don't exist: 404), including the vector and full-text search
  itself, and each account's files are stored in its own folder (`data/uploads/user-<id>/`).

### On your phone (iPhone / Android)

BookMind still runs on your computer; the phone just opens it over your home Wi-Fi.

1. Start it in LAN mode: **`start.bat lan`** (Windows) or **`./start.sh --lan`** (macOS/Linux).
   This builds the app and prints an address such as `http://192.168.1.20:8000`. Inside BookMind,
   **Settings → Use on your phone** shows the same address with a QR code to scan.
2. On the phone (same Wi-Fi), open that address.
   * **iPhone**: in Safari tap **Share → Add to Home Screen**.
   * **Android**: in Chrome tap **⋮ → Add to Home screen** (or **Install app**).
3. Open BookMind from the home-screen icon; it runs full screen like an app.

Notes: the first time, Windows asks whether Python may use the network — allow it for **private
networks**. Anyone on the same Wi-Fi can open BookMind and create an account while LAN mode runs
(they can't see your library, but they can use your AI quota), so only use it on a network you
trust. After an update, refresh the page once on the phone to get the new version. Over plain
`http://` the home-screen app works but needs the computer to be on: phones keep the offline app
shell (the service worker) only on a secure (HTTPS) address, and are stricter about audio there too.
For that, use HTTPS mode below.

#### HTTPS mode (recommended for the installed app)

Start with **`start.bat lan https`** (Windows) or **`./start.sh --lan --https`** (macOS/Linux), or set
`HTTPS=true` in `backend/.env`. BookMind then also answers on **`https://<this computer>:8443`**
(`HTTPS_PORT`); the `http://…:8000` address keeps working. There is no public domain for a real
certificate, so the first start creates a small **local certificate authority** for this computer in
`backend/data/https/` (`ca.key` never leaves the computer) and a server certificate for its network
addresses. The server certificate is renewed automatically (new Wi-Fi address, or yearly) by the
same authority, so each phone trusts it **once**:

1. On the phone, open **`http://<this computer>:8000/bookmind-ca.crt`** — the startup message and
   **Settings → Use on your phone → First time on this phone?** show the exact address and a QR code.
   Before trusting it, you can compare its SHA-256 fingerprint with the one shown there.
2. **iPhone / iPad**: Safari asks to download a configuration profile → **Allow**. Open
   **Settings → Profile Downloaded → Install** (or Settings → General → VPN & Device Management →
   *BookMind local CA* → Install). Then **Settings → General → About → Certificate Trust Settings**
   and turn on full trust for **BookMind local CA**. (Use Safari; other browsers can't install profiles.)
3. **Android**: the file is saved to Downloads. Open **Settings → Security (& privacy) → More security
   settings → Encryption & credentials → Install a certificate → CA certificate** → *Install anyway* →
   pick `BookMind-CA.crt` (search Settings for "CA certificate" if the menus differ). Chrome trusts
   it; Firefox needs *Settings → About Firefox*, tap the logo 5×, then *Secret settings → Use third
   party CA certificates*.
4. Open **`https://<this computer>:8443`** — no warning now — sign in, and add it to the home screen
   (if you installed the `http://` version before, remove that icon and install the https one).

To remove it later: iPhone — Settings → General → VPN & Device Management → *BookMind local CA* →
Remove; Android — Encryption & credentials → User credentials. To start over (new authority,
phones must trust it again), stop BookMind and delete `backend/data/https/`. Prefer
[mkcert](https://github.com/FiloSottile/mkcert)? Set `SSL_CERTFILE` / `SSL_KEYFILE` to its files and
`SSL_CA_FILE` to its `rootCA.pem` (`mkcert -CAROOT`) so the download link serves that instead.
Only trust a certificate you made yourself: whoever holds its `ca.key` could impersonate websites to
that phone, so keep `backend/data/https/` private.

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
oversized uploads, database down, AI model unreachable). Accounts are covered too: sign-up and
sign-in rules, sessions, CSRF, rate limits and lockout, password reset and email verification,
settings, export and account deletion, the admin page, per-account limits, and isolation (a second
account gets 404 from every endpoint for the first account's books, chats, notes and files, and
search never returns another account's passages). Listening is covered by text cleaning for speech
(markdown, citation markers, URLs, emoji), sentence splitting (abbreviations, initials, quotes, very
long chapters), provider selection and fallback, the cloud voices' requests (mocked), the audio
cache (hits, per-account entries, size and age limits), voice preferences, and 404s for other
accounts' chapters and listening positions. A real Piper voice is tested with
`BOOKMIND_TEST_PIPER=1 pytest tests/test_tts.py` (it loads a voice). `stress_large_book.py` runs against
the running backend (start it first); the test book is deleted afterwards.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| Can't sign in after upgrading (your books "disappeared") | They belong to the admin account. Run `python scripts/create_admin.py` in `backend` to give `admin@localhost` a password, then sign in with it. |
| Forgot your password | **Forgot password?** on the sign-in page; the link appears in the backend's terminal unless SMTP is set up. Admins can also run `python scripts/create_admin.py your@email`. |
| "Too many failed sign-in attempts" | Wait up to 15 minutes, then try again (or use **Forgot password?**). |
| "Your session token is missing or out of date" | Reload the page. If it keeps happening, sign out and in again. |
| The phone shows the old version / no sign-in page | Refresh the page once (the installed app caches the previous version). |
| Settings → Listening says "No Piper voices downloaded" | Run `python scripts/download_voices.py` in `backend` (venv active) and restart. Check that `PIPER_VOICES` names voices that are in `backend/data/voices`. |
| "Piper isn't installed" | `pip install piper-tts` in the backend's virtual environment, then restart. Until then, your device's voices read aloud. |
| The first sentence takes a long time with a new voice | Loading a Piper voice takes several seconds (more on a slow CPU); later sentences start at once. The default voice is loaded at start-up; set `TTS_DEFAULT_VOICE` to the one you use most. |
| Reading aloud stutters or pauses between sentences | Use a **medium** Piper voice rather than **high** (it must synthesize faster than it speaks), or lower the speed. |
| "Your saved voice isn't available any more" | That voice was removed (not in `PIPER_VOICES`, or a cloud key was taken out). Pick another in **Settings → Listening**; until then the default voice reads. |
| No device voices in the list | Some browsers (and Linux without speech-dispatcher) have none installed. Use a Piper voice, or install voices in your OS (Windows: Settings → Time & language → Speech). |
| Read-aloud stops when the phone screen locks | Phones may pause web audio in the background; use the lock-screen play button to resume. Installing BookMind to the home screen helps. |
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
| "rate-limiting" / "overloaded" / "free daily quota is used up" | Cloud providers only. Add backups (`LLM_FALLBACKS=groq,openrouter`, §4) and BookMind switches automatically; without backups, Gemini falls back to `GEMINI_FALLBACK_MODEL`. Free daily quotas reset once a day. |
| "Google's content filter stopped this answer" | Gemini's filter occasionally blocks harmless book passages, more often with the lighter fallback model. Rephrase, retry later (when the main model isn't overloaded), or use Ollama / Anthropic. |
| Phone can't open the LAN address | Same Wi-Fi network (not guest Wi-Fi or mobile data)? Allow Python through the firewall for private networks (Windows Security → Firewall → Allow an app). Try the other addresses `start.bat lan` prints. If `backend/.env` sets `HOST`, remove that line. |
| Phone shows "Not private" / "This connection is not private" on the https address | The phone doesn't trust BookMind's certificate yet: follow HTTPS mode steps 1–3 (§5). On iPhone, step 3 (Certificate Trust Settings) is easy to miss. If you deleted `backend/data/https/`, trust the new `bookmind-ca.crt` again. |
| HTTPS worked, now the phone warns again | The computer probably got a new Wi-Fi address while BookMind was running. Restart BookMind: it re-issues the certificate for the new address with the same authority, so nothing needs re-trusting. (A DHCP reservation in your router keeps the address fixed.) |
| `https://…:8443` doesn't load at all | Started with `start.bat lan https` (the startup message lists the https address)? Allow Python through the firewall (port 8443 too). If `backend/.env` sets `HTTPS=false`, remove that line. Change the port with `HTTPS_PORT`. |
| Android: "Install a certificate" refuses the file / asks for a PIN | Android requires a screen lock to install CA certificates; set one. Install from Settings (not by tapping the download). |
| Signed in on https, but the http:// address keeps asking to sign in (or the other way round) | Sign-in cookies over HTTPS are marked Secure and not sent over plain http. Stick to one address per phone — the https one once it's trusted. |
| "Find free books" says a library is busy or slow | That site is temporarily overloaded; the other sources still answer. Try again in a minute (results are cached for an hour). |
| A book I want isn't in "Find free books" | These libraries only carry books that are free to share — mostly books out of copyright (in the US, published before ~1930). Newer books must be uploaded from your own copy. |
| Answers say "the book doesn't say" although it does | BookMind already searches a second time with other wordings. Rephrase with the names the book uses (e.g. "Abram" in Genesis), ask a narrower question, or open the reader's search. For whole-book questions, generating a whole-book summary (Summaries tab) gives the AI an overview to work from. |
| Kindle import: "No Kindle highlights found" | Choose `My Clippings.txt` from the Kindle's `documents` folder (connect it by USB). Highlights from a different edition still import; they just may not show inside the reader text. |
| Translation is slow (Ollama) | Each chapter is translated paragraph by paragraph by your AI model; on a CPU-only laptop a long chapter can take many minutes. It's saved once done. A cloud provider is much faster. |
| Scanned PDF warning | Install Tesseract (Windows: https://github.com/UB-Mannheim/tesseract/wiki, macOS: `brew install tesseract`, Linux: `apt install tesseract-ocr`) and click Re-index. |
| First start is slow | The embedding and re-ranking models (~150 MB) download once into the Hugging Face cache. |
| Backend takes minutes to start / indexing sits at "Loading embedding model" (Windows) | Antivirus real-time scanning of the thousands of files in `backend\.venv` (PyTorch especially) can make imports 10–50× slower. Check with `python -X importtime -c "import app.main"`. If you trust the folder, add `backend\.venv` and `%USERPROFILE%\.cache\huggingface` as Windows Security → Virus & threat protection → Exclusions. |
