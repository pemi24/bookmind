import { Quote, Search, Sparkles, Square, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { api, streamLibraryAnswer, type LibraryQuery } from "../api";
import type { AnswerStage, Book, PassageLoc, Source } from "../types";
import { spoilerLimit } from "../utils";
import AnswerMarkdown, { stripCitations } from "./AnswerMarkdown";
import { Button, ErrorBox } from "./ui";

interface Answer {
  text: string;
  sources: Source[];
  cited: number[];
  pending: boolean;
  stage: AnswerStage;
  error?: string;
}

/** Highlight the query's words in a passage snippet. */
function Snippet({ text, query }: { text: string; query: string }) {
  const words = query.toLowerCase().match(/[\p{L}\p{N}']{3,}/gu) ?? [];
  const snippet = text.length > 420 ? text.slice(0, 420).replace(/\s+\S*$/, "") + "…" : text;
  if (!words.length) return <>{snippet}</>;
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "giu");
  return (
    <>
      {snippet.split(re).map((part, i) =>
        i % 2 ? (
          <mark key={i} className="search-hl">
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </>
  );
}

/** Search every indexed book at once (on the Library page): matching passages, or an AI answer drawn from all of them. */
export default function LibrarySearch({ books, onOpenPassage }: { books: Book[]; onOpenPassage: (loc: PassageLoc) => void }) {
  const ready = books.filter((b) => b.status === "ready");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{
    query: string;
    items: Source[];
  } | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [showCites, setShowCites] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Each book's own spoiler guard applies here too.
  const body = (q: string): LibraryQuery => {
    const max_chapters: Record<number, number> = {};
    for (const b of ready) {
      const limit = spoilerLimit(b);
      if (limit !== null) max_chapters[b.id] = limit;
    }
    return { q, max_chapters };
  };

  const search = async () => {
    const q = query.trim();
    if (q.length < 2) return;
    setSearching(true);
    setError(null);
    try {
      const res = await api.librarySearch(body(q));
      setResults({ query: q, items: res.results });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSearching(false);
    }
  };

  const ask = async () => {
    const q = query.trim();
    if (q.length < 2) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setShowCites(false);
    setAnswer({
      text: "",
      sources: [],
      cited: [],
      pending: true,
      stage: "searching",
    });
    const update = (fn: (a: Answer) => Answer) => setAnswer((a) => (a ? fn(a) : a));
    await streamLibraryAnswer(
      body(q),
      {
        onStage: (stage) => update((a) => ({ ...a, stage })),
        onSources: (sources) => update((a) => ({ ...a, sources })),
        onDelta: (t) => update((a) => ({ ...a, text: a.text + t })),
        onDone: (_id, cited) => update((a) => ({ ...a, cited, pending: false })),
        onError: (msg) => update((a) => ({ ...a, error: msg, pending: false })),
      },
      ctrl.signal,
    );
    update((a) => ({ ...a, pending: false }));
  };

  const byBook = useMemo(() => {
    const groups = new Map<number, Source[]>();
    for (const s of results?.items ?? []) groups.set(s.book_id, [...(groups.get(s.book_id) ?? []), s]);
    return [...groups.entries()];
  }, [results]);

  const citedSources = answer ? answer.sources.filter((s) => answer.cited.includes(s.marker)) : [];

  const clear = () => {
    abortRef.current?.abort();
    setQuery("");
    setResults(null);
    setAnswer(null);
    setError(null);
  };

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          search();
        }}
        className="flex flex-wrap gap-2"
      >
        <div className="flex min-w-0 flex-1 basis-64 items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 focus-within:border-brand-500 dark:border-stone-700 dark:bg-stone-900">
          <Search size={16} className="shrink-0 text-stone-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              ready.length
                ? `Search all ${ready.length} indexed book${ready.length === 1 ? "" : "s"}, or ask them a question`
                : "Search becomes available once a book is indexed"
            }
            aria-label="Search all books"
            disabled={!ready.length}
            className="min-w-0 flex-1 bg-transparent py-2 text-sm outline-none"
          />
          {(query || results || answer) && (
            <button
              type="button"
              onClick={clear}
              className="rounded p-0.5 text-stone-400 hover:text-stone-700 dark:hover:text-stone-200"
              aria-label="Clear search"
            >
              <X size={15} />
            </button>
          )}
        </div>
        <Button type="submit" variant="secondary" loading={searching} disabled={query.trim().length < 2 || !ready.length}>
          Find passages
        </Button>
        {answer?.pending ? (
          <Button type="button" onClick={() => abortRef.current?.abort()}>
            <Square size={14} /> Stop
          </Button>
        ) : (
          <Button type="button" variant="primary" onClick={ask} disabled={query.trim().length < 2 || !ready.length}>
            <Sparkles size={14} /> Ask all books
          </Button>
        )}
      </form>

      {error && (
        <div className="mt-4">
          <ErrorBox>{error}</ErrorBox>
        </div>
      )}

      {answer && (
        <section className="mt-5 rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-medium tracking-wide text-stone-400 uppercase">
            <Sparkles size={12} /> Answer from your library
          </p>
          {answer.text && (
            <AnswerMarkdown text={showCites ? answer.text : stripCitations(answer.text)} sources={answer.sources} onCite={onOpenPassage} />
          )}
          {answer.pending && !answer.text && (
            <p className="text-sm text-stone-500" aria-live="polite">
              {answer.stage === "answering" ? `Reading ${answer.sources.length} passages…` : "Searching every book…"}
            </p>
          )}
          {answer.error && (
            <div className="mt-2">
              <ErrorBox>{answer.error}</ErrorBox>
            </div>
          )}
          {!answer.pending && citedSources.length > 0 && (
            <>
              <button
                onClick={() => setShowCites((v) => !v)}
                aria-expanded={showCites}
                className="mt-2 flex items-center gap-1 rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800"
              >
                <Quote size={14} /> {showCites ? "Hide sources" : `Sources (${citedSources.length})`}
              </button>
              {showCites && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {citedSources.map((s) => (
                    <button
                      key={s.marker}
                      onClick={() => onOpenPassage(s)}
                      className="flex max-w-full items-center gap-1.5 rounded-lg border border-stone-200 bg-stone-50 px-2 py-1 text-left text-xs text-stone-600 hover:border-brand-400 dark:border-stone-700 dark:bg-stone-800/60 dark:text-stone-300"
                    >
                      <span className="font-semibold text-brand-600 dark:text-brand-300">[{s.marker}]</span>
                      <span className="truncate">
                        {s.book_title} · {s.label ?? s.chapter_title}
                        {s.page_start ? ` · p. ${s.page_start}` : ""}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </section>
      )}

      {results && (
        <section className="mt-6">
          <h2 className="text-sm font-medium text-stone-500">
            {results.items.length ? `${results.items.length} passages for “${results.query}”` : `Nothing found for “${results.query}”`}
          </h2>
          {byBook.map(([bookId, items]) => (
            <div key={bookId} className="mt-4">
              <h3 className="font-semibold">{items[0].book_title}</h3>
              <ul className="mt-2 space-y-2">
                {items.map((s) => (
                  <li key={s.chunk_id}>
                    <button
                      onClick={() => onOpenPassage(s)}
                      className="w-full rounded-lg border border-stone-200 bg-white p-3 text-left transition hover:border-brand-400 dark:border-stone-800 dark:bg-stone-900"
                    >
                      <p className="text-xs font-medium text-stone-500">
                        {s.label ?? s.chapter_title}
                        {s.page_start ? ` · p. ${s.page_start}` : ""}
                      </p>
                      <p className="mt-1 font-serif text-[15px] leading-relaxed text-stone-700 dark:text-stone-300">
                        <Snippet text={s.text} query={results.query} />
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
