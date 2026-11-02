import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Maximize2, Minimize2, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { ChapterInfo, ChapterText, SearchHit } from "../types";
import { findLoose, loadPref, savePref } from "../utils";

export interface ReaderTarget {
  chapterId: number;
  highlight?: { start: number; end: number };
  nonce: number; // forces re-scroll when the same passage is clicked again
}

interface Range {
  start: number;
  end: number;
  kind: "cite" | "search" | "search-active";
}

const FONT_SIZES = [15, 17, 19, 22];

/**
 * Render chapter text as paragraphs, wrapping highlight ranges in <mark> and inserting
 * page markers at page boundaries. Offsets are character offsets into chapter.text.
 */
function renderChapter(text: string, ranges: Range[], pageMap: [number, number][]) {
  const marks = pageMap.filter(([o]) => o > 0);
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
      const active = cover.find((r) => r.kind === "search-active");
      const search = cover.find((r) => r.kind === "search");
      if (active || search) {
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
      } else {
        children.push(seg);
      }
    }
    out.push(
      <p key={pi} data-p={pStart} className="my-[0.9em]">
        {children}
      </p>,
    );
  });
  return out;
}

export interface Highlight {
  text: string;
  chapterId: number;
  chapterTitle: string;
  page: number | null;
  start: number;
  end: number;
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
  expanded,
  onToggleExpand,
  onClose,
  onSaveHighlight,
}: {
  bookId: number;
  target: ReaderTarget | null;
  expanded: boolean;
  onToggleExpand: () => void;
  onClose: () => void;
  onSaveHighlight?: (h: Highlight) => void;
}) {
  const [selection, setSelection] = useState<{ text: string; near: number; top: number; left: number } | null>(null);
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chapterId, setChapterId] = useState<number | null>(target?.chapterId ?? null);
  const [chapter, setChapter] = useState<ChapterText | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fontIdx, setFontIdx] = useState(() => loadPref("reader:font", 1));
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [total, setTotal] = useState(0);
  const [active, setActive] = useState(0);
  const [showHits, setShowHits] = useState(false);
  const [scrollNonce, setScrollNonce] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Chapter list; open the target, else where the reader left off, else chapter 1.
  useEffect(() => {
    api
      .chapters(bookId)
      .then((list) => {
        setChapters(list);
        setChapterId((cur) => {
          if (cur) return cur;
          const last = loadPref<number | null>(`reader:last:${bookId}`, null);
          return list.find((c) => c.id === last)?.id ?? list[0]?.id ?? null;
        });
      })
      .catch((e) => setError(e.message));
  }, [bookId]);

  useEffect(() => {
    if (target) {
      setChapterId(target.chapterId);
      setHits(null);
      setScrollNonce((n) => n + 1);
    }
  }, [target]);

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

  const ranges = useMemo<Range[]>(() => {
    if (!chapter) return [];
    const r: Range[] = [];
    if (target?.highlight && target.chapterId === chapter.id) r.push({ ...target.highlight, kind: "cite" });
    if (hits) {
      hits.forEach((h, i) => {
        if (h.chapter_id === chapter.id) r.push({ start: h.start, end: h.end, kind: i === active ? "search-active" : "search" });
      });
    }
    return r;
  }, [chapter, target, hits, active]);

  const body = useMemo(() => (chapter ? renderChapter(chapter.text, ranges, chapter.page_map) : null), [chapter, ranges]);

  // Scroll to the active search hit, else the cited passage, else the top.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !chapter) return;
    const id = requestAnimationFrame(() => {
      const mark =
        el.querySelector<HTMLElement>("mark[data-target='search']") ?? el.querySelector<HTMLElement>("mark[data-target='cite']");
      if (!mark) {
        el.scrollTop = 0;
        return;
      }
      const top = Math.max(mark.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop - el.clientHeight / 4, 0);
      // Smooth for short hops; jump instantly across long chapters.
      el.scrollTo({ top, behavior: Math.abs(top - el.scrollTop) < 1500 ? "smooth" : "auto" });
    });
    return () => cancelAnimationFrame(id);
  }, [chapter, scrollNonce]);

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

  // Text selection -> floating "Save highlight" button.
  const onMouseUp = () => {
    const el = scrollRef.current;
    const sel = window.getSelection();
    if (!el || !sel || sel.isCollapsed || !onSaveHighlight) return setSelection(null);
    const text = sel.toString().trim();
    const range = sel.getRangeAt(0);
    if (text.length < 3 || !el.contains(range.commonAncestorContainer)) return setSelection(null);
    const rect = range.getBoundingClientRect();
    const box = el.getBoundingClientRect();
    const startEl = range.startContainer instanceof Element ? range.startContainer : range.startContainer.parentElement;
    const near = Number(startEl?.closest<HTMLElement>("p[data-p]")?.dataset.p ?? 0);
    setSelection({
      text,
      near,
      top: rect.top - box.top + el.scrollTop - 40,
      left: Math.min(Math.max(rect.left - box.left + rect.width / 2, 70), box.width - 70),
    });
  };

  const saveSelection = () => {
    if (!selection || !chapter || !onSaveHighlight) return;
    const loc = findLoose(chapter.text, selection.text, selection.near);
    const [start, end] = loc ?? [selection.near, selection.near];
    onSaveHighlight({
      text: loc ? chapter.text.slice(start, end) : selection.text,
      chapterId: chapter.id,
      chapterTitle: chapter.title,
      page: pageAt(chapter.page_map, start),
      start,
      end: loc ? end : start,
    });
    window.getSelection()?.removeAllRanges();
    setSelection(null);
  };

  const idx = chapters.findIndex((c) => c.id === chapterId);
  const prev = idx > 0 ? chapters[idx - 1] : null;
  const next = idx >= 0 && idx < chapters.length - 1 ? chapters[idx + 1] : null;
  const goChapter = (id: number) => {
    setChapterId(id);
    setScrollNonce((n) => n + 1);
  };
  const iconBtn = "rounded-md p-1.5 text-stone-500 hover:bg-stone-100 disabled:opacity-30 dark:hover:bg-stone-800";

  return (
    <aside className="flex h-full w-full flex-col border-l border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900">
      {/* Chapter navigation */}
      <div className="flex items-center gap-1 border-b border-stone-200 px-2 py-1.5 dark:border-stone-800">
        <button disabled={!prev} onClick={() => prev && goChapter(prev.id)} className={iconBtn} title="Previous chapter">
          <ChevronLeft size={18} />
        </button>
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
        <button onClick={onToggleExpand} className={`${iconBtn} hidden md:block`} title={expanded ? "Show chat" : "Read full width"}>
          {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
        </button>
        <button onClick={onClose} className={iconBtn} title="Close reader">
          <X size={18} />
        </button>
      </div>

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
        onClick={() => setShowHits(false)}
        onMouseUp={onMouseUp}
        onTouchEnd={() => window.setTimeout(onMouseUp, 50)}
        className="relative flex-1 overflow-y-auto px-5 py-4 font-serif sm:px-8"
        style={{ fontSize: FONT_SIZES[fontIdx], lineHeight: 1.75 }}
      >
        {selection && (
          <button
            onMouseDown={(e) => e.preventDefault() /* keep the text selection */}
            onClick={saveSelection}
            style={{ top: Math.max(selection.top, 4), left: selection.left }}
            className="absolute z-10 -translate-x-1/2 rounded-lg bg-stone-900 px-3 py-1.5 font-sans text-xs font-medium whitespace-nowrap text-white shadow-lg hover:bg-stone-700 dark:bg-stone-100 dark:text-stone-900"
          >
            ✎ Save highlight
          </button>
        )}
        <div className={expanded ? "mx-auto max-w-2xl" : ""}>
          {error && <p className="font-sans text-sm text-red-600">{error}</p>}
          {chapter && (
            <>
              <p className="font-sans text-xs tracking-wide text-stone-400 uppercase">
                Chapter {chapter.position}
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
                  <button onClick={() => goChapter(next.id)} className="min-w-0 truncate text-right text-brand-600 hover:underline dark:text-brand-300">
                    {next.title} →
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}
