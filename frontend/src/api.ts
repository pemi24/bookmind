import type {
  AnswerStage,
  Book,
  CatalogBook,
  CatalogSourceKey,
  CatalogSourceStatus,
  ChapterInfo,
  ChapterText,
  VerseLookup,
  ChatMessage,
  ConversationSummary,
  Entity,
  Essay,
  Flashcard,
  Health,
  HighlightColor,
  Job,
  KindleBook,
  KindleResult,
  Length,
  MemoryStatus,
  Mention,
  NetworkInfo,
  NewNote,
  Note,
  QuestionType,
  Quiz,
  QuizResult,
  QuizSummary,
  Quote,
  Listening,
  Reading,
  Relation,
  SearchHit,
  Source,
  Stats,
  Style,
  SummaryResult,
  TimelineEvent,
  TranslationState,
  User,
} from "./types";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

/* ---------- session: the cookie travels by itself; changes also carry the CSRF token ---------- */
let onSignedOut: (() => void) | null = null;
/** Called when the server says the session is gone (expired, signed out elsewhere). */
export function setSignedOutHandler(fn: (() => void) | null) {
  onSignedOut = fn;
}

function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)bm_csrf=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : "";
}

/** fetch() for BookMind's API: marks the request as coming from the app and adds the CSRF token. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-Requested-With", "BookMind");
  const method = (init.method ?? "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRF-Token", csrfToken());
  const res = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (res.status === 401 && !path.startsWith("/api/auth/")) onSignedOut?.();
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await apiFetch(path, init);
  } catch {
    throw new ApiError("Can't reach the BookMind backend. Is it running (start.bat / start.sh)?", 0);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* not JSON */
    }
    if (res.status === 502 || res.status === 504) detail = "The BookMind backend is not responding. Is it running?";
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const auth = {
  config: () => request<{ password_min_length: number; require_email_verification: boolean }>("/api/auth/config"),
  me: () => request<{ user: User }>("/api/auth/me"),
  signup: (email: string, password: string, display_name: string) =>
    request<{ user: User; verification_required: boolean }>("/api/auth/signup", json("POST", { email, password, display_name })),
  login: (email: string, password: string, remember: boolean) =>
    request<{ user: User }>("/api/auth/login", json("POST", { email, password, remember })),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  logoutAll: () => request<{ ok: boolean }>("/api/auth/logout-all", { method: "POST" }),
  forgot: (email: string) => request<{ ok: boolean; message: string }>("/api/auth/forgot", json("POST", { email })),
  reset: (token: string, password: string) => request<{ ok: boolean }>("/api/auth/reset", json("POST", { token, password })),
  verify: (token: string) => request<{ ok: boolean }>("/api/auth/verify", json("POST", { token })),
  resendVerification: (email: string) => request<{ ok: boolean }>("/api/auth/resend-verification", json("POST", { email })),
};

export interface DeviceSession {
  id: number;
  current: boolean;
  user_agent: string | null;
  ip: string | null;
  created_at: string;
  last_seen_at: string;
}

export interface AiOptions {
  server_default: { name: string; model: string };
  providers: { name: string; default_model: string; local: boolean; available: boolean }[];
}

export interface AdminUser {
  id: number;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_active: boolean;
  email_verified: boolean;
  has_password: boolean;
  created_at: string | null;
  last_seen_at: string | null;
  books: number;
  storage_bytes: number;
  chats: number;
  is_me: boolean;
}

export const account = {
  updateProfile: (display_name: string) => request<{ user: User }>("/api/account/profile", json("PATCH", { display_name })),
  updatePreferences: (prefs: Partial<User["settings"]>) =>
    request<{ user: User }>("/api/account/preferences", json("PATCH", prefs)),
  aiOptions: () => request<AiOptions>("/api/account/ai-options"),
  changeEmail: (email: string, password: string) => request<{ user: User }>("/api/account/email", json("POST", { email, password })),
  changePassword: (current_password: string, new_password: string) =>
    request<{ ok: boolean }>("/api/account/password", json("POST", { current_password, new_password })),
  sessions: () => request<DeviceSession[]>("/api/account/sessions"),
  endSession: (id: number) => request<void>(`/api/account/sessions/${id}`, { method: "DELETE" }),
  exportUrl: "/api/account/export",
  deleteAccount: (password: string) => request<{ ok: boolean }>("/api/account/delete", json("POST", { password })),
};

