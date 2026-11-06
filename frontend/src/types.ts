export type BookStatus = "pending" | "processing" | "ready" | "failed";

export interface Book {
  id: number;
  title: string;
  author: string | null;
  filename: string;
  file_type: string;
  file_size: number;
  page_count: number | null;
  pages_estimated: boolean;
  is_fiction: boolean | null;
  status: BookStatus;
  progress: number;
  status_message: string | null;
  error: string | null;
  warnings: string[];
  suggested_questions: string[];
  created_at: string;
  indexed_at: string | null;
  chapter_count: number | null;
  reading: Reading | null;
  listening: Listening | null; // where read-aloud stopped
  verse_mode: "auto" | "off"; // look for chapters and verses when indexing
  verses: VerseSummary | null; // what was found; null when the book has no verse structure
}

/** A book with chapters and verses (a Bible, the Quran...): what indexing found. */
export interface VerseSummary {
  sections: number; // books of the Bible, surahs...
  chapters: number;
  verses: number;
  summary: string; // "Detected 66 books, 1,189 chapters, 31,102 verses"
}

/** Where the reader stopped. Positions are chapter positions; furthest = furthest chapter actually read. */
export interface Reading {
  position: number;
  offset: number;
  furthest: number | null;
  updated_at: string | null;
}

export interface Listening {
  position: number; // chapter position
  offset: number; // char offset of the sentence
  updated_at: string | null;
}

export interface ChapterInfo {
  id: number;
  position: number;
  title: string;
  start_page: number | null;
  end_page: number | null;
  chars: number;
  section: string | null; // books with verses: "Genesis"
  number: number | null; // and the chapter number in it
}

export interface ChapterText {
  id: number;
  book_id: number;
  position: number;
  title: string;
  text: string;
  page_map: [number, number][];
}

export interface Source {
  marker: number;
  chunk_id: number;
  book_id: number;
  book_title: string;
  chapter_id: number;
  chapter_position: number;
  chapter_title: string;
  page_start: number | null;
  page_end: number | null;
  char_start: number;
  char_end: number;
  score: number;
  text: string;
}

/** Where a streamed answer is: searching, a second search with other wordings, or writing. */
export type AnswerStage = "searching" | "searching_more" | "answering";

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  cited: number[];
  pending?: boolean;
  stage?: AnswerStage;
  error?: string;
}

export type Theme = "system" | "light" | "dark";

export interface User {
  id: number;
  email: string;
  display_name: string;
  is_admin: boolean;
  email_verified: boolean;
  settings: {
    theme?: Theme;
    llm_provider?: string;
    llm_model?: string;
    // listening: "provider:voice" ids ("" = the server's default voice)
    tts_chat_voice?: string;
    tts_read_voice?: string;
    tts_speed?: number;
    tts_pitch?: number; // browser voices only
    tts_volume?: number;
    tts_auto_read?: boolean;
  };
  created_at: string | null;
}

export interface ConversationSummary {
  id: number;
  title: string;
  mode: string;
  persona: string | null;
  book_ids: number[];
  updated_at: string;
}

export interface SearchHit {
  chapter_id: number;
  chapter_position: number;
  chapter_title: string;
  start: number;
  end: number;
  page: number | null;
  before: string;
  match: string;
  after: string;
}

export type Style ="default" | "eli5" | "student" | "expert" | "analogy";

/** A location in the book the reader can open and highlight. */
export interface PassageLoc {
  book_id?: number;
  chapter_id: number;
  char_start?: number;
  char_end?: number;
}

export interface Job {
  id: number;
  kind: string;
  status: "running" | "done" | "failed";
  progress: number;
  error: string | null;
  updated_at: string | null;
}

export type Length = "short" | "medium" | "detailed";

export interface SummaryRow {
  id: number;
  chapter_id: number | null;
  length: Length;
  up_to_chapter: number | null;
  content: string;
  created_at: string | null;
}

export type SummaryResult =
  | { status: "done"; summary: SummaryRow }
  | { status: "running" | "failed"; job: Job }
  | { status: "missing" };

export type EntityKind = "character" | "place" | "organization" | "term" | "concept" | "theme";

export interface Entity {
  id: number;
  kind: EntityKind;
  name: string;
  aliases: string[];
  importance: number;
  first_chapter: number | null;
  details: { chapter: number; text: string }[];
  description: string;
}

export interface Relation {
  id: number;
  source: number;
  target: number;
  relation: string;
  description: string;
  first_chapter: number | null;
}

export interface Mention {
  chunk_id: number;
  chapter_id: number;
  chapter_position: number;
  chapter_title: string;
  page_start: number | null;
  char_start: number;
  char_end: number;
  text: string;
}

export interface TimelineEvent {
  id: number;
  position: number;
  title: string;
  description: string;
  when: string | null;
  chapter_position: number | null;
  importance: number;
  chunk_id: number | null;
  chapter_id: number | null;
  chapter_title: string | null;
  page: number | null;
  char_start: number | null;
  char_end: number | null;
}

export interface Quote {
  quote: string;
  note: string;
  chunk_id: number;
  chapter_id: number;
  chapter_position: number;
  chapter_title: string;
  page: number | null;
  char_start: number;
  char_end: number;
  book_title: string;
}

