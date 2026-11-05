import {
  BookOpen,
  ChevronDown,
  Compass,
  EyeOff,
  FileText,
  FolderOpen,
  GitBranch,
  GraduationCap,
  Headphones,
  Highlighter,
  Languages,
  Layers,
  Lock,
  Mail,
  MessageSquareText,
  PenLine,
  Quote,
  Rss,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  Users,
  WifiOff,
  type LucideIcon,
} from "lucide-react";
import { useId, useRef, useState, type ReactNode } from "react";
import type { IconName } from "../content";
import { useInView } from "./motion";

/* ---------- icons ---------- */

const ICONS: Record<IconName, LucideIcon> = {
  upload: Upload,
  message: MessageSquareText,
  headphones: Headphones,
  book: BookOpen,
  sparkles: Sparkles,
  graduation: GraduationCap,
  compass: Compass,
  folder: FolderOpen,
  shield: ShieldCheck,
  file: FileText,
  quote: Quote,
  users: Users,
  pen: PenLine,
  search: Search,
  timeline: GitBranch,
  "eye-off": EyeOff,
  highlighter: Highlighter,
  layers: Layers,
  "wifi-off": WifiOff,
  languages: Languages,
  lock: Lock,
  github: GitBranch,
  mail: Mail,
  rss: Rss,
};

export function Icon({ name, size = 20, className = "" }: { name: IconName; size?: number; className?: string }) {
  const C = ICONS[name];
  return <C size={size} className={className} aria-hidden="true" />;
}

/* ---------- buttons (links styled as buttons) ---------- */

const base =
  "inline-flex items-center justify-center gap-2 rounded-full font-medium whitespace-nowrap transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export function ButtonLink({
  href,
  children,
  variant = "primary",
  size = "md",
  className = "",
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost";
  size?: "md" | "lg";
  className?: string;
}) {
  const sizes = { md: "px-4 py-2 text-sm", lg: "px-6 py-3 text-base" };
  const variants = {
    primary: "bg-accent text-on-accent shadow-card hover:bg-accent-hover",
    secondary: "border border-line bg-paper-raised text-ink hover:border-ink-muted",
    ghost: "text-ink hover:bg-paper-sunk",
  };
  return (
    <a href={href} className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}>
      {children}
    </a>
  );
}

/* ---------- sections ---------- */

export function Section({
  id,
  title,
  sub,
  children,
  tone = "plain",
  className = "",
}: {
  id?: string;
  title?: string;
  sub?: string;
  children: ReactNode;
  tone?: "plain" | "sunk";
  className?: string;
}) {
  const headingId = useId();
  return (
    <section
      id={id}
      aria-labelledby={title ? headingId : undefined}
      className={`scroll-mt-24 px-5 py-20 sm:px-8 sm:py-28 ${tone === "sunk" ? "bg-paper-sunk" : ""} ${className}`}
    >
      <div className="mx-auto max-w-6xl">
        {title && (
          <Reveal className="mx-auto mb-12 max-w-2xl text-center sm:mb-16">
            <h2
              id={headingId}
              className="font-display text-[clamp(2rem,4.5vw,3.25rem)] leading-[1.08] font-medium tracking-tight text-ink outline-none"
            >
              {title}
            </h2>
            {sub && <p className="mt-4 text-lg leading-relaxed text-ink-muted">{sub}</p>}
          </Reveal>
        )}
        {children}
      </div>
    </section>
  );
}

/** Fades and lifts its content in once it scrolls into view (no movement with reduced motion). */
export function Reveal({
  children,
  className = "",
  delay = 0,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "li";
}) {
  const [ref, seen] = useInView<HTMLDivElement & HTMLLIElement>();
  return (
    <Tag ref={ref} className={`reveal ${seen ? "reveal-in" : ""} ${className}`} style={{ transitionDelay: seen ? `${delay}ms` : undefined }}>
      {children}
    </Tag>
  );
}

/** A small rounded card. */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-[var(--radius-card)] border border-line bg-paper-raised shadow-card ${className}`}>{children}</div>;
}

/* ---------- tabs (WAI-ARIA: arrow keys, Home/End) ---------- */

/** `idPrefix` is shared with the panel: give the panel {...tabPanelProps(idPrefix, value)}. */
export function Tabs<T extends string>({
  label,
  tabs,
  value,
  onChange,
  idPrefix: prefix,
  className = "",
}: {
  label: string;
  tabs: { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
  idPrefix: string;
  className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const move = (i: number) => {
    const n = (i + tabs.length) % tabs.length;
    onChange(tabs[n].id);
    refs.current[n]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className={`flex gap-1 overflow-x-auto rounded-full border border-line bg-paper-raised p-1 ${className}`}>
      {tabs.map((t, i) => {
        const selected = t.id === value;
        return (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            id={`${prefix}-tab-${t.id}`}
            aria-selected={selected}
            aria-controls={`${prefix}-panel`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(t.id)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") move(i + 1);
              else if (e.key === "ArrowLeft") move(i - 1);
              else if (e.key === "Home") move(0);
              else if (e.key === "End") move(tabs.length - 1);
              else return;
              e.preventDefault();
            }}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium whitespace-nowrap transition focus-visible:outline-2 focus-visible:outline-accent ${
              selected ? "bg-accent text-on-accent" : "text-ink-muted hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

export function tabPanelProps(idPrefix: string, selected: string) {
  return { role: "tabpanel", id: `${idPrefix}-panel`, "aria-labelledby": `${idPrefix}-tab-${selected}`, tabIndex: 0 } as const;
}

/* ---------- accordion ---------- */

export function Accordion({ items }: { items: { q: string; a: string }[] }) {
  const [open, setOpen] = useState<number | null>(0);
  const prefix = useId();
  return (
    <div className="divide-y divide-line rounded-[var(--radius-card)] border border-line bg-paper-raised">
      {items.map((item, i) => {
        const expanded = open === i;
        return (
          <div key={item.q}>
            <h3>
              <button
                id={`${prefix}-q${i}`}
                aria-expanded={expanded}
                aria-controls={`${prefix}-a${i}`}
                onClick={() => setOpen(expanded ? null : i)}
                className="flex w-full items-center justify-between gap-4 px-5 py-5 text-left text-base font-medium text-ink transition hover:bg-paper-sunk focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent sm:px-7 sm:text-lg"
              >
                {item.q}
                <ChevronDown
                  size={20}
                  aria-hidden="true"
                  className={`shrink-0 text-ink-muted transition-transform duration-300 ${expanded ? "rotate-180" : ""}`}
                />
              </button>
            </h3>
            <div
              id={`${prefix}-a${i}`}
              role="region"
              aria-labelledby={`${prefix}-q${i}`}
              hidden={!expanded}
              className="px-5 pb-6 text-base leading-relaxed text-ink-muted sm:px-7"
            >
              {item.a}
            </div>
          </div>
        );
      })}
    </div>
  );
}