/* ---------- text-to-speech ---------- */
export interface TtsVoice {
  id: string; // "provider:voice"
  provider: string;
  name: string;
  language: string; // BCP 47, "" when it speaks many
  accent: string;
  gender: string; // female | male | ""
  quality: string;
}

export interface TtsProvider {
  id: string;
  label: string;
  available: boolean;
  reason: string;
  client_side: boolean; // browser voices: listed and played by the browser
  supports_streaming: boolean;
  speed_range: [number, number];
  pitch: boolean;
  volume: boolean;
  voices: TtsVoice[];
}

export interface TtsCatalog {
  providers: TtsProvider[];
  default_voice: string;
  max_chars: number;
}

/** No voice on the server could speak: the app reads with the browser's own voices instead. */
export class TtsUnavailable extends ApiError {}

export interface SpokenAudio {
  blob: Blob;
  voice: string; // the voice that actually spoke
  note: string | null; // why it isn't the one asked for
}

async function fetchAudio(path: string, init: RequestInit = {}): Promise<SpokenAudio> {
  let res: Response;
  try {
    res = await apiFetch(path, init);
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("Can't reach the BookMind backend. Is it running?", 0);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    let fallback = false;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      fallback = body.fallback === "browser";
    } catch {
      /* not JSON */
    }
    throw fallback ? new TtsUnavailable(detail, res.status) : new ApiError(detail, res.status);
  }
  const header = (name: string) => {
    const v = res.headers.get(name);
    return v ? decodeURIComponent(v) : null;
  };
  return { blob: await res.blob(), voice: header("X-TTS-Voice") ?? "", note: header("X-TTS-Note") };
}

export const tts = {
  voices: () => request<TtsCatalog>("/api/tts/voices"),
  /** Speakable sentences; markdown = an AI reply (markdown, citation markers, URLs and emoji removed). */
  sentences: (text: string, markdown = true) => request<{ sentences: string[] }>("/api/tts/sentences", json("POST", { text, markdown })),
  speak: (body: { text: string; voice: string; speed: number; volume?: number }, signal?: AbortSignal) =>
    fetchAudio("/api/tts/speak", { ...json("POST", body), signal }),
  preview: (voice: string, speed: number, signal?: AbortSignal) =>
    fetchAudio(`/api/tts/preview?${new URLSearchParams({ voice, speed: String(speed) })}`, { signal }),
  /** A chapter as sentences, with offsets into its text and each one's paragraph start (`p`). */
  chapterSentences: (chapterId: number) =>
    request<{ chapter_id: number; position: number; title: string; sentences: ChapterSentence[] }>(`/api/tts/chapters/${chapterId}/sentences`),
  saveListening: (bookId: number, position: number, offset: number) =>
    request<Listening>(`/api/tts/books/${bookId}/listening`, json("PUT", { position, offset })),
  clearListening: (bookId: number) => request<void>(`/api/tts/books/${bookId}/listening`, { method: "DELETE" }),
};

export interface ChapterSentence {
  start: number;
  end: number;
  text: string;
  p: number;
  /** Books with verses: "chapter" ("Genesis, chapter 1."), "title" (a psalm's superscription),
   * "verse-number" ("Verse 1.") or "text". start/end then cover the whole verse. */
  kind?: "chapter" | "title" | "verse-number" | "text";
  verse?: number | null;
  verse_end?: number | null;
}

export const admin = {
  users: () => request<AdminUser[]>("/api/admin/users"),
  updateUser: (id: number, change: { is_active?: boolean; is_admin?: boolean }) =>
    request<{ id: number; is_active: boolean; is_admin: boolean }>(`/api/admin/users/${id}`, json("PATCH", change)),
  deleteUser: (id: number) => request<void>(`/api/admin/users/${id}`, { method: "DELETE" }),
};