export type QuestionType = "multiple_choice" | "true_false" | "short_answer";

export interface QuizSummary {
  id: number;
  title: string;
  chapter_id: number | null;
  num_questions: number;
  best_score: number | null;
  attempts: number;
  created_at: string | null;
}

export interface Quiz extends QuizSummary {
  questions: { index: number; type: QuestionType; question: string; options: string[] }[];
}

export interface QuizResult {
  score: number;
  total: number;
  results: {
    index: number;
    given: string;
    answer: string;
    explanation: string;
    correct: boolean;
    feedback: string | null;
    source: { chapter_id: number; chapter_position: number; page: number | null; char_start: number; char_end: number } | null;
  }[];
}

export interface Flashcard {
  id: number;
  front: string;
  back: string;
  chapter_id: number | null;
  ease: number;
  interval_days: number;
  repetitions: number;
  due_at: string | null;
  source: { chapter_id: number; chapter_position: number; page: number | null; char_start: number; char_end: number } | null;
}

export interface Note {
  id: number;
  book_id: number;
  kind: "note" | "answer" | "passage" | "quote";
  title: string | null;
  content: string;
  chunk_id: number | null;
  message_id: number | null;
  location: { chapter_id?: number; chapter_title?: string; page?: number | null; char_start?: number; char_end?: number };
  tags: string[];
  color: HighlightColor | null;
  comment: string | null;
  created_at: string | null;
}

export type HighlightColor = "yellow" | "green" | "blue" | "pink";

/** A book found in a Kindle "My Clippings.txt" file; match = similarity to the open book's title (0-1). */
export interface KindleBook {
  title: string;
  author: string | null;
  highlights: number;
  notes: number;
  match: number;
}

export interface EssayEvidence {
  quote: string;
  explanation: string;
  chunk_id: number;
  chapter_id: number;
  chapter_position: number;
  chapter_title: string;
  page: number | null;
  char_start: number;
  char_end: number;
}

/** Essay helper outline; every quote has been verified word for word against the book. */
export interface Essay {
  title: string;
  thesis: string;
  introduction: string;
  sections: { heading: string; point: string; evidence: EssayEvidence[] }[];
  counterargument: string;
  conclusion: string;
  dropped_quotes: number;
}

/** Side-by-side translation of one chapter. paragraphs align with chapter.text.split("\n\n"). */
export interface TranslationState {
  status: "done" | "running" | "failed" | "none";
  language: string;
  paragraphs?: string[];
  job?: Job | null;
}

export interface Stats {
  today_seconds: number;
  week_seconds: number;
  total_seconds: number;
  streak_days: number;
  best_streak_days: number;
  active_days: number;
  daily: { day: string; seconds: number; cards: number }[];
  books: {
    id: number;
    title: string;
    author: string | null;
    seconds: number;
    chapters: number;
    furthest: number;
    finished: boolean;
    highlights: number;
    last_read: string | null;
  }[];
  books_finished: number;
  quizzes: { attempts: number; average: number | null };
  flashcards: { total: number; due: number; mastered: number; reviews: number };
}

/** Book memory: how many chapters have a summary the AI reads with each question. */
export interface MemoryStatus {
  chapters: number;
  done: number;
  job: Job | null;
}

/** How to open BookMind from a phone or another device on the same network. */
export interface NetworkInfo {
  /** The server listens on the network (started with start.bat lan / start.sh --lan). */
  lan_mode: boolean;
  app_built: boolean;
  port: number;
  addresses: { url: string; qr_svg: string }[];
  /** Optional secure address (start.bat lan https / start.sh --lan --https). */
  https: {
    enabled: boolean;
    port: number;
    addresses: { url: string; qr_svg: string }[];
    /** BookMind's local CA certificate, downloaded over plain http; each phone trusts it once. */
    ca_url: string | null;
    ca_qr_svg: string | null;
    ca_fingerprint: string | null;
  };
}

/** A Project Gutenberg search result. */
export type CatalogSourceKey = "gutenberg" | "standard" | "archive";

/** A free-book search result from one of the sources. */
export interface CatalogBook {
  source: CatalogSourceKey;
  id: string;
  title: string;
  author: string | null;
  cover: string;
  url: string;
}

/** How each source did for a search (a busy or offline source doesn't stop the others). */
export interface CatalogSourceStatus {
  key: CatalogSourceKey;
  name: string;
  count: number;
  error: string | null;
}

export interface KindleResult {
  imported: number;
  located: number;
  duplicates: number;
  notes_attached: number;
  standalone_notes: number;
}

export type NewNote = Omit<Note, "id" | "book_id" | "created_at" | "chunk_id" | "message_id" | "title" | "color" | "comment"> & {
  title?: string | null;
  chunk_id?: number | null;
  message_id?: number | null;
  color?: HighlightColor | null;
  comment?: string | null;
};

export interface Health {
  ok: boolean;
  database: { ok: boolean; error: string | null; pgvector: string | null };
  llm: { provider: string; model: string; local: boolean; configured: boolean; ready: boolean; message: string };
  embeddings: { model: string; dim: number; loaded: boolean; error: string | null };
  ocr: { tesseract: boolean };
}
