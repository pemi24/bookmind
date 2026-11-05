import { useCallback, useEffect, useRef, useState } from "react";
import { tts, type ChapterSentence } from "../api";
import type { ChapterInfo, Listening, User } from "../types";
import { SpeechQueue, type QueueState } from "./queue";
import { resolveVoice, useVoiceCatalog, voicePrefs } from "./voices";

/** One sentence in the reading order, with where it is in the book. */
export interface ReadItem extends ChapterSentence {
  chapterId: number;
  position: number; // chapter position
  title: string;
}

export type SleepTimer = { kind: "off" } | { kind: "time"; until: number } | { kind: "chapter"; chapterId: number };

const SAVE_EVERY_MS = 5000;
const APPEND_WHEN_LEFT = 4; // queue the next chapter this many sentences before the end, so it continues without a gap

/**
 * Reads a book aloud from any sentence, carrying on into the next chapters. Sentences come from the
 * server with offsets into the chapter text, so the reader can highlight the one being read.
 */
export function useBookPlayer({
  bookId,
  bookTitle,
  chapters,
  user,
  saved,
  onShowChapter,
}: {
  bookId: number;
  bookTitle: string;
  chapters: ChapterInfo[];
  user: User;
  saved: Listening | null; // where listening stopped last time
  onShowChapter: (chapterId: number) => void; // reading moved into another chapter
}) {
  const catalog = useVoiceCatalog();
  const prefs = voicePrefs(user);
  const resolved = resolveVoice(catalog, prefs.readVoice);
  const [state, setState] = useState<QueueState | null>(null);
  const [current, setCurrent] = useState<ReadItem | null>(null);
  const [sleep, setSleepState] = useState<SleepTimer>({ kind: "off" });
  const [listening, setListening] = useState<Listening | null>(saved);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const queue = useRef<SpeechQueue | null>(null);
  const items = useRef<ReadItem[]>([]);
  const sentenceCache = useRef(new Map<number, ChapterSentence[]>());
  const appending = useRef<Promise<boolean> | null>(null);
  const lastSaved = useRef(0);
  const run = useRef(0);
  const chapterNow = useRef<number | null>(null); // the chapter of the sentence being read
  const live = useRef({ catalog, resolved, prefs, chapters, onShowChapter, sleep, bookTitle });
  live.current = { catalog, resolved, prefs, chapters, onShowChapter, sleep, bookTitle };

  const sentencesOf = useCallback(async (chapterId: number) => {
    const cached = sentenceCache.current.get(chapterId);
    if (cached) return cached;
    const { sentences } = await tts.chapterSentences(chapterId);
    sentenceCache.current.set(chapterId, sentences);
    return sentences;
  }, []);

  const toItems = (ch: ChapterInfo, sentences: ChapterSentence[]): ReadItem[] =>
    sentences.map((s) => ({ ...s, chapterId: ch.id, position: ch.position, title: ch.title }));

  const save = useCallback(
    (item: ReadItem | null, force = false) => {
      if (!item || (!force && Date.now() - lastSaved.current < SAVE_EVERY_MS)) return;
      lastSaved.current = Date.now();
      tts
        .saveListening(bookId, item.position, item.start)
        .then(setListening)
        .catch(() => {});
    },
    [bookId],
  );

  /** Queue the chapter after the last one queued (skipping empty ones); false at the end of the book. */
  const appendNext = useCallback((): Promise<boolean> => {
    if (appending.current) return appending.current;
    const job = (async () => {
      const list = live.current.chapters;
      const last = items.current[items.current.length - 1];
      let i = list.findIndex((c) => c.id === last?.chapterId);
      while (++i > 0 && i < list.length) {
        const ch = list[i];
        const sentences = await sentencesOf(ch.id).catch(() => [] as ChapterSentence[]);
        if (!sentences.length) continue;
        const more = toItems(ch, sentences);
        items.current.push(...more);
        queue.current?.append(more.map((s) => s.text));
        return true;
      }
      return false;
    })().finally(() => {
      appending.current = null;
    });
    appending.current = job;
    return job;
  }, [sentencesOf]);

  const stop = useCallback(() => {
    run.current++;
    const q = queue.current;
    queue.current = null;
    if (q) {
      save(current, true);
      q.destroy();
    }
    items.current = [];
    setState(null);
    setCurrent(null);
    setPreparing(false);
    setSleepState({ kind: "off" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [save, current]);

  /** Start reading at the first sentence that ends after `offset` in a chapter (or, past its last
   * sentence, e.g. on a closing "* * *", at the next chapter's start). */
  const readFrom = useCallback(
    async (chapterId: number, offset = 0) => {
      const list = live.current.chapters;
      const ch = list.find((c) => c.id === chapterId);
      if (!ch) return;
      const order = (id: number) => list.findIndex((c) => c.id === id);
      const firstFrom = () => items.current.findIndex((s) => (s.chapterId === chapterId ? s.end > offset : order(s.chapterId) > order(chapterId)));
      // Already queued (same or following chapter): jump within the queue, no reload.
      const at = items.current.some((s) => s.chapterId === chapterId) ? firstFrom() : -1;
      if (queue.current && at >= 0) {
        queue.current.seek(at);
        if (queue.current.state.status !== "playing" && queue.current.state.status !== "loading") queue.current.play(at);
        return;
      }
      queue.current?.destroy();
      queue.current = null;
      const mine = ++run.current;
      setError(null);
      setPreparing(true);
      let sentences: ChapterSentence[];
      try {
        sentences = await sentencesOf(chapterId);
      } catch (e) {
        if (mine === run.current) {
          setPreparing(false);
          setError((e as Error).message);
        }
        return;
      }
      if (mine !== run.current) return;
      setPreparing(false);
      items.current = toItems(ch, sentences);
      if (!items.current.length) {
        // nothing to read here (e.g. a title page): start with the next chapter that has text
        if (!(await appendNext()) || mine !== run.current) {
          setError("There's no text to read aloud from here.");
          return;
        }
      }
      let start = firstFrom();
      if (start < 0) {
        // after the chapter's last sentence: carry on with the next chapter
        const queued = items.current.length;
        if (!(await appendNext()) || mine !== run.current) {
          if (mine === run.current) setError("That's the end of the book.");
          return;
        }
        start = queued;
      }
      const { catalog, resolved, prefs, bookTitle } = live.current;
      const first = items.current[start];
      const q = new SpeechQueue(
        items.current.map((s) => s.text),
        {
          catalog,
          voice: resolved.id,
          sound: { rate: prefs.speed, pitch: prefs.pitch, volume: prefs.volume },
          ahead: 3,
          meta: { title: first.title, artist: bookTitle, album: "BookMind" },
          onChange: (s) => {
            if (queue.current !== q) return;
            if (s.status === "idle") {
              // stopped from outside (a chat reply or a preview started playing)
              queue.current = null;
              setState(null);
              setCurrent(null);
              return;
            }
            setState(s);
            if (s.status === "paused" || s.status === "ended") save(items.current[s.index] ?? items.current[items.current.length - 1], true);
          },
          onSentence: (i) => {
            const item = items.current[i];
            if (!item || queue.current !== q) return;
            setCurrent(item);
            if (item.chapterId !== chapterNow.current) {
              // into another chapter (reading on, or a jump)
              chapterNow.current = item.chapterId;
              const { sleep, onShowChapter } = live.current;
              q.setMeta({ title: item.title, artist: live.current.bookTitle, album: "BookMind" });
              onShowChapter(item.chapterId);
              save(item, true);
              if (sleep.kind === "chapter" && sleep.chapterId !== item.chapterId) {
                // sleep timer "end of chapter": stop before the next one starts
                setSleepState({ kind: "off" });
                q.pause();
                return;
              }
            } else {
              save(item);
            }
            if (i >= items.current.length - APPEND_WHEN_LEFT) void appendNext();
          },
          onEnd: () => appendNext(),
        },
      );
      queue.current = q;
      chapterNow.current = first.chapterId;
      setCurrent(first);
      q.play(start);
    },
    [appendNext, save, sentencesOf],
  );

  // Settings changed (here, or in Settings) while reading.
  useEffect(() => {
    queue.current?.setSound({ rate: prefs.speed, pitch: prefs.pitch, volume: prefs.volume });
  }, [prefs.speed, prefs.pitch, prefs.volume]);
  useEffect(() => {
    queue.current?.setVoice(resolved.id);
  }, [resolved.id]);

  // Sleep timer by time.
  useEffect(() => {
    if (sleep.kind !== "time") return;
    const t = window.setTimeout(
      () => {
        queue.current?.pause();
        setSleepState({ kind: "off" });
      },
      Math.max(0, sleep.until - Date.now()),
    );
    return () => window.clearTimeout(t);
  }, [sleep]);

  // Leaving the reader (or the book) stops reading and remembers the place.
  const stopRef = useRef(stop);
  stopRef.current = stop;
  useEffect(() => () => stopRef.current(), []);

  // Where we are in the chapter being read, in sentences.
  const inChapter = current ? items.current.filter((s) => s.chapterId === current.chapterId) : [];
  const chapterProgress = current ? { index: inChapter.indexOf(current), count: inChapter.length } : null;

  const seekBy = (fn: (i: number, list: ReadItem[]) => number) => {
    const q = queue.current;
    if (!q) return;
    const i = fn(q.state.index, items.current);
    if (i >= 0 && i < items.current.length) q.seek(i);
  };

  return {
    state,
    current,
    listening,
    preparing,
    error: error ?? state?.error ?? null,
    notice: state?.notice ?? resolved.notice,
    voice: resolved,
    catalog,
    prefs,
    sleep,
    chapterProgress,
    active: !!state || preparing,
    /** Speed or volume now, before the account has saved it. */
    setSound: (change: { rate?: number; volume?: number }) =>
      queue.current?.setSound({ rate: change.rate ?? prefs.speed, pitch: prefs.pitch, volume: change.volume ?? prefs.volume }),
    readFrom,
    stop,
    toggle: () => queue.current?.toggle(),
    sentence: (d: number) => seekBy((i) => i + d),
    paragraph: (d: number) =>
      seekBy((i, list) => {
        const here = list[i];
        if (!here) return -1;
        const firstOfPara = list.findIndex((s) => s.chapterId === here.chapterId && s.p === here.p);
        if (d < 0) {
          // back: to this paragraph's start, or the one before if already there (and a moment in)
          if (i > firstOfPara) return firstOfPara;
          const before = list[firstOfPara - 1];
          return before ? list.findIndex((s) => s.chapterId === before.chapterId && s.p === before.p) : 0;
        }
        const next = list.findIndex((s, j) => j > i && (s.chapterId !== here.chapterId || s.p !== here.p));
        return next;
      }),
    chapter: (d: number) => {
      const here = current ?? null;
      const list = live.current.chapters;
      const i = list.findIndex((c) => c.id === here?.chapterId);
      const target = list[i + d];
      if (!target) return;
      if (d < 0 && here) {
        // like a music player: back goes to this chapter's start unless already near it
        const firstHere = items.current.findIndex((s) => s.chapterId === here.chapterId);
        const atIndex = queue.current?.state.index ?? 0;
        if (atIndex - firstHere > 2) return void readFrom(here.chapterId, 0);
      }
      live.current.onShowChapter(target.id);
      void readFrom(target.id, 0);
    },
    setSleep: (minutes: number | "chapter" | "off") => {
      if (minutes === "off") setSleepState({ kind: "off" });
      else if (minutes === "chapter") setSleepState(current ? { kind: "chapter", chapterId: current.chapterId } : { kind: "off" });
      else setSleepState({ kind: "time", until: Date.now() + minutes * 60_000 });
    },
  };
}
