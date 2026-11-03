import { AlertTriangle, BarChart3, BookOpen, Compass, Library as LibraryIcon, Loader2, Moon, Search, Smartphone, Sun, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import type { Book } from "../types";
import { isIndexing } from "../utils";
import PhoneAccess from "./PhoneAccess";

export type Page = "library" | "discover" | "search" | "stats";

const NAV: { page: Page; label: string; icon: typeof LibraryIcon; hash: string }[] = [
  { page: "library", label: "Library", icon: LibraryIcon, hash: "#/" },
  { page: "search", label: "Search library", icon: Search, hash: "#/search" },
  { page: "discover", label: "Find free books", icon: Compass, hash: "#/discover" },
  { page: "stats", label: "Reading stats", icon: BarChart3, hash: "#/stats" },
];

export default function Sidebar({
  books,
  selectedId,
  page,
  onNavigate,
  onSelect,
  onUpload,
  dark,
  onToggleTheme,
  onClose,
}: {
  books: Book[];
  selectedId: number | null;
  /** The top-level page shown, or null while a book is open. */
  page: Page | null;
  onNavigate: (hash: string) => void;
  onSelect: (id: number) => void;
  onUpload: (files: File[]) => void;
  dark: boolean;
  onToggleTheme: () => void;
  onClose?: () => void; // shown in the mobile drawer
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [phone, setPhone] = useState(false);
  return (
    <nav className="flex h-full flex-col border-r border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900">
      <div className="flex items-center gap-2 px-4 py-3">
        <button onClick={() => onNavigate("#/")} className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
            <BookOpen size={18} />
          </span>
          <span className="text-lg font-semibold tracking-tight">BookMind</span>
        </button>
        <button
          onClick={onToggleTheme}
          className="ml-auto rounded-md p-1.5 text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800"
          title={dark ? "Light mode" : "Dark mode"}
        >
          {dark ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        {onClose && (
          <button onClick={onClose} className="rounded-md p-1.5 text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800" title="Close menu">
            <X size={18} />
          </button>
        )}
      </div>
      <div className="space-y-0.5 px-3">
        {NAV.map(({ page: p, label, icon: Icon, hash }) => (
          <button
            key={p}
            onClick={() => onNavigate(hash)}
            aria-current={page === p ? "page" : undefined}
            className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition ${
              page === p ? "bg-stone-100 dark:bg-stone-800" : "hover:bg-stone-100 dark:hover:bg-stone-800"
            }`}
          >
            <Icon size={16} /> {label}
          </button>
        ))}
        <button
          onClick={() => fileRef.current?.click()}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-brand-700 transition hover:bg-brand-50 dark:text-brand-300 dark:hover:bg-brand-900/30"
        >
          <Upload size={16} /> Upload book
        </button>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".pdf,.epub,.docx,.txt,.md,.markdown"
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) onUpload(Array.from(e.target.files));
            e.target.value = "";
          }}
        />
      </div>
      <div className="mt-4 px-4 text-xs font-medium tracking-wide text-stone-400 uppercase">Books</div>
      <ul className="mt-1 flex-1 overflow-y-auto px-2 pb-3">
        {books.length === 0 && <li className="px-2 py-3 text-sm text-stone-500">No books yet.</li>}
        {books.map((b) => (
          <li key={b.id}>
            <button
              onClick={() => onSelect(b.id)}
              className={`w-full rounded-lg px-2 py-2 text-left transition ${
                b.id === selectedId ? "bg-brand-50 dark:bg-brand-900/30" : "hover:bg-stone-100 dark:hover:bg-stone-800"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{b.title}</span>
                {isIndexing(b.status) && <Loader2 size={14} className="shrink-0 animate-spin text-brand-500" />}
                {b.status === "failed" && <AlertTriangle size={14} className="shrink-0 text-red-500" />}
              </div>
              <div className="truncate text-xs text-stone-500">{b.author ?? b.filename}</div>
              {isIndexing(b.status) && (
                <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-700">
                  <div className="h-full bg-brand-500 transition-all" style={{ width: `${Math.round(b.progress * 100)}%` }} />
                </div>
              )}
            </button>
          </li>
        ))}
      </ul>
      <div className="border-t border-stone-200 p-3 dark:border-stone-800">
        <button
          onClick={() => setPhone(true)}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-stone-600 transition hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800"
        >
          <Smartphone size={16} /> Use on your phone
        </button>
      </div>
      {phone && <PhoneAccess onClose={() => setPhone(false)} />}
    </nav>
  );
}
