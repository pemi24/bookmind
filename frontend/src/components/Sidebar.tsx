import {
  AlertTriangle,
  BarChart3,
  ChevronUp,
  Compass,
  Library as LibraryIcon,
  Loader2,
  LogOut,
  MonitorSmartphone,
  Moon,
  Settings,
  ShieldCheck,
  Sun,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import Logo from "../landing/brand/Logo";
import type { Book, User } from "../types";
import { isIndexing } from "../utils";

export type Page = "library" | "discover" | "stats" | "settings" | "admin";

const NAV: { page: Page; label: string; icon: typeof LibraryIcon; hash: string }[] = [
  { page: "library", label: "Library", icon: LibraryIcon, hash: "#/" },
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
  user,
  onSignOut,
  onNavigateAccount,
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
  user: User;
  onSignOut: (everywhere?: boolean) => void;
  onNavigateAccount: (hash: string) => void;
  onClose?: () => void; // shown in the mobile drawer
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <nav className="flex h-full flex-col border-r border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900">
      <div className="flex items-center gap-2 px-4 py-3">
        <button onClick={() => onNavigate("#/")} className="flex items-center rounded-lg" aria-label="BookMind, your library">
          <Logo size={26} />
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
        <UserMenu user={user} onSignOut={onSignOut} onNavigate={onNavigateAccount} />
      </div>
    </nav>
  );
}

function initials(user: User): string {
  const words = (user.display_name || user.email).split(/[\s@._-]+/).filter(Boolean);
  return ((words[0]?.[0] ?? "") + (words[1]?.[0] ?? "")).toUpperCase() || "?";
}

/** Who is signed in, with sign-out (here, or on every device). */
function UserMenu({ user, onSignOut, onNavigate }: { user: User; onSignOut: (everywhere?: boolean) => void; onNavigate: (hash: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const item = "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-stone-100 dark:hover:bg-stone-800";
  return (
    <div ref={ref} className="relative">
      {open && (
        <div
          role="menu"
          className="absolute right-0 bottom-full left-0 mb-1 rounded-lg border border-stone-200 bg-white p-1 shadow-lg dark:border-stone-700 dark:bg-stone-900"
        >
          <div className="px-3 py-2 text-xs text-stone-500">
            Signed in as
            <div className="truncate text-sm font-medium text-stone-800 dark:text-stone-100">{user.email}</div>
          </div>
          <button role="menuitem" onClick={() => (setOpen(false), onNavigate("#/settings"))} className={item}>
            <Settings size={15} /> Settings
          </button>
          {user.is_admin && (
            <button role="menuitem" onClick={() => (setOpen(false), onNavigate("#/admin"))} className={item}>
              <ShieldCheck size={15} /> Admin
            </button>
          )}
          <div className="my-1 border-t border-stone-200 dark:border-stone-700" />
          <button role="menuitem" onClick={() => onSignOut(false)} className={item}>
            <LogOut size={15} /> Sign out
          </button>
          <button
            role="menuitem"
            onClick={() => confirm("Sign out of BookMind on every device, including this one?") && onSignOut(true)}
            className={item}
          >
            <MonitorSmartphone size={15} /> Sign out everywhere
          </button>
        </div>
      )}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-stone-100 dark:hover:bg-stone-800"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-semibold text-white">
          {initials(user)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{user.display_name || user.email.split("@")[0]}</span>
          <span className="block truncate text-xs text-stone-500">{user.email}</span>
        </span>
        <ChevronUp size={16} className={`shrink-0 text-stone-400 transition ${open ? "" : "rotate-180"}`} />
      </button>
    </div>
  );
}
