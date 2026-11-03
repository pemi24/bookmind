import { AlertTriangle, BookOpenText, FileUp, Loader2, MessageSquare, MoreVertical, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Book } from "../types";
import { coverGradient, formatBytes, formatDate, isIndexing } from "../utils";

const ACCEPT = ".pdf,.epub,.docx,.txt,.md,.markdown";

function BookCover({ book }: { book: Book }) {
  return (
    <div
      className="@container relative flex aspect-[3/4] w-full flex-col justify-between overflow-hidden rounded-lg p-3 text-white shadow-md"
      style={{ background: coverGradient(book.title) }}
    >
      <div className="absolute inset-y-0 left-0 w-2 bg-black/20" />
      <span className="self-end rounded bg-black/25 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider uppercase">
        {book.file_type}
      </span>
      <div className="pl-2">
        <p className="line-clamp-4 font-serif text-[clamp(0.85rem,9cqi,1.15rem)] leading-snug font-semibold hyphens-auto [overflow-wrap:anywhere]" lang="en">
          {book.title}
        </p>
        {book.author && <p className="mt-1 line-clamp-1 text-xs opacity-80">{book.author}</p>}
      </div>
    </div>
  );
}

function BookCard({
  book,
  onOpen,
  onRead,
  onReindex,
  onDelete,
  onResetReading,
}: {
  book: Book;
  onOpen: () => void;
  onRead: () => void;
  onReindex: () => void;
  onDelete: () => void;
  onResetReading: () => void;
}) {
  const [menu, setMenu] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setMenu(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);

  const busy = isIndexing(book.status);
  const meta = [
    book.page_count ? `${book.page_count}${book.pages_estimated ? " est." : ""} pages` : null,
    book.chapter_count ? `${book.chapter_count} ch.` : null,
    formatBytes(book.file_size),
  ].filter(Boolean);

  return (
    <div className="group flex flex-col rounded-xl border border-stone-200 bg-white p-3 transition hover:shadow-md dark:border-stone-800 dark:bg-stone-900">
      <button onClick={onOpen} className="block text-left" aria-label={`Open ${book.title}`}>
        <BookCover book={book} />
      </button>
      <div className="mt-3 flex items-start gap-1">
        <button onClick={onOpen} className="min-w-0 flex-1 text-left">
          <p className="truncate text-sm font-semibold" title={book.title}>
            {book.title}
          </p>
          <p className="truncate text-xs text-stone-500">{book.author ?? book.filename}</p>
        </button>
        <div className="relative" ref={ref}>
          <button
            onClick={() => setMenu((v) => !v)}
            className="rounded-md p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700 dark:hover:bg-stone-800 dark:hover:text-stone-200"
            aria-label="Book actions"
          >
            <MoreVertical size={16} />
          </button>
          {menu && (
            <div className="absolute right-0 z-20 mt-1 w-40 rounded-lg border border-stone-200 bg-white p-1 text-sm shadow-lg dark:border-stone-700 dark:bg-stone-900">
              <button disabled={book.status !== "ready"} onClick={() => { setMenu(false); onOpen(); }} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 hover:bg-stone-100 disabled:opacity-40 dark:hover:bg-stone-800">
                <MessageSquare size={14} /> Chat
              </button>
              <button disabled={book.status !== "ready"} onClick={() => { setMenu(false); onRead(); }} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 hover:bg-stone-100 disabled:opacity-40 dark:hover:bg-stone-800">
                <BookOpenText size={14} /> Read
              </button>
              {book.reading && (
                <button onClick={() => { setMenu(false); onResetReading(); }} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 hover:bg-stone-100 dark:hover:bg-stone-800">
                  <RotateCcw size={14} /> Start over
                </button>
              )}
              <button disabled={busy} onClick={() => { setMenu(false); onReindex(); }} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 hover:bg-stone-100 disabled:opacity-40 dark:hover:bg-stone-800">
                <RefreshCw size={14} /> Re-index
              </button>
              <button disabled={book.status === "processing"} onClick={() => { setMenu(false); onDelete(); }} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-red-600 hover:bg-red-50 disabled:opacity-40 dark:hover:bg-red-950/40">
                <Trash2 size={14} /> Delete
              </button>
            </div>
          )}
        </div>
      </div>
      <p className="mt-1 truncate text-xs text-stone-500">{meta.join(" · ")}</p>
      <p className="text-xs text-stone-400">Added {formatDate(book.created_at)}</p>

      <div className="mt-2">
        {busy && (
          <>
            <div className="h-1.5 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-700">
              <div className="h-full bg-brand-500 transition-all" style={{ width: `${Math.round(book.progress * 100)}%` }} />
            </div>
            <p className="mt-1 flex items-center gap-1 truncate text-xs text-stone-500">
              <Loader2 size={12} className="shrink-0 animate-spin" />
              {Math.round(book.progress * 100)}% · {book.status_message ?? "Queued"}
            </p>
          </>
        )}
        {book.status === "ready" && book.reading && book.chapter_count ? (
          <>
            <div className="h-1.5 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-700" title="Furthest chapter read">
              <div className="h-full bg-emerald-500" style={{ width: `${Math.round(((book.reading.furthest ?? 0) / book.chapter_count) * 100)}%` }} />
            </div>
            <button onClick={onRead} className="mt-1 flex w-full items-center justify-between gap-1 text-xs text-stone-500 hover:text-stone-800 dark:hover:text-stone-200">
              <span className="truncate">Ch. {book.reading.position} of {book.chapter_count}</span>
              <span className="shrink-0 font-medium text-brand-600 dark:text-brand-300">Continue →</span>
            </button>
          </>
        ) : book.status === "ready" ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Ready
          </span>
        ) : null}
        {book.status === "failed" && (
          <div className="flex items-start gap-1 text-xs text-red-600 dark:text-red-400" title={book.error ?? ""}>
            <AlertTriangle size={12} className="mt-0.5 shrink-0" />
            <span className="line-clamp-3">{book.error ?? "Indexing failed"}</span>
          </div>
        )}
        {book.status === "ready" && book.warnings.length > 0 && (
          <p className="mt-1 line-clamp-2 text-xs text-amber-700 dark:text-amber-400" title={book.warnings.join("\n")}>
            ⚠ {book.warnings[0]}
          </p>
        )}
      </div>
    </div>
  );
}

