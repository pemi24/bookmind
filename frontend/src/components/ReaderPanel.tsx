import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Languages, Link2, Loader2, Maximize2, Minimize2, Play, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { ChapterInfo, ChapterText, HighlightColor, Note, Reading, SearchHit, TranslationState, VerseInfo } from "../types";
import { useBookPlayer } from "../audio/useBookPlayer";
import { findLoose, loadPref, savePref } from "../utils";
import { useWorkspace } from "../workspace";
import ListenBar from "./ListenBar";
import VerseNavigator from "./VerseNavigator";
import { buttonClasses } from "./ui";

export interface ReaderTarget {
  chapterId?: number;
  highlight?: { start: number; end: number };
  ref?: string; // books with verses: a reference to look up ("John 3:16"), from a link
  verses?: { start: number; end: number | null }; // books with verses: the verses cited (shown in the verse bar)
  nonce: number; // forces re-scroll when the same passage is clicked again
}

interface Range {
  start: number;
  end: number;
  kind: "cite" | "search" | "search-active" | "user" | "tts" | "verse"; // tts: only where CSS highlights aren't supported
  color?: HighlightColor;
  noteId?: number;
  comment?: string | null;
}

const FONT_SIZES = [15, 17, 19, 22];
const COLORS: HighlightColor[] = ["yellow", "green", "blue", "pink"];
const SWATCH: Record<HighlightColor, string> = {
  yellow: "bg-yellow-300",
  green: "bg-emerald-300",
  blue: "bg-sky-300",
  pink: "bg-pink-300",
};
// A chapter that fits on one screen can't be scrolled; it counts as read after this long.
const SHORT_CHAPTER_READ_MS = 15_000;
// Reading time: counted in ticks while the page is visible and the reader was used recently.
const TICK_SECONDS = 15;
const IDLE_AFTER_MS = 120_000;
const LANGUAGES = [
  "English", "French", "Spanish", "German", "Italian", "Portuguese", "Dutch", "Russian", "Polish", "Turkish",
  "Arabic", "Hindi", "Chinese (Simplified)", "Japanese", "Korean", "Swahili",
];

/**
 * Render chapter text as paragraphs, wrapping highlight ranges in <mark> and inserting
 * page markers at page boundaries. Offsets are character offsets into chapter.text.
 */
function renderChapter(text: string, ranges: Range[], pageMap: [number, number][], translation?: string[], verses?: VerseInfo[]) {
  const marks = pageMap.filter(([o]) => o > 0);
  const verseAt = new Map((verses ?? []).map((v) => [v.start, v]));
  const out: JSX.Element[] = [];
  let offset = 0;
  text.split("\n\n").forEach((para, pi) => {
    const pStart = offset;
    const pEnd = offset + para.length;
    offset = pEnd + 2;

    const inPara = ranges.filter((r) => r.start < pEnd && r.end > pStart);
    const pageMarks = marks.filter(([o]) => o >= pStart && o < pEnd + 2);
    const points = new Set<number>([pStart, pEnd]);
    for (const r of inPara) {
      points.add(Math.max(r.start, pStart));
      points.add(Math.min(r.end, pEnd));
    }
    for (const [o] of pageMarks) points.add(Math.min(Math.max(o, pStart), pEnd));
    const cuts = [...points].sort((a, b) => a - b);

    const children: (JSX.Element | string)[] = [];
    for (let i = 0; i < cuts.length; i++) {
      const a = cuts[i];
      for (const [o, page] of pageMarks) {
        if (Math.min(Math.max(o, pStart), pEnd) === a) {
          children.push(
            <span key={`p${page}`} data-page={page} className="mx-1 inline-block rounded bg-stone-100 px-1.5 align-middle font-sans text-[10px] leading-4 text-stone-400 select-none dark:bg-stone-800 dark:text-stone-500">
              p. {page}
            </span>,
          );
        }
      }
      if (i === cuts.length - 1) break;
      const b = cuts[i + 1];
      if (b <= a) continue;
      const seg = para.slice(a - pStart, b - pStart);
      const cover = inPara.filter((r) => r.start <= a && r.end >= b);
      const cite = cover.find((r) => r.kind === "cite");
      const verse = cover.find((r) => r.kind === "verse");
      const active = cover.find((r) => r.kind === "search-active");
      const search = cover.find((r) => r.kind === "search");
      const user = cover.filter((r) => r.kind === "user").pop(); // newest wins where highlights overlap
      if (cover.some((r) => r.kind === "tts")) {
        children.push(
          <mark key={a} className="tts-hl" data-target="tts">
            {seg}
          </mark>,
        );
      } else if (active || search) {
        children.push(
          <mark key={a} className={active ? "search-hl search-active" : "search-hl"} data-target={active ? "search" : undefined}>
            {seg}
          </mark>,
        );
      } else if (cite) {
        children.push(
          <mark key={a} className="cite-hl" data-target={cite.start >= pStart && a === Math.max(cite.start, pStart) ? "cite" : undefined}>
            {seg}
          </mark>,
        );
      } else if (verse) {
        children.push(
          <mark key={a} className="verse-hl" data-target={a === Math.max(verse.start, pStart) && verse.start >= pStart ? "verse" : undefined}>
            {seg}
          </mark>,
        );
      } else if (user) {
        children.push(
          <mark
            key={a}
            className={`user-hl hl-${user.color ?? "yellow"}${user.comment && b === user.end ? " has-comment" : ""}`}
            data-note={user.noteId}
            title={user.comment ?? "Click to add a note or change the colour"}
          >
            {seg}
          </mark>,
        );
      } else {
        children.push(seg);
      }
    }
    // Books with verses: each verse is a paragraph, numbered (the number isn't part of the text).
    const v = verseAt.get(pStart);
    const original = (
      <p key={pi} data-p={pStart} className={v?.kind === "title" ? "my-[0.9em] text-[0.92em] text-stone-500 italic dark:text-stone-400" : "my-[0.9em]"}>
        {v?.kind === "verse" && (
          <sup
            data-verse-num={v.number}
            className="mr-1 cursor-pointer font-sans text-[0.62em] font-semibold text-brand-600 select-none hover:underline dark:text-brand-300"
            title={`Verse ${v.number}${v.end ? `–${v.end}` : ""}`}
          >
            {v.end ? `${v.number}–${v.end}` : v.number}
          </sup>
        )}
        {children}
      </p>
    );
    // Side by side when the reader is wide enough, else the translation under each paragraph.
    out.push(
      translation ? (
        <div key={pi} className="grid gap-x-8 @2xl:grid-cols-2">
          {original}
          <p className="mb-[0.9em] border-l-2 border-brand-200 pl-3 text-stone-600 @2xl:my-[0.9em] @2xl:border-0 @2xl:pl-0 dark:border-brand-900 dark:text-stone-300">
            {translation[pi] ?? ""}
          </p>
        </div>
      ) : (
        original
      ),
    );
  });
  return out;
}

