import { AlertTriangle, Check, Compass, ExternalLink, Loader2, Plus, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Book, CatalogBook, CatalogSourceKey, CatalogSourceStatus } from "../types";
import { coverGradient } from "../utils";
import { Button, EmptyState, ErrorBox } from "./ui";

const SOURCES: { key: CatalogSourceKey; name: string; short: string; note: string; badge: string }[] = [
  { key: "gutenberg", name: "Project Gutenberg", short: "Gutenberg", note: "70,000+ public-domain books", badge: "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-200" },
  { key: "standard", name: "Standard Ebooks", short: "Standard Ebooks", note: "Carefully edited editions", badge: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200" },
  { key: "archive", name: "Internet Archive", short: "Internet Archive", note: "Library scans (may contain OCR errors)", badge: "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-200" },
];
const SOURCE = Object.fromEntries(SOURCES.map((s) => [s.key, s])) as Record<CatalogSourceKey, (typeof SOURCES)[number]>;

/** Same as the server's download_prefix(): books keep their source and id in the file name. */
function filePrefix(b: CatalogBook): string {
  return `${b.source}-${b.id.replace(/[^A-Za-z0-9-]+/g, "_").slice(0, 100)}.`;
}

function Cover({ book }: { book: CatalogBook }) {
  const [failed, setFailed] = useState(!book.cover);
  return (
    <div className="relative aspect-[2/3] w-full overflow-hidden rounded-md shadow-sm" style={{ background: coverGradient(book.title) }}>
      {!failed && (
        <img src={book.cover} alt="" loading="lazy" onError={() => setFailed(true)} className="absolute inset-0 h-full w-full object-cover" />
      )}
      {failed && <p className="absolute inset-0 line-clamp-5 p-2 font-serif text-xs leading-snug font-semibold text-white">{book.title}</p>}
    </div>
  );
}

/** Find free books: search Project Gutenberg, Standard Ebooks and Internet Archive, add one in a click. */
export default function Discover({ books, onAdded }: { books: Book[]; onAdded: (b: Book) => void }) {
  const [query, setQuery] = useState("");
  const [shownQuery, setShownQuery] = useState("");
  const [source, setSource] = useState<CatalogSourceKey | null>(null);
  const [results, setResults] = useState<CatalogBook[] | null>(null);
  const [status, setStatus] = useState<CatalogSourceStatus[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState<"search" | "more" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<Set<string>>(new Set());
  const [added, setAdded] = useState<Set<string>>(new Set());

  const keyOf = (b: CatalogBook) => `${b.source}:${b.id}`;
  const inLibrary = useCallback(
    (b: CatalogBook) => added.has(keyOf(b)) || books.some((x) => x.filename.startsWith(filePrefix(b))),
    [books, added],
  );

  const load = useCallback(async (q: string, p: number, src: CatalogSourceKey | null) => {
    setLoading(p === 1 ? "search" : "more");
    setError(null);
    try {
      const res = await api.catalogSearch(q, p, src);
      setResults((prev) => {
        if (p === 1) return res.results;
        const seen = new Set((prev ?? []).map(keyOf));
        return [...(prev ?? []), ...res.results.filter((r) => !seen.has(keyOf(r)))];
      });
      setStatus(res.sources);
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
    load("", 1, null); // most downloaded books (Project Gutenberg)
  }, [load]);

  const pickSource = (src: CatalogSourceKey | null) => {
    setSource(src);
    if (shownQuery) load(shownQuery, 1, src);
  };

  const add = async (b: CatalogBook) => {
    const k = keyOf(b);
    setAdding((s) => new Set(s).add(k));
    setError(null);
    try {
      const book = await api.catalogImport(b);
      setAdded((s) => new Set(s).add(k));
      onAdded(book);
    } catch (e) {
      setError(`“${b.title}”: ${(e as Error).message}`);
    } finally {
      setAdding((s) => {
        const next = new Set(s);
        next.delete(k);
        return next;
      });
    }
  };

  const failed = status.filter((s) => s.error);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight">Find free books</h1>
        <p className="text-sm text-stone-500">
          Free, legal books from Project Gutenberg, Standard Ebooks and Internet Archive (public-domain items only). Adding one
          downloads it and indexes it like an upload.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            load(query.trim(), 1, source);
          }}
          className="mt-4 flex max-w-xl gap-2"
        >
          <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 focus-within:border-brand-500 dark:border-stone-700 dark:bg-stone-900">
            <Search size={16} className="shrink-0 text-stone-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Title, author or subject…"
              aria-label="Search free books"
              className="min-w-0 flex-1 bg-transparent py-2 text-sm outline-none"
            />
          </div>
          <Button type="submit" variant="primary" loading={loading === "search"}>
            Search
          </Button>
        </form>

        <div className="mt-3 flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label="Where to search">
          {[{ key: null, label: "All sources" }, ...SOURCES.map((s) => ({ key: s.key, label: s.name }))].map((opt) => (
            <button
              key={opt.label}
              role="radio"
              aria-checked={source === opt.key}
              onClick={() => pickSource(opt.key)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                source === opt.key ? "bg-brand-600 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700"
              }`}
              title={opt.key ? SOURCE[opt.key].note : "Search every source at once"}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {error && <div className="mt-4"><ErrorBox>{error}</ErrorBox></div>}
        {failed.length > 0 && (
          <p className="mt-3 flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-400">
            <AlertTriangle size={14} className="mt-px shrink-0" />
            <span>
              {failed.map((s) => s.error).join(" ")} Showing results from the other sources.
            </span>
          </p>
        )}

        <h2 className="mt-6 text-sm font-medium text-stone-500">
          {shownQuery
            ? `Results for “${shownQuery}”` + (status.length > 1 ? ` · ${status.filter((s) => !s.error).map((s) => `${SOURCE[s.key].short} ${s.count}`).join(" · ")}` : "")
            : "Most downloaded on Project Gutenberg"}
        </h2>
        {results === null && loading === "search" && (
          <p className="mt-6 flex items-center gap-2 text-sm text-stone-500">
            <Loader2 size={16} className="animate-spin" /> Searching free-book libraries…
          </p>
        )}
        {results && results.length === 0 && !loading && (
          <EmptyState icon={<Compass size={22} />} title="No free books found">
            Try a shorter search or an author's last name. Books still under copyright (most from the last ~95 years) aren't
            available from these libraries.
          </EmptyState>
        )}
        {results && results.length > 0 && (
          <ul className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {results.map((b) => {
              const have = inLibrary(b);
              const busy = adding.has(keyOf(b));
              return (
                <li key={keyOf(b)} className="flex flex-col">
                  <Cover book={b} />
                  <span className={`mt-2 self-start rounded px-1.5 py-0.5 text-[10px] font-semibold ${SOURCE[b.source].badge}`} title={SOURCE[b.source].note}>
                    {SOURCE[b.source].short}
                  </span>
                  <p className="mt-1 line-clamp-2 text-sm font-medium" title={b.title}>{b.title}</p>
                  <p className="truncate text-xs text-stone-500">{b.author ?? "Unknown author"}</p>
                  <div className="mt-auto flex items-center gap-1 pt-2">
                    <Button
                      variant={have ? "secondary" : "primary"}
                      onClick={() => add(b)}
                      disabled={have}
                      loading={busy}
                      className="flex-1 !px-2 !py-1 text-xs"
                    >
                      {have ? <><Check size={12} /> In library</> : busy ? "Downloading…" : <><Plus size={12} /> Add</>}
                    </Button>
                    <a href={b.url} target="_blank" rel="noreferrer" className="rounded-md p-1.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700 dark:hover:bg-stone-800" title={`View on ${SOURCE[b.source].name}`}>
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
            <Button onClick={() => load(shownQuery, page + 1, source)} loading={loading === "more"}>
              Load more
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
