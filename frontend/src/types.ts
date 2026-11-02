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
}

export interface ChapterInfo {
  id: number;
  position: number;
  title: string;
  start_page: number | null;
  end_page: number | null;
  chars: number;
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

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  cited: number[];
  pending?: boolean;
  stage?: "searching" | "answering";
  error?: string;
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
  created_at: string | null;
}

export type NewNote = Omit<Note, "id" | "book_id" | "created_at" | "chunk_id" | "message_id" | "title"> & {
  title?: string | null;
  chunk_id?: number | null;
  message_id?: number | null;
};

export interface Health {
  ok: boolean;
  database: { ok: boolean; error: string | null; pgvector: string | null };
  llm: { provider: string; model: string; local: boolean; configured: boolean; ready: boolean; message: string };
  embeddings: { model: string; dim: number; loaded: boolean; error: string | null };
  ocr: { tesseract: boolean };
}