// The CSS Custom Highlight API paints the sentence being read without re-rendering the chapter.
const CAN_HIGHLIGHT = typeof CSS !== "undefined" && "highlights" in CSS && typeof Highlight !== "undefined";

/** A DOM range over chapter text [start, end) inside the paragraph starting at `p` (page markers and verse numbers skipped). */
function textRange(root: HTMLElement, p: number, start: number, end: number): globalThis.Range | null {
  const para = root.querySelector<HTMLElement>(`p[data-p="${p}"]`);
  if (!para) return null;
  const walker = document.createTreeWalker(para, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement?.closest("[data-page], [data-verse-num]") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  const range = document.createRange();
  let pos = p;
  let started = false;
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const len = n.textContent?.length ?? 0;
    if (!started && start < pos + len) {
      range.setStart(n, Math.max(0, start - pos));
      started = true;
    }
    if (started && end <= pos + len) {
      range.setEnd(n, Math.max(0, end - pos));
      return range;
    }
    pos += len;
  }
  if (!started) return null;
  range.setEndAfter(para.lastChild ?? para);
  return range;
}

function isShortcut(e: { key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean }): boolean {
  return !e.ctrlKey && !e.metaKey && !e.altKey && (e.key === " " || e.key === "ArrowLeft" || e.key === "ArrowRight");
}

function pageAt(pageMap: [number, number][], offset: number): number | null {
  let page: number | null = null;
  for (const [o, p] of pageMap) {
    if (o <= offset) page = p;
    else break;
  }
  return page;
}