export const api = {
  health: () => request<Health>("/api/health"),
  books: () => request<Book[]>("/api/books"),
  book: (id: number) => request<Book>(`/api/books/${id}`),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<Book>("/api/books", { method: "POST", body: fd });
  },
  deleteBook: (id: number) => request<void>(`/api/books/${id}`, { method: "DELETE" }),
  reindex: (id: number) => request<{ ok: boolean }>(`/api/books/${id}/reindex`, { method: "POST" }),
  /** Turn chapter-and-verse detection on or off; the book is re-indexed. */
  setVerseMode: (id: number, detect: boolean) =>
    request<{ ok: boolean }>(`/api/books/${id}/verse-mode`, json("PUT", { detect })),
  chapters: (id: number) => request<ChapterInfo[]>(`/api/books/${id}/chapters`),
  chapter: (id: number) => request<ChapterText>(`/api/chapters/${id}`),
  /** Find "John 3:16", "Gen 1:3" or "3:16" (in the book of `fromChapter`) in a book with verses. */
  lookupVerse: (bookId: number, ref: string, fromChapter?: number) =>
    request<VerseLookup>(`/api/books/${bookId}/verses/lookup?ref=${encodeURIComponent(ref)}${fromChapter ? `&from_chapter=${fromChapter}` : ""}`),
  search: (bookId: number, q: string) =>
    request<{ query: string; total: number; results: SearchHit[] }>(
      `/api/books/${bookId}/search?q=${encodeURIComponent(q)}`,
    ),
  conversations: (bookId: number) => request<ConversationSummary[]>(`/api/books/${bookId}/conversations`),
  conversation: (id: number) =>
    request<{ id: number; messages: ChatMessage[]; mode: string; persona: string | null; book_ids: number[] }>(
      `/api/conversations/${id}`,
    ),
  deleteConversation: (id: number) => request<void>(`/api/conversations/${id}`, { method: "DELETE" }),
  renameConversation: (id: number, title: string) => request<{ id: number; title: string }>(`/api/conversations/${id}`, json("PATCH", { title })),

  // Summaries
  summarize: (bookId: number, body: { chapter_id?: number | null; length: Length; max_chapter?: number | null; refresh?: boolean }) =>
    request<SummaryResult>(`/api/books/${bookId}/summaries`, json("POST", body)),
  summary: (bookId: number, p: { chapter_id?: number | null; length: Length; max_chapter?: number | null }) =>
    request<SummaryResult>(`/api/books/${bookId}/summaries${qs(p)}`),

  // Explorer + timeline (book analysis)
  startAnalysis: (bookId: number) => request<Job>(`/api/books/${bookId}/analysis`, { method: "POST" }),
  entities: (bookId: number, maxChapter: number | null) =>
    request<{ job: Job | null; entities: Entity[]; relations: Relation[] }>(
      `/api/books/${bookId}/entities${qs({ max_chapter: maxChapter })}`,
    ),
  mentions: (entityId: number, maxChapter: number | null) =>
    request<Mention[]>(`/api/entities/${entityId}/mentions${qs({ max_chapter: maxChapter })}`),
  timeline: (bookId: number, maxChapter: number | null) =>
    request<{ job: Job | null; events: TimelineEvent[] }>(`/api/books/${bookId}/timeline${qs({ max_chapter: maxChapter })}`),
  job: (bookId: number, kind: string) =>
    request<{ job: Job | null }>(`/api/books/${bookId}/jobs/${encodeURIComponent(kind)}`),

  // Quotes
  quotes: (bookId: number, topic: string, maxChapter: number | null) =>
    request<{ topic: string; quotes: Quote[] }>(`/api/books/${bookId}/quotes`, json("POST", { topic, max_chapter: maxChapter })),

  // Study
  createQuiz: (
    bookId: number,
    body: { chapter_id?: number | null; max_chapter?: number | null; num_questions: number; types: QuestionType[]; difficulty: string },
  ) => request<Quiz>(`/api/books/${bookId}/quizzes`, json("POST", body)),
  quizzes: (bookId: number, maxChapter: number | null) =>
    request<QuizSummary[]>(`/api/books/${bookId}/quizzes${qs({ max_chapter: maxChapter })}`),
  quiz: (id: number, maxChapter: number | null) => request<Quiz>(`/api/quizzes/${id}${qs({ max_chapter: maxChapter })}`),
  submitQuiz: (id: number, answers: (string | null)[]) => request<QuizResult>(`/api/quizzes/${id}/submit`, json("POST", { answers })),
  deleteQuiz: (id: number) => request<void>(`/api/quizzes/${id}`, { method: "DELETE" }),
  createCards: (bookId: number, body: { chapter_id?: number | null; max_chapter?: number | null; count: number }) =>
    request<Flashcard[]>(`/api/books/${bookId}/flashcards`, json("POST", body)),
  cards: (bookId: number, dueOnly = false) =>
    request<{ total: number; due: number; cards: Flashcard[] }>(`/api/books/${bookId}/flashcards${qs({ due_only: dueOnly || null })}`),
  reviewCard: (id: number, grade: "again" | "hard" | "good" | "easy") =>
    request<Flashcard>(`/api/flashcards/${id}/review`, json("POST", { grade })),
  exportCardsUrl: (bookId: number, maxChapter: number | null) => `/api/books/${bookId}/flashcards/export${qs({ max_chapter: maxChapter })}`,
  deleteCard: (id: number) => request<void>(`/api/flashcards/${id}`, { method: "DELETE" }),

  // Notes
  notes: (bookId: number, tag?: string | null) => request<{ notes: Note[]; tags: string[] }>(`/api/books/${bookId}/notes${qs({ tag })}`),
  createNote: (bookId: number, note: NewNote) => request<Note>(`/api/books/${bookId}/notes`, json("POST", note)),
  updateNote: (id: number, patch: { title?: string | null; content?: string; tags?: string[]; color?: HighlightColor; comment?: string }) =>
    request<Note>(`/api/notes/${id}`, json("PATCH", patch)),
  kindlePreview: (bookId: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ books: KindleBook[] }>(`/api/books/${bookId}/kindle/preview`, { method: "POST", body: fd });
  },
  kindleImport: (bookId: number, file: File, kindleTitle: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kindle_title", kindleTitle);
    return request<KindleResult>(`/api/books/${bookId}/kindle/import`, { method: "POST", body: fd });
  },
  highlights: (bookId: number, chapterId: number) => request<Note[]>(`/api/books/${bookId}/highlights${qs({ chapter_id: chapterId })}`),

  // Essay helper
  essay: (bookId: number, body: { thesis: string; max_chapter: number | null; sections: number }) =>
    request<Essay>(`/api/books/${bookId}/essay`, json("POST", body)),
  essayMarkdown: async (bookId: number, essay: Essay): Promise<string> => {
    const res = await apiFetch(`/api/books/${bookId}/essay/export`, json("POST", { essay }));
    if (!res.ok) throw new ApiError("Couldn't format the outline.", res.status);
    return res.text();
  },

  // Side-by-side translation
  translation: (chapterId: number, language: string) =>
    request<TranslationState>(`/api/chapters/${chapterId}/translation${qs({ language })}`),
  translate: (chapterId: number, language: string) =>
    request<TranslationState>(`/api/chapters/${chapterId}/translation`, json("POST", { language })),

  network: () => request<NetworkInfo>("/api/network"),
  memory: (bookId: number) => request<MemoryStatus>(`/api/books/${bookId}/memory`),
  buildMemory: (bookId: number) => request<MemoryStatus>(`/api/books/${bookId}/memory`, { method: "POST" }),

  // Reading stats
  stats: () => request<Stats>("/api/stats"),
  addReadingTime: (bookId: number, seconds: number) =>
    request<void>(`/api/books/${bookId}/reading/time`, json("POST", { seconds })),

  // Whole-library search
  librarySearch: (body: LibraryQuery) =>
    request<{ query: string; results: Source[] }>("/api/library/search", json("POST", body)),

  // Free books (Project Gutenberg)
  catalogSearch: (q: string, page = 1, source: CatalogSourceKey | null = null) =>
    request<{ results: CatalogBook[]; has_more: boolean; sources: CatalogSourceStatus[] }>(
      `/api/catalog/search${qs({ q: q || null, page, sources: source })}`,
    ),
  catalogImport: (b: CatalogBook) =>
    request<Book>("/api/catalog/import", json("POST", { source: b.source, id: b.id, title: b.title, author: b.author })),

  // Reading progress
  saveReading: (bookId: number, body: { position: number; offset: number; reached: boolean }) =>
    request<Reading>(`/api/books/${bookId}/reading`, json("PUT", body)),
  resetReading: (bookId: number) => request<void>(`/api/books/${bookId}/reading`, { method: "DELETE" }),
  deleteNote: (id: number) => request<void>(`/api/notes/${id}`, { method: "DELETE" }),
  exportNotesUrl: (bookId: number, format: "md" | "pdf", tag?: string | null) =>
    `/api/books/${bookId}/notes/export${qs({ format, tag })}`,
};

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== "");
  return entries.length ? "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString() : "";
}