export default function Library({
  books,
  onUpload,
  onOpen,
  onRead,
  onReindex,
  onDelete,
  onResetReading,
}: {
  books: Book[];
  onUpload: (files: FileList | File[]) => void;
  onOpen: (id: number) => void;
  onRead: (id: number) => void;
  onReindex: (id: number) => void;
  onDelete: (book: Book) => void;
  onResetReading: (book: Book) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);
  const fileRef = useRef<HTMLInputElement>(null);

  return (
    <div
      className="relative h-full overflow-y-auto"
      onDragEnter={(e) => {
        e.preventDefault();
        depth.current++;
        setDragging(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => {
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        depth.current = 0;
        setDragging(false);
        if (e.dataTransfer.files.length) onUpload(e.dataTransfer.files);
      }}
    >
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Your library</h1>
            <p className="text-sm text-stone-500">
              {books.length ? `${books.length} book${books.length > 1 ? "s" : ""}` : "Upload a book to start chatting with it."}
            </p>
          </div>
          <button
            onClick={() => fileRef.current?.click()}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            <FileUp size={16} /> Upload books
          </button>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.length) onUpload(Array.from(e.target.files));
              e.target.value = "";
            }}
          />
        </div>

        {books.length === 0 ? (
          <button
            onClick={() => fileRef.current?.click()}
            className="mt-8 flex w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-300 px-6 py-16 text-center transition hover:border-brand-400 dark:border-stone-700"
          >
            <FileUp className="text-stone-400" size={32} />
            <p className="mt-3 font-medium">Drop books here or click to browse</p>
            <p className="mt-1 text-sm text-stone-500">PDF, EPUB, DOCX, TXT or Markdown. Try samples/alice-in-wonderland.txt.</p>
          </button>
        ) : (
          <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {books.map((b) => (
              <BookCard
                key={b.id}
                book={b}
                onOpen={() => onOpen(b.id)}
                onRead={() => onRead(b.id)}
                onReindex={() => onReindex(b.id)}
                onDelete={() => onDelete(b)}
                onResetReading={() => onResetReading(b)}
              />
            ))}
          </div>
        )}
      </div>

      {dragging && (
        <div className="pointer-events-none absolute inset-3 z-40 flex items-center justify-center rounded-2xl border-2 border-dashed border-brand-500 bg-brand-50/80 dark:bg-brand-900/40">
          <p className="text-lg font-medium text-brand-700 dark:text-brand-200">Drop to upload</p>
        </div>
      )}
    </div>
  );
}
