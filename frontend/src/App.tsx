import {
  AlertTriangle,
  BookOpenText,
  CalendarRange,
  EyeOff,
  FileText,
  GraduationCap,
  Loader2,
  Menu,
  MessageSquare,
  Network,
  NotebookPen,
  PenLine,
  Quote,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { account, api, watchProgress } from "./api";
import AdminPage from "./components/AdminPage";
import BookMemory from "./components/BookMemory";
import ChatPanel from "./components/ChatPanel";
import Discover from "./components/Discover";
import Library from "./components/Library";
import EssayPanel from "./components/panels/EssayPanel";
import ExplorerPanel from "./components/panels/ExplorerPanel";
import NotesPanel from "./components/panels/NotesPanel";
import QuotesPanel from "./components/panels/QuotesPanel";
import StudyPanel from "./components/panels/StudyPanel";
import SummariesPanel from "./components/panels/SummariesPanel";
import TimelinePanel from "./components/panels/TimelinePanel";
import ReaderPanel, { type ReaderTarget } from "./components/ReaderPanel";
import SettingsPage from "./components/SettingsPage";
import Sidebar, { type Page } from "./components/Sidebar";
import StatsPage from "./components/StatsPage";
import type { Book, ChapterInfo, Health, NewNote, PassageLoc, Reading, Source, User } from "./types";
import { applyTheme, isIndexing, loadPref, savePref, spoilerLimit, type Spoiler } from "./utils";
import { WorkspaceContext, type Workspace } from "./workspace";

/* ---------- hash router: #/  ·  #/discover|stats|settings|admin  ·  #/book/:id[/:tab]  ·  #/book/:id/read?c=&s=&e= ---------- */
const TABS = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "summaries", label: "Summaries", icon: FileText },
  { id: "study", label: "Study", icon: GraduationCap },
  { id: "explore", label: "Explore", icon: Network },
  { id: "timeline", label: "Timeline", icon: CalendarRange },
  { id: "quotes", label: "Quotes", icon: Quote },
  { id: "essay", label: "Essay", icon: PenLine },
  { id: "notes", label: "Notes", icon: NotebookPen },
] as const;
type Tab = (typeof TABS)[number]["id"];

type Route =
  | { name: "page"; page: Page }
  | { name: "book"; id: number; tab: Tab; read: boolean; target: PassageLoc | null };

