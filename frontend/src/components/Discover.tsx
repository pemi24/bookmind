import { Check, Compass, ExternalLink, Loader2, Plus, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Book, CatalogBook } from "../types";
import { coverGradient } from "../utils";
import { Button, EmptyState, ErrorBox } from "./ui";

function Cover({ book }: { book: CatalogBook }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="relative aspect-[2/3] w-full overflow-hidden rounded-md shadow-sm" style={{ background: coverGradient(book.title) }}>
      {!failed && (
        <img src={book.cover} alt="" loading="lazy" onError={() => setFailed(true)} className="absolute inset-0 h-full w-full object-cover" />
      )}
      {failed && <p className="absolute inset-0 line-clamp-5 p-2 font-serif text-xs leading-snug font-semibold text-white">{book.title}</p>}
    </div>
  );
}

/** Find free books: search Project Gutenberg and add one to the library in a click. */
export default function Discover({ books, onAdded }: { books: Book[]; onAdded: (b: Book) => void }) {
  const [query, setQuery] = useState("");
  const [shownQuery, setShownQuery] = useState("");
  const [results, setResults] = useState<CatalogBook[] | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState<"search" | "more" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<Set<number>>(new Set());
  const [added, setAdded] = useState<Set<number>>(new Set());

  // Books already imported from Gutenberg are recognised by their file name.
  const inLibrary = useCallback(
    (id: number) => added.has(id) || books.some((b) => b.filename.startsWith(`gutenberg-${id}.`)),
    [books, added],
  );

  const load = useCallback(async (q: string, p: number) => {
    setLoading(p === 1 ? "search" : "more");
    setError(null);
    try {
      const res = await api.catalogSearch(q, p);
      setResults((prev) => (p === 1 ? res.results : [...(prev ?? []), ...res.results]));
      setHasMore(res.has_more);
      setPage(p);
      setShownQuery(q);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(null);
    }
  }, []);

  useEffect(() => {
    load("", 1); // most downloaded books
  }, [load]);

  const add = async (b: CatalogBook) => {
    setAdding((s) => new Set(s).add(b.id));
    setError(null);
    try {
      const book = await api.catalogImport(b.id);
      setAdded((s) => new Set(s).add(b.id));
      onAdded(book);
    } catch (e) {
      setError(`“${b.title}”: ${(e as Error).message}`);
    } finally {
      setAdding((s) => {
        const next = new Set(s);
        next.delete(b.id);
        return next;
      });
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight">Find free books</h1>
        <p className="text-sm text-stone-500">
          Over 70,000 public-domain books from{" "}
          <a href="https://www.gutenberg.org" target="_blank" rel="noreferrer" className="text-brand-600 hover:underline dark:text-brand-300">
            Project Gutenberg
          </a>
          . Adding one downloads it and indexes it like an upload.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            load(query.trim(), 1);
          }}
          className="mt-4 flex max-w-xl gap-2"
        >
          <div className="flex flex-1 items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 focus-within:border-brand-500 dark:border-stone-700 dark:bg-stone-900">
            <Search size={16} className="shrink-0 text-stone-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Title, author or subject…"
              aria-label="Search Project Gutenberg"
              className="min-w-0 flex-1 bg-transparent py-2 text-sm outline-none"
            />
          </div>
          <Button type="submit" variant="primary" loading={loading === "search"}>
            Search
          </Button>
        </form>

        {error && <div className="mt-4"><ErrorBox>{error}</ErrorBox></div>}

        <h2 className="mt-6 text-sm font-medium text-stone-500">{shownQuery ? `Results for “${shownQuery}”` : "Most downloaded"}</h2>
        {results === null && loading === "search" && (
          <p className="mt-6 flex items-center gap-2 text-sm text-stone-500">
            <Loader2 size={16} className="animate-spin" /> Asking Project Gutenberg…
          </p>
        )}
        {results && results.length === 0 && !loading && (
          <EmptyState icon={<Compass size={22} />} title="No books found">
            Try a shorter search, an author's last name, or a subject like “poetry”.
          </EmptyState>
        )}
        {results && results.length > 0 && (
          <ul className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {results.map((b) => {
              const have = inLibrary(b.id);
              return (
                <li key={b.id} className="flex flex-col">
                  <Cover book={b} />
                  <p className="mt-2 line-clamp-2 text-sm font-medium" title={b.title}>{b.title}</p>
                  <p className="truncate text-xs text-stone-500">{b.author ?? "Unknown author"}</p>
                  <div className="mt-auto flex items-center gap-1 pt-2">
                    <Button
                      variant={have ? "secondary" : "primary"}
                      onClick={() => add(b)}
                      disabled={have}
                      loading={adding.has(b.id)}
                      className="flex-1 !px-2 !py-1 text-xs"
                    >
                      {have ? <><Check size={12} /> In library</> : adding.has(b.id) ? "Downloading…" : <><Plus size={12} /> Add</>}
                    </Button>
                    <a href={b.url} target="_blank" rel="noreferrer" className="rounded-md p-1.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700 dark:hover:bg-stone-800" title="View on gutenberg.org">
                      <ExternalLink size={14} />
                    </a>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {hasMore && results && (
          <div className="mt-6 text-center">
            <Button onClick={() => load(shownQuery, page + 1)} loading={loading === "more"}>
              Load more
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
