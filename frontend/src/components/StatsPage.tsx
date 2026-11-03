import { BarChart3, BookCheck, Clock, Flame, GraduationCap, Layers } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Stats } from "../types";
import { EmptyState, ErrorBox } from "./ui";

export function formatDuration(seconds: number): string {
  if (seconds < 60) return seconds ? "<1 min" : "0 min";
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h} h ${m % 60} min` : `${h} h`;
}

function Tile({ icon, label, value, sub }: { icon: JSX.Element; label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
      <p className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-stone-500 uppercase">
        {icon} {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-stone-500">{sub}</p>}
    </div>
  );
}

/** Minutes read per day for the last 30 days. */
function DailyChart({ daily }: { daily: Stats["daily"] }) {
  const max = Math.max(...daily.map((d) => d.seconds), 60);
  const label = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return (
    <div>
      <div className="flex h-36 items-end gap-[3px]" role="img" aria-label="Minutes read per day, last 30 days">
        {daily.map((d, i) => (
          <div key={d.day} className="group relative flex h-full flex-1 items-end">
            <div
              className={`w-full rounded-t-sm ${i === daily.length - 1 ? "bg-brand-500" : "bg-brand-300 dark:bg-brand-700"} ${d.seconds ? "" : "!bg-stone-200 dark:!bg-stone-800"}`}
              style={{ height: d.seconds ? `${Math.max((d.seconds / max) * 100, 4)}%` : "2px" }}
            />
            <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 rounded bg-stone-900 px-2 py-1 text-xs whitespace-nowrap text-white group-hover:block dark:bg-stone-100 dark:text-stone-900">
              {label(d.day)}: {formatDuration(d.seconds)}
              {d.cards ? ` · ${d.cards} cards` : ""}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-stone-400">
        <span>{label(daily[0].day)}</span>
        <span>Today</span>
      </div>
    </div>
  );
}

export default function StatsPage({ onOpenBook }: { onOpenBook: (id: number) => void }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.stats().then(setStats).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight">Reading stats</h1>
        <p className="text-sm text-stone-500">Time counts only while the reader is open and you're actually reading.</p>
        {error && <div className="mt-4"><ErrorBox>{error}</ErrorBox></div>}
        {stats && stats.total_seconds === 0 && stats.flashcards.reviews === 0 && stats.quizzes.attempts === 0 && (
          <EmptyState icon={<BarChart3 size={22} />} title="No reading recorded yet">
            Open a book in the reader and start reading; your time, streak and progress will show up here.
          </EmptyState>
        )}
        {stats && (
          <>
            <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Tile icon={<Clock size={14} />} label="Today" value={formatDuration(stats.today_seconds)} sub={`${formatDuration(stats.week_seconds)} this week`} />
              <Tile icon={<Flame size={14} />} label="Streak" value={`${stats.streak_days} day${stats.streak_days === 1 ? "" : "s"}`} sub={`Best: ${stats.best_streak_days} · ${stats.active_days} reading days`} />
              <Tile icon={<BookCheck size={14} />} label="Books finished" value={String(stats.books_finished)} sub={`${formatDuration(stats.total_seconds)} read in total`} />
              <Tile
                icon={<GraduationCap size={14} />}
                label="Quizzes"
                value={stats.quizzes.average === null ? "–" : `${Math.round(stats.quizzes.average * 100)}%`}
                sub={`${stats.quizzes.attempts} attempt${stats.quizzes.attempts === 1 ? "" : "s"} · average score`}
              />
            </div>

            <section className="mt-5 rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
              <h2 className="mb-3 text-sm font-medium">Last 30 days</h2>
              <DailyChart daily={stats.daily} />
            </section>

            <section className="mt-5 rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
              <h2 className="flex items-center gap-1.5 text-sm font-medium">
                <Layers size={14} /> Flashcards
              </h2>
              <p className="mt-1 text-sm text-stone-600 dark:text-stone-300">
                {stats.flashcards.total} cards · {stats.flashcards.mastered} mastered (3+ weeks between reviews) · {stats.flashcards.due} due now ·{" "}
                {stats.flashcards.reviews} reviews done
              </p>
            </section>

            {stats.books.length > 0 && (
              <section className="mt-5">
                <h2 className="mb-2 text-sm font-medium text-stone-500">Your books</h2>
                <ul className="divide-y divide-stone-100 rounded-xl border border-stone-200 bg-white dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900">
                  {stats.books.map((b) => (
                    <li key={b.id}>
                      <button onClick={() => onOpenBook(b.id)} className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-left hover:bg-stone-50 dark:hover:bg-stone-800/50">
                        <span className="min-w-0 flex-1 basis-48">
                          <span className="block truncate font-medium">{b.title}</span>
                          <span className="block truncate text-xs text-stone-500">{b.author ?? ""}</span>
                        </span>
                        <span className="w-40">
                          <span className="block h-1.5 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-700">
                            <span className={`block h-full ${b.finished ? "bg-emerald-500" : "bg-brand-500"}`} style={{ width: `${b.chapters ? (b.furthest / b.chapters) * 100 : 0}%` }} />
                          </span>
                          <span className="mt-0.5 block text-xs text-stone-500">
                            {b.finished ? "Finished" : b.furthest ? `Ch. ${b.furthest} of ${b.chapters}` : "Not started"}
                          </span>
                        </span>
                        <span className="w-20 text-right text-sm tabular-nums">{formatDuration(b.seconds)}</span>
                        <span className="w-24 text-right text-xs text-stone-500">{b.highlights} highlight{b.highlights === 1 ? "" : "s"}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
