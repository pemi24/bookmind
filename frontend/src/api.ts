import type {
  Book,
  CatalogBook,
  ChapterInfo,
  ChapterText,
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
  Mention,
  NewNote,
  Note,
  QuestionType,
  Quiz,
  QuizResult,
  QuizSummary,
  Quote,
  Reading,
  Relation,
  SearchHit,
  Source,
  Stats,
  Style,
  SummaryResult,
  TimelineEvent,
  TranslationState,
} from "./types";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
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
  chapters: (id: number) => request<ChapterInfo[]>(`/api/books/${id}/chapters`),
  chapter: (id: number) => request<ChapterText>(`/api/chapters/${id}`),
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
    const res = await fetch(`/api/books/${bookId}/essay/export`, json("POST", { essay }));
    if (!res.ok) throw new ApiError("Couldn't format the outline.", res.status);
    return res.text();
  },

  // Side-by-side translation
  translation: (chapterId: number, language: string) =>
    request<TranslationState>(`/api/chapters/${chapterId}/translation${qs({ language })}`),
  translate: (chapterId: number, language: string) =>
    request<TranslationState>(`/api/chapters/${chapterId}/translation`, json("POST", { language })),

  // Reading stats
  stats: () => request<Stats>("/api/stats"),
  addReadingTime: (bookId: number, seconds: number) =>
    request<void>(`/api/books/${bookId}/reading/time`, json("POST", { seconds })),

  // Whole-library search
  librarySearch: (body: LibraryQuery) =>
    request<{ query: string; results: Source[] }>("/api/library/search", json("POST", body)),

  // Free books (Project Gutenberg)
  catalogSearch: (q: string, page = 1) =>
    request<{ results: CatalogBook[]; has_more: boolean }>(`/api/catalog/search${qs({ q: q || null, page })}`),
  catalogImport: (gutenbergId: number) => request<Book>("/api/catalog/import", json("POST", { gutenberg_id: gutenbergId })),

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
  onStage?: (stage: "searching" | "answering") => void;
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
    res = await fetch(url, {
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
