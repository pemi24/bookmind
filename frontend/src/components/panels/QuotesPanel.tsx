import { BookmarkPlus, Copy, Quote as QuoteIcon, Search, Share2 } from "lucide-react";
import { useState } from "react";
import { api } from "../../api";
import type { Quote } from "../../types";
import { useWorkspace } from "../../workspace";
import { Button, EmptyState, ErrorBox, LocationChip, PanelShell } from "../ui";

export function passageLink(bookId: number, chapterId: number, start?: number, end?: number): string {
  const q = start !== undefined && end !== undefined ? `?c=${chapterId}&s=${start}&e=${end}` : `?c=${chapterId}`;
  return `${window.location.origin}${window.location.pathname}#/book/${bookId}/read${q}`;
}

const EXAMPLES = ["madness", "growing up", "the Queen's temper", "time"];

export default function QuotesPanel() {
  const { book, maxChapter, openPassage, saveNote, notify } = useWorkspace();
  const [topic, setTopic] = useState("");
  const [results, setResults] = useState<Quote[] | null>(null);
  const [searched, setSearched] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async (t = topic) => {
    const q = t.trim();
    if (q.length < 2) return;
    setTopic(q);
    setBusy(true);
    setError(null);
    try {
      const res = await api.quotes(book.id, q, maxChapter);
      setResults(res.quotes);
      setSearched(q);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const citation = (q: Quote) => `“${q.quote}” — ${book.title}${book.author ? `, ${book.author}` : ""} (${q.chapter_title}${q.page ? `, p. ${q.page}` : ""})`;

  const share = async (q: Quote) => {
    const url = passageLink(book.id, q.chapter_id, q.char_start, q.char_end);
    try {
      if (navigator.share) await navigator.share({ title: book.title, text: citation(q), url });
      else {
        await navigator.clipboard.writeText(`${citation(q)}\n${url}`);
        notify("Quote and link copied.");
      }
    } catch {
      /* share sheet dismissed */
    }
  };

  return (
    <PanelShell title="Quote finder">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          search();
        }}
        className="flex gap-2"
      >
        <div className="flex flex-1 items-center gap-2 rounded-xl border border-stone-300 bg-white px-3 focus-within:border-brand-500 dark:border-stone-700 dark:bg-stone-900">
          <Search size={16} className="text-stone-400" />
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Find passages about…"
            className="min-w-0 flex-1 bg-transparent py-2 outline-none"
            aria-label="Quote topic"
          />
        </div>
        <Button variant="primary" type="submit" loading={busy} disabled={topic.trim().length < 2}>
          Find quotes
        </Button>
      </form>
      <p className="mt-2 text-xs text-stone-500">Every quote is checked word-for-word against the book before it's shown.</p>

      {error && <div className="mt-4"><ErrorBox>{error}</ErrorBox></div>}

      {results === null && !busy && (
        <EmptyState icon={<QuoteIcon size={22} />} title="Search the book for exact quotations">
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            {EXAMPLES.map((ex) => (
              <button key={ex} onClick={() => search(ex)} className="rounded-full border border-stone-300 px-3 py-1 text-xs hover:border-brand-400 dark:border-stone-700">
                {ex}
              </button>
            ))}
          </div>
        </EmptyState>
      )}

      {results && results.length === 0 && !busy && (
        <EmptyState icon={<QuoteIcon size={22} />} title={`No quotes about “${searched}”`}>
          The book doesn't seem to discuss this{maxChapter ? ` in chapters 1–${maxChapter}` : ""}. Try different words.
        </EmptyState>
      )}

      {results && results.length > 0 && (
        <ul className="mt-5 space-y-3">
          {results.map((q) => (
            <li key={`${q.chapter_id}-${q.char_start}`} className="rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
              <blockquote className="border-l-4 border-brand-400 pl-3 font-serif text-[17px] leading-relaxed">“{q.quote}”</blockquote>
              <p className="mt-2 text-sm text-stone-500">{q.note}</p>
              <div className="mt-3 flex flex-wrap items-center gap-1">
                <LocationChip chapter={q.chapter_title} page={q.page} onClick={() => openPassage({ chapter_id: q.chapter_id, char_start: q.char_start, char_end: q.char_end })} />
                <span className="flex-1" />
                <Button variant="ghost" onClick={() => navigator.clipboard.writeText(citation(q)).then(() => notify("Quote copied."))}>
                  <Copy size={14} /> Copy
                </Button>
                <Button variant="ghost" onClick={() => share(q)}>
                  <Share2 size={14} /> Share
                </Button>
                <Button
                  variant="ghost"
                  onClick={() =>
                    saveNote({
                      kind: "quote",
                      content: q.quote,
                      chunk_id: q.chunk_id,
                      tags: [searched.toLowerCase().slice(0, 40)],
                      location: { chapter_id: q.chapter_id, chapter_title: q.chapter_title, page: q.page, char_start: q.char_start, char_end: q.char_end },
                    })
                  }
                >
                  <BookmarkPlus size={14} /> Save
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </PanelShell>
  );
}
