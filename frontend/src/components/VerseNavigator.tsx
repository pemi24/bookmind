import { ChevronDown, ChevronRight, CornerDownLeft, Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { ChapterInfo, VerseInfo } from "../types";

/** A section of a book with verses ("Genesis") and its chapters, in reading order. */
interface Section {
  name: string;
  chapters: ChapterInfo[];
}

type Step = { kind: "books" } | { kind: "chapters"; section: string } | { kind: "verses"; chapter: ChapterInfo };

/**
 * Go to a verse: type a reference ("John 3:16", "Gen 1:3", "3:16"), or pick a book, then a chapter,
 * then a verse from numbered grids. Grids move with the arrow keys; Escape closes.
 */
export default function VerseNavigator({
  bookId,
  chapters,
  current,
  onChapter,
  onVerse,
}: {
  bookId: number;
  chapters: ChapterInfo[];
  current: ChapterInfo | null; // the chapter on screen
  onChapter: (chapterId: number) => void; // a chapter without choosing a verse
  onVerse: (chapterId: number, verse: number, highlight?: { start: number; end: number }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>({ kind: "books" });
  const [ref, setRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verses, setVerses] = useState<VerseInfo[] | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const { sections, others } = useMemo(() => {
    const sections: Section[] = [];
    const others: ChapterInfo[] = [];
    for (const c of chapters) {
      if (!c.section) others.push(c);
      else if (sections.at(-1)?.name === c.section) sections.at(-1)!.chapters.push(c);
      else sections.push({ name: c.section, chapters: [c] });
    }
    return { sections, others };
  }, [chapters]);

  // Opening starts where the reader is: the chapters of the book on screen.
  const show = () => {
    setError(null);
    setStep(current?.section ? { kind: "chapters", section: current.section } : { kind: "books" });
    setOpen(true);
  };
  useEffect(() => {
    if (!open) return;
    input.current?.select(); // focused, with any earlier text selected so typing replaces it
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  // The verses of the chosen chapter (from the server: a chapter's verses come with its text).
  useEffect(() => {
    if (step.kind !== "verses") return;
    let alive = true;
    setVerses(null);
    api
      .chapter(step.chapter.id)
      .then((c) => alive && setVerses((c.verses ?? []).filter((v) => v.kind === "verse")))
      .catch((e) => alive && setError((e as Error).message));
    return () => {
      alive = false;
    };
  }, [step]);

  const go = async () => {
    const text = ref.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      const hit = await api.lookupVerse(bookId, text, current?.id);
      setOpen(false);
      setRef("");
      if (hit.verse !== null && hit.start !== null && hit.end !== null) onVerse(hit.chapter_id, hit.verse, { start: hit.start, end: hit.end });
      else onChapter(hit.chapter_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const section = step.kind === "chapters" ? sections.find((s) => s.name === step.section) : null;
  const label = current ? current.title : "Choose a chapter";

  return (
    // (not positioned itself: the panel spans the reader's toolbar, which the parent positions)
    <div ref={box} className="min-w-0 flex-1">
      <button
        onClick={() => (open ? setOpen(false) : show())}
        aria-expanded={open}
        aria-haspopup="dialog"
        className="flex w-full min-w-0 items-center gap-1 rounded-md border border-stone-200 px-2 py-1 text-left text-sm hover:bg-stone-50 dark:border-stone-700 dark:hover:bg-stone-800"
        title="Go to a book, chapter or verse"
      >
        <span className="min-w-0 flex-1 truncate">{label}</span>
        <ChevronDown size={14} className="shrink-0 text-stone-400" />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Go to a verse"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              setOpen(false);
            }
          }}
          className="absolute inset-x-2 top-full z-30 mt-1 flex max-h-[min(70vh,34rem)] max-w-[28rem] flex-col rounded-xl border border-stone-200 bg-white font-sans shadow-xl dark:border-stone-700 dark:bg-stone-900"
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void go();
            }}
            className="border-b border-stone-200 p-2 dark:border-stone-800"
          >
            <label htmlFor="verse-ref" className="sr-only">
              Go to a reference
            </label>
            <div className="flex items-center gap-1 rounded-md border border-stone-300 px-2 focus-within:border-brand-500 dark:border-stone-700">
              <input
                id="verse-ref"
                ref={input}
                value={ref}
                onChange={(e) => {
                  setRef(e.target.value);
                  setError(null);
                }}
                placeholder="Go to… John 3:16, Gen 1:3, 3:16"
                autoComplete="off"
                spellCheck={false}
                className="min-w-0 flex-1 bg-transparent py-1.5 text-sm outline-none"
              />
              <button type="submit" disabled={!ref.trim() || busy} className="rounded p-1 text-stone-500 hover:text-brand-600 disabled:opacity-40" aria-label="Go">
                {busy ? <Loader2 size={14} className="animate-spin" /> : <CornerDownLeft size={14} />}
              </button>
            </div>
            {error && (
              <p role="alert" className="mt-1.5 text-xs text-red-600 dark:text-red-400">
                {error}
              </p>
            )}
          </form>

          {/* where we are: Books › Genesis › Chapter 1 */}
          <nav aria-label="Steps" className="flex items-center gap-1 px-3 pt-2 text-xs text-stone-500">
            <button onClick={() => setStep({ kind: "books" })} className={step.kind === "books" ? "font-semibold text-stone-800 dark:text-stone-100" : "hover:underline"}>
              Books
            </button>
            {step.kind !== "books" && (
              <>
                <ChevronRight size={12} />
                <button
                  onClick={() => setStep({ kind: "chapters", section: step.kind === "chapters" ? step.section : step.chapter.section! })}
                  className={step.kind === "chapters" ? "font-semibold text-stone-800 dark:text-stone-100" : "hover:underline"}
                >
                  {step.kind === "chapters" ? step.section : step.chapter.section}
                </button>
              </>
            )}
            {step.kind === "verses" && (
              <>
                <ChevronRight size={12} />
                <span className="font-semibold text-stone-800 dark:text-stone-100">Chapter {step.chapter.number}</span>
              </>
            )}
          </nav>

          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {step.kind === "books" && (
              <>
                <Grid label="Books" wide>
                  {sections.map((s) => (
                    <GridButton key={s.name} current={s.name === current?.section} onClick={() => setStep({ kind: "chapters", section: s.name })}>
                      {s.name}
                    </GridButton>
                  ))}
                </Grid>
                {others.length > 0 && (
                  <>
                    <p className="mt-3 px-1 text-xs font-medium text-stone-500">Other parts</p>
                    <Grid label="Other parts" wide>
                      {others.map((c) => (
                        <GridButton
                          key={c.id}
                          current={c.id === current?.id}
                          onClick={() => {
                            setOpen(false);
                            onChapter(c.id);
                          }}
                        >
                          {c.title}
                        </GridButton>
                      ))}
                    </Grid>
                  </>
                )}
              </>
            )}
            {step.kind === "chapters" && section && (
              <Grid label={`Chapters of ${section.name}`}>
                {section.chapters.map((c) => (
                  <GridButton key={c.id} current={c.id === current?.id} onClick={() => setStep({ kind: "verses", chapter: c })} title={c.title}>
                    {c.number}
                  </GridButton>
                ))}
              </Grid>
            )}
            {step.kind === "verses" && (
              <>
                <button
                  onClick={() => {
                    setOpen(false);
                    onChapter(step.chapter.id);
                  }}
                  className="mb-2 w-full rounded-md border border-stone-200 px-2 py-1.5 text-left text-sm hover:bg-stone-50 dark:border-stone-700 dark:hover:bg-stone-800"
                >
                  Open {step.chapter.title} from the start
                </button>
                {verses === null ? (
                  <Loader2 size={16} className="mx-auto my-4 animate-spin text-stone-400" />
                ) : (
                  <Grid label={`Verses of ${step.chapter.title}`}>
                    {verses.map((v) => (
                      <GridButton
                        key={v.start}
                        onClick={() => {
                          setOpen(false);
                          onVerse(step.chapter.id, v.number, { start: v.start, end: v.stop });
                        }}
                        title={`${step.chapter.title}:${v.number}${v.end ? `–${v.end}` : ""}`}
                      >
                        {v.end ? `${v.number}–${v.end}` : v.number}
                      </GridButton>
                    ))}
                  </Grid>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** A grid of buttons; arrow keys move between them (up and down by a row). */
function Grid({ label, wide = false, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -2, ArrowDown: 2, Home: -3, End: 3 };
    const move = moves[e.key];
    if (move === undefined) return;
    const buttons = [...e.currentTarget.querySelectorAll<HTMLButtonElement>("button")];
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (at < 0) return;
    e.preventDefault();
    const top = buttons[0].offsetTop;
    const perRow = Math.max(1, buttons.findIndex((b) => b.offsetTop !== top) === -1 ? buttons.length : buttons.findIndex((b) => b.offsetTop !== top));
    const step = Math.abs(move) === 2 ? perRow : 1;
    const to = move === -3 ? 0 : move === 3 ? buttons.length - 1 : at + Math.sign(move) * step;
    buttons[Math.min(Math.max(to, 0), buttons.length - 1)]?.focus();
  };
  return (
    <div
      role="group"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={`grid gap-1 ${wide ? "grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))]" : "grid-cols-[repeat(auto-fill,minmax(2.75rem,1fr))]"}`}
    >
      {children}
    </div>
  );
}

function GridButton({ current = false, title, onClick, children }: { current?: boolean; title?: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      title={title}
      aria-current={current ? "true" : undefined}
      className={`min-w-0 truncate rounded-md px-2 py-1.5 text-sm tabular-nums transition focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none ${
        current ? "bg-brand-600 font-medium text-white" : "bg-stone-100 text-stone-700 hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-200 dark:hover:bg-stone-700"
      }`}
    >
      {children}
    </button>
  );
}
