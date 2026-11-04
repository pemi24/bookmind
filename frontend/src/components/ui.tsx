import { AlertTriangle, Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChapterInfo, Job } from "../types";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "destructive";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700",
  secondary:
    "border border-stone-300 bg-white text-stone-700 hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-200 dark:hover:bg-stone-800",
  ghost: "text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800",
  danger: "text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40",
  destructive: "bg-red-600 text-white hover:bg-red-700",
};

export function buttonClasses(variant: Variant = "secondary"): string {
  return `inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]}`;
}

export function Button({
  variant = "secondary",
  loading,
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={`${buttonClasses(variant)} ${className}`}
    >
      {loading && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-lg bg-stone-100 p-0.5 text-xs dark:bg-stone-800">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-2.5 py-1 whitespace-nowrap transition ${
            value === o.value
              ? "bg-white font-medium text-stone-900 shadow-sm dark:bg-stone-700 dark:text-white"
              : "text-stone-500 hover:text-stone-800 dark:text-stone-400 dark:hover:text-stone-200"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ChapterSelect({
  chapters,
  value,
  onChange,
  maxChapter,
  allLabel = "Whole book",
}: {
  chapters: ChapterInfo[];
  value: number | null;
  onChange: (id: number | null) => void;
  maxChapter: number | null;
  allLabel?: string;
}) {
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      className="max-w-full min-w-0 truncate rounded-lg border border-stone-300 bg-white px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-900"
      aria-label="Scope"
    >
      <option value="">{maxChapter ? `${allLabel} (up to ch. ${maxChapter})` : allLabel}</option>
      {chapters
        .filter((c) => maxChapter === null || c.position <= maxChapter)
        .map((c) => (
          <option key={c.id} value={c.id}>
            {c.position}. {c.title}
          </option>
        ))}
    </select>
  );
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

export function JobProgress({ job, label }: { job: Job; label: string }) {
  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Loader2 size={16} className="animate-spin text-brand-500" /> {label}
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-800">
        <div className="h-full bg-brand-500 transition-all" style={{ width: `${Math.max(3, Math.round(job.progress * 100))}%` }} />
      </div>
      <p className="mt-1.5 text-xs text-stone-500">{Math.round(job.progress * 100)}% · you can keep using other tabs meanwhile</p>
    </div>
  );
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-answer text-[15px]">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

export function EmptyState({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="mx-auto max-w-md py-12 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-brand-900/40 dark:text-brand-300">
        {icon}
      </div>
      <p className="mt-3 font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-stone-500">{children}</div>}
    </div>
  );
}

export function PanelShell({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-4 py-5 sm:px-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">{title}</h2>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
        {children}
      </div>
    </div>
  );
}

/** Clickable "Ch. 3 · p. 12" location chip. */
export function LocationChip({ chapter, page, onClick }: { chapter: string; page?: number | null; onClick?: () => void }) {
  const text = [chapter, page ? `p. ${page}` : null].filter(Boolean).join(" · ");
  if (!onClick) return <span className="text-xs text-stone-500">{text}</span>;
  return (
    <button onClick={onClick} className="max-w-full truncate text-left text-xs font-medium text-brand-600 hover:underline dark:text-brand-300" title="Open in reader">
      {text}
    </button>
  );
}
