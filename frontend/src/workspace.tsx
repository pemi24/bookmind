import { createContext, useContext, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Book, ChapterInfo, Job, NewNote, PassageLoc, User } from "./types";

/** Everything a feature panel needs about the open book. */
export interface Workspace {
  book: Book;
  books: Book[];
  chapters: ChapterInfo[];
  /** Spoiler guard: last chapter (position) the reader has read, or null for no limit. */
  maxChapter: number | null;
  openPassage: (loc: PassageLoc) => void;
  saveNote: (note: NewNote) => Promise<void>;
  notify: (msg: string) => void;
  /** The signed-in user (their listening preferences, for one). */
  user: User;
  /** After the account changed (e.g. a voice or speed picked in the reader's player). */
  onUser: (u: User) => void;
}

export const WorkspaceContext = createContext<Workspace | null>(null);

export function useWorkspace(): Workspace {
  const ws = useContext(WorkspaceContext);
  if (!ws) throw new Error("useWorkspace outside WorkspaceContext");
  return ws;
}

export function chapterLabel(chapters: ChapterInfo[], position: number | null | undefined): string {
  if (!position) return "";
  const ch = chapters.find((c) => c.position === position);
  return ch ? ch.title : `Chapter ${position}`;
}

/** Poll a background job until it finishes; calls onDone once when it completes. */
export function useJobPolling(bookId: number, kind: string | null, onDone: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null);
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => {
    if (!kind) return;
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const { job: j } = await api.job(bookId, kind);
        if (!alive) return;
        setJob(j);
        if (j && j.status === "running") timer = window.setTimeout(tick, 1500);
        else if (j) done.current(j);
      } catch {
        if (alive) timer = window.setTimeout(tick, 3000);
      }
    };
    tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [bookId, kind]);

  return job;
}