export default function ReaderPanel({
  bookId,
  target,
  resume,
  expanded,
  onToggleExpand,
  onClose,
  onReading,
  onNotesChanged,
  notify,
}: {
  bookId: number;
  target: ReaderTarget | null;
  /** Where the reader stopped last time; used when the reader opens without a target passage. */
  resume?: Reading | null;
  expanded: boolean;
  onToggleExpand: () => void;
  onClose: () => void;
  onReading?: (r: Reading) => void;
  onNotesChanged?: () => void;
  notify?: (msg: string) => void;
}) {
  const [selection, setSelection] = useState<{ text: string; near: number; top: number; left: number } | null>(null);
  const [editing, setEditing] = useState<{ note: Note; draft: string; top: number; left: number } | null>(null);
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chapterId, setChapterId] = useState<number | null>(target?.chapterId ?? null);
  const [chapter, setChapter] = useState<ChapterText | null>(null);
  const [highlights, setHighlights] = useState<Note[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [fontIdx, setFontIdx] = useState(() => loadPref("reader:font", 1));
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [total, setTotal] = useState(0);
  const [active, setActive] = useState(0);
  const [showHits, setShowHits] = useState(false);
  const [scrollNonce, setScrollNonce] = useState(0);
  const [fraction, setFraction] = useState(0); // how far through the current chapter
  const [translateTo, setTranslateTo] = useState<string | null>(null);
  const [langPicker, setLangPicker] = useState(false);
  const [translation, setTranslation] = useState<TranslationState | null>(null);
  // Books with verses: the verse chosen in the navigator ("first"/"last" until its chapter loads).
  const [verseSel, setVerseSel] = useState<{
    chapterId: number;
    number: number | "first" | "last";
    last?: number | null; // a range of verses ("John 3:16–21", a cited passage)
    span?: { start: number; end: number };
  } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const { book, user, onUser } = useWorkspace();
  const [follow, setFollow] = useState(() => loadPref("reader:tts-follow", true));
  const lastManualScroll = useRef(0);

  // Read aloud. Moving into the next chapter shows it here, without counting as reading progress.
  const showChapter = useCallback((id: number) => {
    byUser.current = false;
    resumeRef.current = null;
    setChapterId(id);
  }, []);
  const player = useBookPlayer({ bookId, bookTitle: book.title, chapters, user, saved: book.listening, onShowChapter: showChapter });
  const reading = player.current; // the sentence being read aloud

  // Reading progress. Only the reader's own navigation and scrolling count: jumping to a cited
  // passage or a search hit must not move the bookmark or mark chapters as read.
  const resumeRef = useRef<Reading | null>(target ? null : resume ?? null);
  const byUser = useRef(!target);
  const userScrolled = useRef(false);
  const reached = useRef(false);
  const pending = useRef<(() => Promise<void>) | null>(null);
  const saveTimer = useRef<number>();
  const onReadingRef = useRef(onReading);
  onReadingRef.current = onReading;

  const flush = useCallback(() => {
    window.clearTimeout(saveTimer.current);
    const run = pending.current;
    pending.current = null;
    return run ? run() : Promise.resolve();
  }, []);

  /** Paragraph offset at the top of the screen, to resume at the same spot. */
  const topOffset = () => {
    const el = scrollRef.current;
    if (!el) return 0;
    const top = el.getBoundingClientRect().top;
    for (const p of el.querySelectorAll<HTMLElement>("p[data-p]")) {
      if (p.getBoundingClientRect().bottom > top + 8) return Number(p.dataset.p);
    }
    return 0;
  };

  const report = (isReached: boolean) => {
    if (!chapter || !onReadingRef.current) return;
    reached.current ||= isReached;
    const body = { position: chapter.position, offset: topOffset(), reached: reached.current };
    pending.current = () =>
      api
        .saveReading(bookId, body)
        .then((r) => onReadingRef.current?.(r))
        .catch(() => {});
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(flush, 1200);
  };

  useEffect(() => () => void flush(), [flush]); // save the last position when the reader closes

  // Chapter list; open the target, else where the reader left off, else chapter 1.
  useEffect(() => {
    api
      .chapters(bookId)
      .then((list) => {
        setChapters(list);
        setChapterId((cur) => {
          if (cur) return cur;
          const r = resumeRef.current;
          const last = loadPref<number | null>(`reader:last:${bookId}`, null);
          return (r && list.find((c) => c.position === r.position)?.id) ?? list.find((c) => c.id === last)?.id ?? list[0]?.id ?? null;
        });
      })
      .catch((e) => setError(e.message));
  }, [bookId]);

  useEffect(() => {
    if (!target) return;
    void flush();
    byUser.current = false;
    resumeRef.current = null;
    setHits(null);
    if (target.chapterId) {
      // a cited passage in a book with verses: its verses are chosen, so the verse bar shows "John 3:16–21"
      setVerseSel(target.verses ? { chapterId: target.chapterId, number: target.verses.start, last: target.verses.end, span: target.highlight } : null);
      setChapterId(target.chapterId);
      setScrollNonce((n) => n + 1);
    }
    if (target.ref) {
      // A link to a verse (#/book/1/read?ref=John+3:16): find it, then show it like a cited passage.
      api
        .lookupVerse(bookId, target.ref)
        .then((hit) => {
          setChapterId(hit.chapter_id);
          setVerseSel(
            hit.verse !== null && hit.start !== null && hit.end !== null
              ? { chapterId: hit.chapter_id, number: hit.verse, last: hit.verse_end, span: { start: hit.start, end: hit.end } }
              : null,
          );
          setScrollNonce((n) => n + 1);
        })
        .catch((e) => notify?.((e as Error).message));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, flush, bookId]);

  useEffect(() => {
    if (!chapterId) return;
    setError(null);
    savePref(`reader:last:${bookId}`, chapterId);
    let cancelled = false;
    api
      .chapter(chapterId)
      .then((c) => !cancelled && setChapter(c))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [chapterId, bookId]);

  // Saved highlights for this chapter.
  useEffect(() => {
    setHighlights([]);
    setEditing(null);
    if (!chapterId) return;
    let cancelled = false;
    api
      .highlights(bookId, chapterId)
      .then((h) => !cancelled && setHighlights(h))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [bookId, chapterId]);

  // New chapter on screen: reset per-chapter progress; short chapters count as read after a while.
  useEffect(() => {
    userScrolled.current = false;
    reached.current = false;
    setFraction(0);
    const el = scrollRef.current;
    if (!chapter || !el || !byUser.current) return;
    const t = window.setTimeout(() => {
      if (el.scrollHeight <= el.clientHeight + 40) {
        setFraction(1);
        report(true);
      }
    }, SHORT_CHAPTER_READ_MS);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapter]);

  // The chosen verse in the chapter on screen: its number(s) and where it is in the text.
  const verseList = useMemo(() => (chapter?.verses ?? []).filter((v) => v.kind === "verse"), [chapter]);
  const selectedVerse = useMemo(() => {
    if (!chapter || !verseSel || verseSel.chapterId !== chapter.id || !verseList.length) return null;
    const n = verseSel.number;
    const v = n === "first" ? verseList[0] : n === "last" ? verseList[verseList.length - 1] : verseList.find((x) => x.number <= n && n <= (x.end ?? x.number));
    if (!v) return null;
    const span = typeof n === "number" ? verseSel.span : undefined;
    // a range: "next verse" goes on after its last verse
    const lastNo = typeof n === "number" && verseSel.last && verseSel.last > n ? verseSel.last : null;
    const lastVerse = lastNo ? (verseList.find((x) => x.number <= lastNo && lastNo <= (x.end ?? x.number)) ?? v) : v;
    return {
      verse: v,
      index: verseList.indexOf(v),
      endIndex: verseList.indexOf(lastVerse),
      label: `${v.number}${lastNo ? `–${lastNo}` : v.end ? `–${v.end}` : ""}`,
      start: span?.start ?? v.start,
      end: span?.end ?? v.stop,
    };
  }, [chapter, verseSel, verseList]);

  const ranges = useMemo<Range[]>(() => {
    if (!chapter) return [];
    const r: Range[] = [];
    for (const n of highlights) {
      const { chapter_id, char_start, char_end } = n.location;
      if (chapter_id === chapter.id && char_start !== undefined && char_end !== undefined && char_end > char_start) {
        r.push({ start: char_start, end: char_end, kind: "user", color: n.color ?? "yellow", noteId: n.id, comment: n.comment });
      }
    }
    if (target?.highlight && target.chapterId === chapter.id) r.push({ ...target.highlight, kind: "cite" });
    if (selectedVerse) r.push({ start: selectedVerse.start, end: selectedVerse.end, kind: "verse" });
    if (hits) {
      hits.forEach((h, i) => {
        if (h.chapter_id === chapter.id) r.push({ start: h.start, end: h.end, kind: i === active ? "search-active" : "search" });
      });
    }
    if (!CAN_HIGHLIGHT && reading && reading.chapterId === chapter.id) r.push({ start: reading.start, end: reading.end, kind: "tts" });
    return r;
  }, [chapter, highlights, target, hits, active, reading, selectedVerse]);

  const shownTranslation = translation?.status === "done" ? translation.paragraphs : undefined;
  const body = useMemo(
    () => (chapter ? renderChapter(chapter.text, ranges, chapter.page_map, shownTranslation, chapter.verses) : null),
    [chapter, ranges, shownTranslation],
  );

  // The sentence being read: highlighted, and kept in view while following along (but not right
  // after the reader scrolled by hand: they're looking at something). Re-applied when the text
  // re-renders (a new highlight, a translation), since that replaces the text nodes.
  useEffect(() => {
    const el = scrollRef.current;
    if (!CAN_HIGHLIGHT || !el) return;
    if (!reading || !chapter || reading.chapterId !== chapter.id) {
      CSS.highlights.delete("bookmind-tts");
      return;
    }
    const range = textRange(el, reading.p, reading.start, reading.end);
    if (range) CSS.highlights.set("bookmind-tts", new Highlight(range));
    else CSS.highlights.delete("bookmind-tts");
    if (follow && range && Date.now() - lastManualScroll.current > 8000) {
      const r = range.getBoundingClientRect();
      const box = el.getBoundingClientRect();
      if (r.top < box.top + 40 || r.bottom > box.bottom - 40) {
        el.scrollTo({ top: el.scrollTop + r.top - box.top - el.clientHeight / 3, behavior: Math.abs(r.top - box.top) < 2000 ? "smooth" : "auto" });
      }
    }
  }, [reading, chapter, body, follow]);
  useEffect(() => () => void (CAN_HIGHLIGHT && CSS.highlights.delete("bookmind-tts")), []);
  // Fallback highlight (a <mark>): follow it the same way.
  useEffect(() => {
    if (CAN_HIGHLIGHT || !follow || !reading || Date.now() - lastManualScroll.current < 8000) return;
    scrollRef.current?.querySelector("mark[data-target='tts']")?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [reading, follow, body]);

  // Side-by-side translation: a saved one loads at once; otherwise it's translated in the background (polled).
  useEffect(() => {
    setTranslation(null);
    if (!chapter || !translateTo) return;
    let alive = true;
    let timer: number | undefined;
    const poll = async (start: boolean) => {
      try {
        const st = start ? await api.translate(chapter.id, translateTo) : await api.translation(chapter.id, translateTo);
        if (!alive) return;
        setTranslation(st);
        if (st.status === "running") timer = window.setTimeout(() => poll(false), 2000);
      } catch (e) {
        if (!alive) return;
        setTranslation({ status: "failed", language: translateTo });
        notify?.((e as Error).message);
      }
    };
    poll(true);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapter, translateTo]);

  const chooseLanguage = (lang: string) => {
    const l = lang.trim();
    setLangPicker(false);
    if (!l) return;
    savePref("reader:lang", l);
    setTranslateTo(l);
  };

  // Reading time for the stats page.
  const lastActive = useRef(Date.now());
  useEffect(() => {
    let seconds = 0;
    const sendTime = () => {
      if (seconds) api.addReadingTime(bookId, seconds).catch(() => {});
      seconds = 0;
    };
    const t = window.setInterval(() => {
      if (document.visibilityState === "visible" && Date.now() - lastActive.current < IDLE_AFTER_MS) seconds += TICK_SECONDS;
      if (seconds >= 60) sendTime();
    }, TICK_SECONDS * 1000);
    return () => {
      window.clearInterval(t);
      sendTime();
    };
  }, [bookId]);

  // Scroll to the active search hit, else the cited passage, else where the reader left off, else the top.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !chapter) return;
    const id = requestAnimationFrame(() => {
      const mark =
        el.querySelector<HTMLElement>("mark[data-target='search']") ??
        el.querySelector<HTMLElement>("mark[data-target='cite']") ??
        el.querySelector<HTMLElement>("mark[data-target='verse']");
      if (!mark) {
        const r = resumeRef.current;
        resumeRef.current = null;
        if (r && r.position === chapter.position && r.offset > 0) {
          const para = [...el.querySelectorAll<HTMLElement>("p[data-p]")].filter((p) => Number(p.dataset.p) <= r.offset).pop();
          el.scrollTop = para ? Math.max(para.offsetTop - 8, 0) : 0;
        } else {
          el.scrollTop = 0;
        }
        return;
      }
      const top = Math.max(mark.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop - el.clientHeight / 4, 0);
      // Smooth for short hops; jump instantly across long chapters.
      el.scrollTo({ top, behavior: Math.abs(top - el.scrollTop) < 1500 ? "smooth" : "auto" });
    });
    return () => cancelAnimationFrame(id);
    // (selectedVerse: "first"/"last" become a verse only once their chapter has loaded)
  }, [chapter, scrollNonce, selectedVerse?.start]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const f = el.scrollHeight <= el.clientHeight ? 1 : Math.min(el.scrollTop / (el.scrollHeight - el.clientHeight), 1);
    setFraction(f);
    // Halfway through a chapter you've been reading counts as having read into it.
    if (userScrolled.current) report(f >= 0.5);
  };
  const onTextKeyDown = (e: React.KeyboardEvent) => {
    if (!(player.active && isShortcut(e))) markUserScroll(); // the read-aloud shortcuts don't scroll
  };
  const markUserScroll = () => {
    userScrolled.current = true;
    byUser.current = true;
    lastActive.current = Date.now();
    lastManualScroll.current = Date.now();
  };

  // Read-aloud shortcuts, anywhere except while typing.
  const playerRef = useRef(player);
  playerRef.current = player;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const p = playerRef.current;
      if (!p.active || !isShortcut(e)) return;
      const t = e.target as HTMLElement | null;
      if (t?.closest("input, textarea, select, [contenteditable='true'], [role='menu']")) return;
      if (e.key === " " && t?.closest("button, a")) return; // Space presses the focused button itself
      e.preventDefault();
      if (e.key === " ") p.toggle();
      else if (e.shiftKey) p.paragraph(e.key === "ArrowRight" ? 1 : -1);
      else p.sentence(e.key === "ArrowRight" ? 1 : -1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  /** Read aloud from the sentence at (or after) an offset in the chapter on screen. */
  const readHere = (offset: number) => {
    if (!chapter) return;
    lastManualScroll.current = 0; // follow from here
    void player.readFrom(chapter.id, offset);
  };

  const runSearch = async () => {
    const q = query.trim();
    if (q.length < 2) return;
    try {
      const res = await api.search(bookId, q);
      setHits(res.results);
      setTotal(res.total);
      setShowHits(true);
      if (res.results.length) goToHit(res.results, 0);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const goToHit = (list: SearchHit[], i: number) => {
    const n = list.length;
    if (!n) return;
    const idx = ((i % n) + n) % n;
    setActive(idx);
    if (list[idx].chapter_id !== chapterId) {
      void flush();
      byUser.current = false;
    }
    setChapterId(list[idx].chapter_id);
    setScrollNonce((x) => x + 1);
  };

  const clearSearch = () => {
    setQuery("");
    setHits(null);
    setShowHits(false);
  };

  const changeFont = (d: number) => {
    const next = Math.min(Math.max(fontIdx + d, 0), FONT_SIZES.length - 1);
    setFontIdx(next);
    savePref("reader:font", next);
  };

  // Text selection -> floating highlight toolbar.
  const onMouseUp = (e?: React.MouseEvent) => {
    if ((e?.target as HTMLElement | undefined)?.closest("[data-reader-ui]")) return;
    const el = scrollRef.current;
    const sel = window.getSelection();
    if (!el || !sel || sel.isCollapsed) return setSelection(null);
    const text = sel.toString().trim();
    const range = sel.getRangeAt(0);
    if (text.length < 3 || !el.contains(range.commonAncestorContainer)) return setSelection(null);
    const rect = range.getBoundingClientRect();
    const box = el.getBoundingClientRect();
    const startEl = range.startContainer instanceof Element ? range.startContainer : range.startContainer.parentElement;
    const near = Number(startEl?.closest<HTMLElement>("p[data-p]")?.dataset.p ?? 0);
    setEditing(null);
    setSelection({
      text,
      near,
      top: rect.top - box.top + el.scrollTop - 44,
      left: Math.min(Math.max(rect.left - box.left + rect.width / 2, 100), box.width - 100),
    });
  };

  const saveSelection = async (color: HighlightColor, withNote = false) => {
    if (!selection || !chapter) return;
    const loc = findLoose(chapter.text, selection.text, selection.near);
    const [start, end] = loc ?? [selection.near, selection.near];
    const at = { top: selection.top + 76, left: selection.left };
    window.getSelection()?.removeAllRanges();
    setSelection(null);
    try {
      const note = await api.createNote(bookId, {
        kind: "passage",
        content: loc ? chapter.text.slice(start, end) : selection.text,
        tags: [],
        color,
        location: { chapter_id: chapter.id, chapter_title: chapter.title, page: pageAt(chapter.page_map, start), char_start: start, char_end: loc ? end : start },
      });
      setHighlights((hs) => [...hs, note]);
      onNotesChanged?.();
      if (!loc) notify?.("Saved to notes, but the exact spot couldn't be found to show it in the text.");
      else if (withNote) setEditing({ note, draft: "", ...at });
    } catch (e) {
      notify?.((e as Error).message);
    }
  };

  // Click a saved highlight -> popover to recolour, comment on or delete it.
  const openHighlight = (mark: HTMLElement) => {
    const note = highlights.find((n) => n.id === Number(mark.dataset.note));
    const el = scrollRef.current;
    if (!note || !el) return;
    const rect = mark.getBoundingClientRect();
    const box = el.getBoundingClientRect();
    setEditing({
      note,
      draft: note.comment ?? "",
      top: rect.bottom - box.top + el.scrollTop + 8,
      left: Math.min(Math.max(rect.left - box.left + rect.width / 2, 150), box.width - 150),
    });
  };

  const updateHighlight = async (patch: { color?: HighlightColor; comment?: string }) => {
    if (!editing) return;
    try {
      const n = await api.updateNote(editing.note.id, patch);
      setHighlights((hs) => hs.map((h) => (h.id === n.id ? n : h)));
      setEditing((ed) => (patch.comment !== undefined ? null : ed && { ...ed, note: n }));
      onNotesChanged?.();
    } catch (e) {
      notify?.((e as Error).message);
    }
  };

  const removeHighlight = async () => {
    if (!editing) return;
    try {
      await api.deleteNote(editing.note.id);
      setHighlights((hs) => hs.filter((h) => h.id !== editing.note.id));
      setEditing(null);
      onNotesChanged?.();
    } catch (e) {
      notify?.((e as Error).message);
    }
  };

  const idx = chapters.findIndex((c) => c.id === chapterId);
  const prev = idx > 0 ? chapters[idx - 1] : null;
  const next = idx >= 0 && idx < chapters.length - 1 ? chapters[idx + 1] : null;
  /** The reader's own chapter navigation: moves the bookmark. `finished` = they read to the end. */
  const goChapter = (id: number, finished = false) => {
    if (finished) report(true);
    const position = chapters.find((c) => c.id === id)?.position;
    void flush().then(() => {
      if (position && onReadingRef.current) {
        api
          .saveReading(bookId, { position, offset: 0, reached: false })
          .then((r) => onReadingRef.current?.(r))
          .catch(() => {});
      }
    });
    byUser.current = true;
    resumeRef.current = null;
    setVerseSel(null);
    setChapterId(id);
    setScrollNonce((n) => n + 1);
  };
  /** Books with verses: show a verse (the reader's own navigation, like choosing a chapter). */
  const goVerse = (id: number, number: number | "first" | "last", span?: { start: number; end: number }) => {
    if (id !== chapterId) goChapter(id);
    setVerseSel({ chapterId: id, number, span });
    setScrollNonce((n) => n + 1);
  };
  const stepVerse = (d: 1 | -1) => {
    if (!selectedVerse || !chapter) return;
    const to = verseList[(d > 0 ? selectedVerse.endIndex : selectedVerse.index) + d];
    if (to) return goVerse(chapter.id, to.number);
    const other = d > 0 ? next : prev;
    if (other?.number != null) goVerse(other.id, d > 0 ? "first" : "last");
  };
  const verseLabel = selectedVerse && chapter ? `${chapter.title}:${selectedVerse.label}` : null;
  const copyVerseLink = async () => {
    if (!verseLabel) return;
    const url = `${window.location.origin}${window.location.pathname}#/book/${bookId}/read?ref=${encodeURIComponent(verseLabel.replace("–", "-"))}`;
    try {
      await navigator.clipboard.writeText(url);
      notify?.(`Link to ${verseLabel} copied.`);
    } catch {
      notify?.(url);
    }
  };
  const hasVerses = chapters.some((c) => c.section);
  const iconBtn = "rounded-md p-1.5 text-stone-500 hover:bg-stone-100 disabled:opacity-30 dark:hover:bg-stone-800";
  const bookFraction = chapters.length && idx >= 0 ? (idx + fraction) / chapters.length : 0;

  return (
    <aside className="flex h-full w-full flex-col border-l border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900">
      {/* Chapter navigation (positioned: the verse navigator's panel opens across it) */}
      <div className="relative flex items-center gap-1 border-b border-stone-200 px-2 py-1.5 dark:border-stone-800">
        <button disabled={!prev} onClick={() => prev && goChapter(prev.id)} className={iconBtn} title="Previous chapter">
          <ChevronLeft size={18} />
        </button>
        {hasVerses ? (
          <VerseNavigator
            bookId={bookId}
            chapters={chapters}
            current={chapters.find((c) => c.id === chapterId) ?? null}
            onChapter={(id) => goChapter(id)}
            onVerse={(id, n, span) => goVerse(id, n, span)}
          />
        ) : (
          <select
            value={chapterId ?? ""}
            onChange={(e) => goChapter(Number(e.target.value))}
            className="min-w-0 flex-1 truncate rounded-md border border-stone-200 bg-transparent px-2 py-1 text-sm dark:border-stone-700"
            aria-label="Chapter"
          >
            {chapters.map((c) => (
              <option key={c.id} value={c.id} className="dark:bg-stone-900">
                {c.position}. {c.title}
              </option>
            ))}
          </select>
        )}
        <button disabled={!next} onClick={() => next && goChapter(next.id)} className={iconBtn} title="Next chapter">
          <ChevronRight size={18} />
        </button>
        <div className="mx-1 hidden h-5 w-px bg-stone-200 sm:block dark:bg-stone-700" />
        <button onClick={() => changeFont(-1)} disabled={fontIdx === 0} className={`${iconBtn} hidden text-xs font-semibold sm:block`} title="Smaller text">
          A−
        </button>
        <button onClick={() => changeFont(1)} disabled={fontIdx === FONT_SIZES.length - 1} className={`${iconBtn} hidden text-sm font-semibold sm:block`} title="Larger text">
          A+
        </button>
        <div className="relative">
          <button
            onClick={() => (translateTo ? setTranslateTo(null) : setLangPicker((v) => !v))}
            className={`${iconBtn} ${translateTo ? "!bg-brand-100 !text-brand-700 dark:!bg-brand-900/60 dark:!text-brand-200" : ""}`}
            title={translateTo ? `Hide the ${translateTo} translation` : "Translate side by side"}
            aria-pressed={!!translateTo}
          >
            <Languages size={16} />
          </button>
          {langPicker && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                chooseLanguage(String(new FormData(e.currentTarget).get("lang") ?? ""));
              }}
              className="absolute right-0 z-30 mt-1 w-60 rounded-lg border border-stone-200 bg-white p-2 font-sans shadow-lg dark:border-stone-700 dark:bg-stone-900"
            >
              <label htmlFor="reader-lang" className="text-xs font-medium text-stone-500">Translate into</label>
              <div className="mt-1 flex gap-1">
                <input
                  id="reader-lang"
                  name="lang"
                  list="reader-lang-options"
                  autoFocus
                  defaultValue={loadPref<string>("reader:lang", "French")}
                  onKeyDown={(e) => e.key === "Escape" && setLangPicker(false)}
                  className="min-w-0 flex-1 rounded-md border border-stone-300 bg-transparent px-2 py-1 text-sm dark:border-stone-700"
                />
                <button type="submit" className="rounded-md bg-brand-600 px-2 text-xs font-medium text-white hover:bg-brand-700">
                  Go
                </button>
              </div>
              <datalist id="reader-lang-options">
                {LANGUAGES.map((l) => (
                  <option key={l} value={l} />
                ))}
              </datalist>
              <p className="mt-1.5 text-[11px] leading-snug text-stone-400">Uses your AI model. Each chapter is translated once, then saved.</p>
            </form>
          )}
        </div>
        <button onClick={onToggleExpand} className={`${iconBtn} hidden md:block`} title={expanded ? "Show chat" : "Read full width"}>
          {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
        </button>
        <button onClick={onClose} className={iconBtn} title="Close reader">
          <X size={18} />
        </button>
      </div>
      <div className="h-0.5 bg-stone-100 dark:bg-stone-800" title={`${Math.round(bookFraction * 100)}% through the book`}>
        <div className="h-full bg-brand-500 transition-[width]" style={{ width: `${bookFraction * 100}%` }} />
      </div>

      {selectedVerse && verseLabel && (
        <div className="flex items-center gap-1 border-b border-stone-200 bg-brand-50/60 px-2 py-1 text-sm dark:border-stone-800 dark:bg-brand-900/25" aria-label="Chosen verse">
          <button onClick={() => stepVerse(-1)} disabled={selectedVerse.index === 0 && prev?.number == null} className={iconBtn} title="Previous verse" aria-label="Previous verse">
            <ChevronLeft size={16} />
          </button>
          <span className="min-w-0 truncate font-medium text-brand-800 tabular-nums dark:text-brand-200" aria-live="polite">
            {verseLabel}
          </span>
          <button
            onClick={() => stepVerse(1)}
            disabled={selectedVerse.endIndex === verseList.length - 1 && next?.number == null}
            className={iconBtn}
            title="Next verse"
            aria-label="Next verse"
          >
            <ChevronRight size={16} />
          </button>
          <span className="flex-1" />
          <button onClick={() => readHere(selectedVerse.start)} className={`${iconBtn} flex items-center gap-1 text-xs`} title="Read aloud from this verse">
            <Play size={14} /> <span className="hidden sm:inline">Read from here</span>
          </button>
          <button onClick={copyVerseLink} className={iconBtn} title="Copy a link to this verse" aria-label="Copy a link to this verse">
            <Link2 size={15} />
          </button>
          <button onClick={() => setVerseSel(null)} className={iconBtn} title="Clear" aria-label="Clear the chosen verse">
            <X size={15} />
          </button>
        </div>
      )}

      {translateTo && translation && translation.status !== "done" && (
        <div className="flex items-center gap-2 border-b border-stone-200 bg-brand-50 px-3 py-1.5 text-xs text-brand-800 dark:border-stone-800 dark:bg-brand-950/40 dark:text-brand-200">
          {translation.status === "failed" ? (
            <span className="flex-1">Translation into {translateTo} failed{translation.job?.error ? `: ${translation.job.error}` : "."}</span>
          ) : (
            <>
              <Loader2 size={12} className="shrink-0 animate-spin" />
              <span className="flex-1">
                Translating this chapter into {translateTo}… {Math.round((translation.job?.progress ?? 0) * 100)}%
              </span>
            </>
          )}
          <button onClick={() => setTranslateTo(null)} className="rounded p-0.5 hover:bg-brand-100 dark:hover:bg-brand-900" aria-label="Close translation">
            <X size={12} />
          </button>
        </div>
      )}

      {/* Search */}
      <div className="relative border-b border-stone-200 px-2 py-1.5 dark:border-stone-800">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            // hits are cleared whenever the query changes, so existing hits belong to this query.
            if (hits?.length) goToHit(hits, active + 1);
            else runSearch();
          }}
          className="flex items-center gap-1 rounded-md border border-stone-200 px-2 focus-within:border-brand-500 dark:border-stone-700"
        >
          <Search size={14} className="shrink-0 text-stone-400" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setHits(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.shiftKey && hits?.length) {
                e.preventDefault();
                goToHit(hits, active - 1);
              }
              if (e.key === "Escape") clearSearch();
            }}
            placeholder="Search in book…"
            className="min-w-0 flex-1 bg-transparent py-1 text-sm outline-none"
            aria-label="Search in book"
          />
          {hits && (
            <>
              <button type="button" onClick={() => setShowHits((v) => !v)} className="shrink-0 text-xs text-stone-500 hover:text-stone-800 dark:hover:text-stone-200">
                {hits.length ? `${active + 1} / ${total}` : "No matches"}
              </button>
              <button type="button" disabled={!hits.length} onClick={() => goToHit(hits, active - 1)} className="p-0.5 text-stone-500 disabled:opacity-30" title="Previous match (Shift+Enter)">
                <ChevronUp size={14} />
              </button>
              <button type="button" disabled={!hits.length} onClick={() => goToHit(hits, active + 1)} className="p-0.5 text-stone-500 disabled:opacity-30" title="Next match (Enter)">
                <ChevronDown size={14} />
              </button>
            </>
          )}
          {query && (
            <button type="button" onClick={clearSearch} className="p-0.5 text-stone-400 hover:text-stone-700" title="Clear search">
              <X size={14} />
            </button>
          )}
        </form>
        {showHits && hits && hits.length > 0 && (
          <div className="absolute inset-x-2 top-full z-20 mt-1 max-h-72 overflow-y-auto rounded-lg border border-stone-200 bg-white p-1 shadow-lg dark:border-stone-700 dark:bg-stone-900">
            {total > hits.length && <p className="px-2 py-1 text-xs text-stone-500">Showing first {hits.length} of {total} matches</p>}
            {hits.map((h, i) => (
              <button
                key={`${h.chapter_id}-${h.start}`}
                onClick={() => {
                  goToHit(hits, i);
                  setShowHits(false);
                }}
                className={`block w-full rounded-md px-2 py-1.5 text-left text-xs hover:bg-stone-100 dark:hover:bg-stone-800 ${i === active ? "bg-stone-100 dark:bg-stone-800" : ""}`}
              >
                <span className="font-medium text-stone-700 dark:text-stone-200">
                  Ch. {h.chapter_position}
                  {h.page ? ` · p. ${h.page}` : ""}
                </span>
                <span className="mt-0.5 block text-stone-500">
                  {h.before}
                  <mark className="search-hl">{h.match}</mark>
                  {h.after}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Text */}
      <div
        ref={scrollRef}
        onClick={(e) => {
          setShowHits(false);
          const t = e.target as HTMLElement;
          if (t.closest("[data-reader-ui]")) return;
          const num = t.closest<HTMLElement>("[data-verse-num]");
          if (num && chapter) return goVerse(chapter.id, Number(num.dataset.verseNum));
          const mark = t.closest<HTMLElement>("mark[data-note]");
          const collapsed = window.getSelection()?.isCollapsed !== false;
          if (mark && collapsed) openHighlight(mark);
          else if (editing) setEditing(null);
          else if (player.active && collapsed && !selection) {
            // while listening, tapping a paragraph reads from there
            const para = t.closest<HTMLElement>("p[data-p]");
            if (para) readHere(Number(para.dataset.p));
          }
        }}
        onMouseUp={onMouseUp}
        onTouchEnd={() => window.setTimeout(onMouseUp, 50)}
        onScroll={onScroll}
        onWheel={markUserScroll}
        onTouchMove={markUserScroll}
        onPointerDown={markUserScroll /* includes dragging the scrollbar */}
        onKeyDown={onTextKeyDown}
        tabIndex={-1}
        className="relative flex-1 overflow-y-auto px-5 py-4 font-serif outline-none sm:px-8"
        style={{ fontSize: FONT_SIZES[fontIdx], lineHeight: 1.75 }}
      >
        {selection && (
          <div
            data-reader-ui
            onMouseDown={(e) => e.preventDefault() /* keep the text selection */}
            style={{ top: Math.max(selection.top, 4), left: selection.left }}
            className="absolute z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-lg bg-stone-900 px-2 py-1.5 font-sans shadow-lg dark:bg-stone-100"
          >
            {COLORS.map((c) => (
              <button
                key={c}
                onClick={() => saveSelection(c)}
                className={`h-5 w-5 rounded-full border-2 border-white/60 transition hover:scale-110 dark:border-stone-900/30 ${SWATCH[c]}`}
                title={`Highlight in ${c}`}
                aria-label={`Highlight in ${c}`}
              />
            ))}
            <span className="h-4 w-px bg-white/30 dark:bg-stone-400" />
            <button onClick={() => saveSelection("yellow", true)} className="px-1 text-xs font-medium whitespace-nowrap text-white hover:underline dark:text-stone-900">
              ✎ Add note
            </button>
            <span className="h-4 w-px bg-white/30 dark:bg-stone-400" />
            <button
              onClick={() => {
                const loc = chapter && findLoose(chapter.text, selection.text, selection.near);
                window.getSelection()?.removeAllRanges();
                setSelection(null);
                readHere(loc ? loc[0] : selection.near);
              }}
              className="px-1 text-xs font-medium whitespace-nowrap text-white hover:underline dark:text-stone-900"
              title="Read aloud from here"
            >
              ▶ Read from here
            </button>
          </div>
        )}
        {editing && (
          <div
            data-reader-ui
            style={{ top: editing.top, left: editing.left }}
            className="absolute z-20 w-72 max-w-[calc(100%-1rem)] -translate-x-1/2 rounded-xl border border-stone-200 bg-white p-3 font-sans text-sm shadow-xl dark:border-stone-700 dark:bg-stone-900"
          >
            <div className="flex items-center gap-1.5">
              {COLORS.map((c) => (
                <button
                  key={c}
                  onClick={() => updateHighlight({ color: c })}
                  className={`h-5 w-5 rounded-full ${SWATCH[c]} ${(editing.note.color ?? "yellow") === c ? "ring-2 ring-stone-500 ring-offset-1 dark:ring-stone-300 dark:ring-offset-stone-900" : ""}`}
                  title={`Colour: ${c}`}
                  aria-label={`Colour: ${c}`}
                />
              ))}
              <button onClick={removeHighlight} className="ml-auto rounded p-1 text-stone-400 hover:text-red-600" title="Delete highlight" aria-label="Delete highlight">
                <Trash2 size={14} />
              </button>
              <button onClick={() => setEditing(null)} className="rounded p-1 text-stone-400 hover:text-stone-700 dark:hover:text-stone-200" title="Close" aria-label="Close">
                <X size={14} />
              </button>
            </div>
            <textarea
              autoFocus
              value={editing.draft}
              onChange={(e) => setEditing({ ...editing, draft: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) updateHighlight({ comment: editing.draft });
                if (e.key === "Escape") setEditing(null);
              }}
              rows={3}
              placeholder="Your note on this passage…"
              className="mt-2 w-full resize-y rounded-md border border-stone-200 bg-transparent px-2 py-1 text-sm outline-none focus:border-brand-500 dark:border-stone-700"
              aria-label="Note on this highlight"
            />
            <div className="mt-2 flex justify-end">
              <button
                disabled={editing.draft.trim() === (editing.note.comment ?? "")}
                onClick={() => updateHighlight({ comment: editing.draft })}
                className={buttonClasses("primary")}
              >
                Save note
              </button>
            </div>
          </div>
        )}
        <div className={`@container ${expanded ? (shownTranslation ? "mx-auto max-w-6xl" : "mx-auto max-w-2xl") : ""}`}>
          {error && <p className="font-sans text-sm text-red-600">{error}</p>}
          {chapter && (
            <>
              <p className="font-sans text-xs tracking-wide text-stone-400 uppercase">
                {chapter.section && chapter.number != null ? `${chapter.section} · Chapter ${chapter.number}` : `Chapter ${chapter.position}`}
                {chapter.page_map[0] ? ` · page ${chapter.page_map[0][1]}` : ""}
              </p>
              <h2 className="mt-1 mb-4 font-sans text-xl font-semibold">{chapter.title}</h2>
              {body}
              <div className="mt-8 flex justify-between gap-2 border-t border-stone-200 pt-4 font-sans text-sm dark:border-stone-800">
                {prev ? (
                  <button onClick={() => goChapter(prev.id)} className="min-w-0 truncate text-brand-600 hover:underline dark:text-brand-300">
                    ← {prev.title}
                  </button>
                ) : <span />}
                {next && (
                  <button onClick={() => goChapter(next.id, true)} className="min-w-0 truncate text-right text-brand-600 hover:underline dark:text-brand-300">
                    {next.title} →
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <ListenBar
        player={player}
        chapters={chapters}
        shownChapter={chapters.find((c) => c.id === chapter?.id) ?? null}
        hereOffset={topOffset}
        follow={follow}
        onFollow={(v) => {
          setFollow(v);
          savePref("reader:tts-follow", v);
          if (v) lastManualScroll.current = 0;
        }}
        user={user}
        onUser={onUser}
      />
    </aside>
  );
}