function parseHash(): Route {
  const page = window.location.hash.match(/^#\/(discover|stats|settings|admin)\/?$/); // anything else (incl. the old #/search) → library
  if (page) return { name: "page", page: page[1] as Page };
  const m = window.location.hash.match(/^#\/book\/(\d+)(?:\/([a-z]+))?(?:\?(.*))?$/);
  if (!m) return { name: "page", page: "library" };
  const seg = m[2] ?? "chat";
  const read = seg === "read";
  const tab = (TABS.some((t) => t.id === seg) ? seg : "chat") as Tab;
  const q = new URLSearchParams(m[3] ?? "");
  const c = Number(q.get("c"));
  const target = c ? { chapter_id: c, char_start: q.has("s") ? Number(q.get("s")) : undefined, char_end: q.has("e") ? Number(q.get("e")) : undefined } : null;
  return { name: "book", id: Number(m[1]), tab, read, target };
}

function useRoute(): [Route, (hash: string) => void] {
  const [route, setRoute] = useState(parseHash);
  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return [route, (hash: string) => (window.location.hash = hash)];
}

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    // Settings can change the theme too: follow the page itself.
    const html = document.documentElement;
    const obs = new MutationObserver(() => setDark(html.classList.contains("dark")));
    obs.observe(html, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  const toggle = () => {
    const next = dark ? "light" : "dark";
    applyTheme(next);
    account.updatePreferences({ theme: next }).catch(() => {}); // follows you to other devices
  };
  return { dark, toggle };
}

function SpoilerControl({
  chapters,
  value,
  furthest,
  onChange,
}: {
  chapters: ChapterInfo[];
  value: Spoiler;
  furthest: number;
  onChange: (v: Spoiler) => void;
}) {
  return (
    <label
      className={`flex max-w-[16rem] min-w-0 items-center gap-1.5 rounded-lg border px-2 py-1 text-xs ${
        value !== null ? "border-amber-400 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200" : "border-stone-300 text-stone-600 dark:border-stone-700 dark:text-stone-300"
      }`}
      title="Spoiler guard: nothing after this chapter is ever retrieved or shown"
    >
      <EyeOff size={14} className="shrink-0" />
      <span className="hidden lg:inline">Read up to</span>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "follow" ? "follow" : e.target.value ? Number(e.target.value) : null)}
        className="min-w-0 flex-1 truncate bg-transparent outline-none"
        aria-label="Spoiler guard: chapters read"
      >
        <option value="">Whole book (no spoiler guard)</option>
        <option value="follow">Follow my reading (Ch. {furthest})</option>
        {chapters.map((c) => (
          <option key={c.id} value={c.position}>
            Ch. {c.position}: {c.title}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function App({ user, onUser, onSignOut }: { user: User; onUser: (u: User) => void; onSignOut: (everywhere?: boolean) => void }) {
  const { dark, toggle } = useTheme();
  const [route, navigate] = useRoute();
  const [books, setBooks] = useState<Book[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [reader, setReader] = useState<{ open: boolean; target: ReaderTarget | null }>({ open: false, target: null });
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [spoiler, setSpoilerState] = useState<Spoiler>(null);
  const [notesKey, setNotesKey] = useState(0);
  const [health, setHealth] = useState<Health | null>(null);
  const watchers = useRef(new Map<number, () => void>());

  // AI model status (e.g. "Ollama isn't running"); re-checked every 20 s until it's ready.
  const checkHealth = useCallback(() => api.health().then(setHealth).catch(() => {}), []);
  useEffect(() => {
    checkHealth();
  }, [checkHealth]);
  useEffect(() => {
    if (!health || health.llm.ready) return;
    const t = window.setInterval(checkHealth, 20000);
    return () => window.clearInterval(t);
  }, [health, checkHealth]);

  const bookId = route.name === "book" ? route.id : null;
  const book = books.find((b) => b.id === bookId) ?? null;
  const readMode = route.name === "book" && route.read;
  const tab: Tab = route.name === "book" ? route.tab : "chat";

  const notify = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((t) => (t === msg ? null : t)), 7000);
  }, []);

  const refreshBooks = useCallback(async () => {
    try {
      setBooks(await api.books());
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setLoaded(true);
    }
  }, [notify]);

  useEffect(() => {
    refreshBooks();
    // Pick up books added or changed from another tab (at most every 10 s).
    let last = Date.now();
    const onFocus = () => {
      if (Date.now() - last > 10_000) {
        last = Date.now();
        refreshBooks();
      }
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshBooks]);

  const reloadBook = useCallback((id: number) => {
    api.book(id).then((nb) => setBooks((bs) => bs.map((x) => (x.id === nb.id ? nb : x)))).catch(() => {});
  }, []);

  // Live progress (SSE) for every book that is indexing.
  useEffect(() => {
    for (const b of books) {
      if (isIndexing(b.status) && !watchers.current.has(b.id)) {
        const stop = watchProgress(b.id, (p) => {
          setBooks((bs) =>
            bs.map((x) => (x.id === b.id ? { ...x, status: p.status as Book["status"], progress: p.progress, status_message: p.message, error: p.error } : x)),
          );
          if (p.status === "ready" || p.status === "failed") {
            watchers.current.delete(b.id);
            reloadBook(b.id);
            window.setTimeout(() => reloadBook(b.id), 20000); // suggested questions arrive shortly after
          }
        });
        watchers.current.set(b.id, stop);
      }
    }
  }, [books, reloadBook]);

  useEffect(() => () => watchers.current.forEach((stop) => stop()), []);

  // Per-book state: chapters + spoiler limit (remembered).
  const bookReady = book?.status === "ready";
  useEffect(() => {
    setChapters([]);
    setSpoilerState(bookId ? loadPref<Spoiler>(`spoiler:${bookId}`, null) : null);
    if (bookId && bookReady) api.chapters(bookId).then(setChapters).catch(() => {});
  }, [bookId, bookReady]);

  const setSpoiler = (v: Spoiler) => {
    setSpoilerState(v);
    if (bookId) savePref(`spoiler:${bookId}`, v);
  };
  // "Follow my reading" = nothing past the furthest chapter actually read (chapter 1 before you start).
  const furthestRead = book?.reading?.furthest ?? 1;
  const maxChapter = book ? spoilerLimit(book, spoiler) : null;

  const setReading = useCallback((id: number, reading: Reading | null) => {
    setBooks((bs) => bs.map((b) => (b.id === id ? { ...b, reading } : b)));
  }, []);

  const resetReading = async (b: Book) => {
    if (!confirm(`Start “${b.title}” over? This forgets where you stopped and which chapters you've read. Highlights and notes are kept.`)) return;
    try {
      await api.resetReading(b.id);
      setReading(b.id, null);
    } catch (e) {
      notify((e as Error).message);
    }
  };

  // Reader: reset when switching books, unless we switched to open a passage there.
  const pendingTarget = useRef<ReaderTarget | null>(null);
  useEffect(() => {
    const t = pendingTarget.current;
    pendingTarget.current = null;
    setReader(t ? { open: true, target: t } : { open: false, target: null });
  }, [bookId]);
  // Deep links (#/book/1/read?c=..&s=..&e=..) open the reader at that passage.
  const routeTarget = route.name === "book" ? route.target : null;
  const routeTargetKey = routeTarget ? `${routeTarget.chapter_id}:${routeTarget.char_start}:${routeTarget.char_end}` : "";
  useEffect(() => {
    if (readMode) {
      setReader((r) => ({
        open: true,
        target: routeTarget
          ? { chapterId: routeTarget.chapter_id, highlight: routeTarget.char_start !== undefined && routeTarget.char_end !== undefined ? { start: routeTarget.char_start, end: routeTarget.char_end } : undefined, nonce: Date.now() }
          : r.target,
      }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readMode, routeTargetKey]);
  useEffect(() => setDrawer(false), [route]);

  const upload = async (files: FileList | File[]) => {
    let last: number | null = null;
    const list = Array.from(files);
    for (const f of list) {
      try {
        const b = await api.upload(f);
        setBooks((bs) => [b, ...bs]);
        last = b.id;
      } catch (e) {
        notify(`${f.name}: ${(e as Error).message}`);
      }
    }
    if (last !== null && list.length === 1) navigate(`#/book/${last}`);
  };

  const remove = async (b: Book) => {
    if (!confirm(`Delete “${b.title}” and all its chats, notes, quizzes and analysis? This cannot be undone.`)) return;
    try {
      await api.deleteBook(b.id);
      setBooks((bs) => bs.filter((x) => x.id !== b.id));
      if (bookId === b.id) navigate("#/");
    } catch (e) {
      notify((e as Error).message);
    }
  };

  const reindex = async (id: number) => {
    try {
      await api.reindex(id);
      setBooks((bs) => bs.map((b) => (b.id === id ? { ...b, status: "pending", progress: 0, error: null, status_message: "Queued" } : b)));
      if (id === bookId) setReader({ open: false, target: null });
    } catch (e) {
      notify((e as Error).message);
    }
  };

  const openPassage = useCallback(
    (loc: PassageLoc) => {
      const target: ReaderTarget = {
        chapterId: loc.chapter_id,
        highlight: loc.char_start !== undefined && loc.char_end !== undefined ? { start: loc.char_start, end: loc.char_end } : undefined,
        nonce: Date.now(),
      };
      if (loc.book_id && loc.book_id !== bookId) {
        pendingTarget.current = target; // compare mode can cite another book
        navigate(`#/book/${loc.book_id}`);
      } else {
        setReader({ open: true, target });
      }
    },
    [bookId, navigate],
  );

  const saveNote = useCallback(
    async (note: NewNote) => {
      if (!bookId) return;
      try {
        await api.createNote(bookId, note);
        setNotesKey((k) => k + 1);
        notify("Saved to notes.");
      } catch (e) {
        notify((e as Error).message);
      }
    },
    [bookId, notify],
  );

  const workspace = useMemo<Workspace | null>(
    () => (book ? { book, books, chapters, maxChapter, openPassage, saveNote, notify, user } : null),
    [book, books, chapters, maxChapter, openPassage, saveNote, notify, user],
  );

  const closeReader = () => {
    setReader({ open: false, target: null });
    if (readMode && bookId) navigate(`#/book/${bookId}`);
  };

  const sidebar = (inDrawer: boolean) => (
    <Sidebar
      books={books}
      selectedId={bookId}
      page={route.name === "page" ? route.page : null}
      onNavigate={navigate}
      onSelect={(id) => navigate(`#/book/${id}`)}
      onUpload={upload}
      dark={dark}
      onToggleTheme={toggle}
      user={user}
      onSignOut={onSignOut}
      onNavigateAccount={navigate}
      onClose={inDrawer ? () => setDrawer(false) : undefined}
    />
  );

  const menuButton = (
    <button onClick={() => setDrawer(true)} className="rounded-md p-2 text-stone-600 hover:bg-stone-100 md:hidden dark:text-stone-300 dark:hover:bg-stone-800" aria-label="Open menu">
      <Menu size={18} />
    </button>
  );

  const panel = (() => {
    switch (tab) {
      case "summaries":
        return <SummariesPanel />;
      case "study":
        return <StudyPanel />;
      case "explore":
        return <ExplorerPanel dark={dark} />;
      case "timeline":
        return <TimelinePanel />;
      case "quotes":
        return <QuotesPanel />;
      case "notes":
        return <NotesPanel refreshKey={notesKey} />;
      case "essay":
        return <EssayPanel />;
      default:
        return <ChatPanel onCite={(s: Source) => openPassage(s)} />;
    }
  })();

  return (
    <div className="flex h-full">
      <div className="hidden w-64 shrink-0 md:block">{sidebar(false)}</div>
      {drawer && (
        <div className="fixed inset-0 z-50 flex md:hidden">
          <div className="w-72 max-w-[85%] shadow-xl">{sidebar(true)}</div>
          <button className="flex-1 bg-black/40" onClick={() => setDrawer(false)} aria-label="Close menu" />
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        {health && !health.llm.ready && (
          <div role="alert" className="flex flex-wrap items-start gap-2 border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-100">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <div className="min-w-0 flex-1">
              <span className="font-medium">AI model not ready ({health.llm.provider} · {health.llm.model}).</span>{" "}
              <span className="break-words">{health.llm.message}</span>{" "}
              <span className="text-amber-700 dark:text-amber-300">Reading, search and the library still work.</span>
            </div>
            <button onClick={checkHealth} className="shrink-0 rounded-md border border-amber-400 px-2 py-0.5 text-xs hover:bg-amber-100 dark:hover:bg-amber-900">
              Check again
            </button>
          </div>
        )}
        {route.name === "page" && (
          <>
            <div className="flex items-center gap-2 border-b border-stone-200 px-2 py-1.5 md:hidden dark:border-stone-800">
              {menuButton}
              <span className="font-semibold">BookMind</span>
            </div>
            <div className="min-h-0 flex-1">
              {route.page === "discover" && <Discover books={books} onAdded={(b) => setBooks((bs) => [b, ...bs])} />}
              {route.page === "stats" && <StatsPage onOpenBook={(id) => navigate(`#/book/${id}`)} />}
              {route.page === "settings" && <SettingsPage user={user} onUser={onUser} onSignOut={onSignOut} />}
              {route.page === "admin" && (user.is_admin ? <AdminPage /> : <p className="p-6 text-center text-stone-500">This page doesn't exist.</p>)}
              {route.page === "library" && loaded && (
                <Library
                  books={books}
                  onUpload={upload}
                  onOpen={(id) => navigate(`#/book/${id}`)}
                  onRead={(id) => navigate(`#/book/${id}/read`)}
                  onReindex={reindex}
                  onDelete={remove}
                  onResetReading={resetReading}
                  onOpenPassage={openPassage}
                />
              )}
            </div>
          </>
        )}

        {route.name === "book" && !book && loaded && (
          <div className="m-auto p-6 text-center">
            <p className="font-medium">This book doesn't exist (it may have been deleted).</p>
            <button onClick={() => navigate("#/")} className="mt-3 text-brand-600 hover:underline">
              Back to library
            </button>
          </div>
        )}

        {book && workspace && (
          <WorkspaceContext.Provider value={workspace}>
            <header className="flex flex-wrap items-center gap-2 border-b border-stone-200 px-2 py-2 sm:px-4 dark:border-stone-800">
              {menuButton}
              <div className="min-w-0 flex-1">
                <h1 className="truncate font-semibold">{book.title}</h1>
                <p className="truncate text-xs text-stone-500">
                  {[book.author, book.chapter_count ? `${book.chapter_count} chapters` : null, book.page_count ? `${book.page_count}${book.pages_estimated ? " est." : ""} pages` : null]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              {bookReady && chapters.length > 0 && <SpoilerControl chapters={chapters} value={spoiler} furthest={furthestRead} onChange={setSpoiler} />}
              {bookReady && <BookMemory bookId={book.id} notify={notify} />}
              <div className="flex shrink-0 items-center gap-1">
                <button
                  onClick={() => (reader.open ? closeReader() : setReader((r) => ({ ...r, open: true })))}
                  disabled={!bookReady}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm transition disabled:opacity-30 ${
                    reader.open ? "bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-200" : "text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800"
                  }`}
                  title="Read the book side by side"
                >
                  <BookOpenText size={16} /> <span className="hidden sm:inline">Read</span>
                </button>
                <button onClick={() => reindex(book.id)} disabled={isIndexing(book.status)} className="rounded-md p-2 text-stone-500 hover:bg-stone-100 disabled:opacity-30 dark:hover:bg-stone-800" title="Re-index">
                  <RefreshCw size={16} />
                </button>
                <button onClick={() => remove(book)} disabled={book.status === "processing"} className="rounded-md p-2 text-stone-500 hover:bg-stone-100 hover:text-red-600 disabled:opacity-30 dark:hover:bg-stone-800" title="Delete book">
                  <Trash2 size={16} />
                </button>
              </div>
            </header>

            {bookReady && !readMode && (
              <nav className="flex gap-0.5 overflow-x-auto border-b border-stone-200 px-2 sm:px-4 dark:border-stone-800" aria-label="Book tools">
                {TABS.map((t) => (
                  <a
                    key={t.id}
                    href={`#/book/${book.id}${t.id === "chat" ? "" : `/${t.id}`}`}
                    aria-current={tab === t.id ? "page" : undefined}
                    className={`flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm transition ${
                      tab === t.id
                        ? "border-brand-600 font-medium text-brand-700 dark:text-brand-300"
                        : "border-transparent text-stone-500 hover:text-stone-800 dark:hover:text-stone-200"
                    }`}
                  >
                    <t.icon size={15} /> {t.label}
                  </a>
                ))}
              </nav>
            )}

            {book.warnings.length > 0 && bookReady && tab === "chat" && !readMode && (
              <div className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                <div>{book.warnings.join(" ")}</div>
              </div>
            )}

            <div className="flex min-h-0 flex-1">
              {!readMode && (
                <div className="min-w-0 flex-1">
                  {bookReady ? (
                    panel
                  ) : book.status === "failed" ? (
                    <div className="mx-auto mt-20 max-w-md px-4 text-center">
                      <AlertTriangle className="mx-auto text-red-500" />
                      <p className="mt-3 font-medium">Indexing failed</p>
                      <p className="mt-1 text-sm text-stone-500">{book.error}</p>
                      <button onClick={() => reindex(book.id)} className="mt-4 rounded-lg bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700">
                        Try again
                      </button>
                    </div>
                  ) : (
                    <div className="mx-auto mt-20 max-w-md px-4 text-center">
                      <Loader2 className="mx-auto animate-spin text-brand-500" />
                      <p className="mt-3 font-medium">Indexing “{book.title}”</p>
                      <div className="mt-4 h-2 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-800">
                        <div className="h-full bg-brand-500 transition-all" style={{ width: `${Math.round(book.progress * 100)}%` }} />
                      </div>
                      <p className="mt-2 text-sm text-stone-500">
                        {Math.round(book.progress * 100)}% · {book.status_message ?? "Queued"}
                      </p>
                      <p className="mt-4 text-xs text-stone-400">You can keep using other books while this one indexes.</p>
                    </div>
                  )}
                </div>
              )}
              {reader.open && bookReady && (
                <div className={readMode ? "min-w-0 flex-1" : "fixed inset-0 z-40 md:static md:z-auto md:w-[44%] md:max-w-2xl md:shrink-0"}>
                  <ReaderPanel
                    bookId={book.id}
                    target={reader.target}
                    resume={book.reading}
                    expanded={readMode}
                    onToggleExpand={() => navigate(readMode ? `#/book/${book.id}` : `#/book/${book.id}/read`)}
                    onClose={closeReader}
                    onReading={(r) => setReading(book.id, r)}
                    onNotesChanged={() => setNotesKey((k) => k + 1)}
                    notify={notify}
                  />
                </div>
              )}
            </div>
          </WorkspaceContext.Provider>
        )}
      </main>

      {toast && (
        <div role="status" className="fixed right-4 bottom-4 left-4 z-50 flex items-start gap-2 rounded-lg bg-stone-900 px-4 py-3 text-sm text-white shadow-lg sm:left-auto sm:max-w-sm dark:bg-stone-100 dark:text-stone-900">
          <span className="flex-1">{toast}</span>
          <button onClick={() => setToast(null)} className="opacity-70 hover:opacity-100" aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