/** Subscribe to indexing progress (SSE). Returns an unsubscribe function. */
export function watchProgress(
  bookId: number,
  onUpdate: (p: { status: string; progress: number; message: string | null; error: string | null }) => void,
): () => void {
  const es = new EventSource(`/api/books/${bookId}/progress`);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    onUpdate(data);
    if (data.status === "ready" || data.status === "failed") es.close();
  };
  es.onerror = () => es.close();
  return () => es.close();
}

export interface ChatHandlers {
  onConversation?: (id: number, userMessageId: number) => void;
  onStage?: (stage: AnswerStage) => void;
  /** The server is replacing a "the book doesn't say" answer after searching again: clear it. */
  onReset?: () => void;
  onSources?: (sources: Source[], query: string) => void;
  onDelta?: (text: string) => void;
  onDone?: (messageId: number, cited: number[]) => void;
  onError?: (message: string) => void;
}

export interface LibraryQuery {
  q: string;
  /** Spoiler guard per book: {book_id: last chapter read}. */
  max_chapters?: Record<number, number>;
  book_ids?: number[];
  style?: Style;
}

export interface ChatParams {
  message: string;
  conversation_id?: number | null;
  style?: Style;
  spoiler_chapter?: number | null;
  persona?: string | null;
  compare_book_ids?: number[];
  /** Replace this user message (and everything after it) instead of appending. */
  resend_from?: number | null;
}

/** POST a question and parse the Server-Sent Events stream of the answer. */
export function streamChat(bookId: number, params: ChatParams, h: ChatHandlers, signal?: AbortSignal) {
  return streamAnswer(`/api/books/${bookId}/chat`, params, h, signal);
}

/** A question answered from the whole library (one-off, not saved). */
export function streamLibraryAnswer(body: LibraryQuery, h: ChatHandlers, signal?: AbortSignal) {
  return streamAnswer("/api/library/ask", body, h, signal);
}

async function streamAnswer(url: string, body: unknown, h: ChatHandlers, signal?: AbortSignal) {
  let res: Response;
  try {
    res = await apiFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    h.onError?.("Can't reach the BookMind backend. Is it running?");
    return;
  }
  if (!res.ok || !res.body) {
    let msg = `Request failed (${res.status})`;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {
      /* ignore */
    }
    h.onError?.(msg);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let event = "message";
        let data = "";
        for (const line of raw.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7);
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        if (!data) continue;
        const d = JSON.parse(data);
        if (event === "conversation") h.onConversation?.(d.id, d.user_message_id);
        else if (event === "status") h.onStage?.(d.stage);
        else if (event === "reset") h.onReset?.();
        else if (event === "sources") h.onSources?.(d.sources, d.query);
        else if (event === "delta") h.onDelta?.(d.text);
        else if (event === "done") h.onDone?.(d.message_id, d.cited);
        else if (event === "error") h.onError?.(d.message);
      }
    }
  } catch (e) {
    if ((e as Error).name !== "AbortError") h.onError?.("The connection was interrupted while answering.");
  }
}
