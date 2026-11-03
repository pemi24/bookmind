import { Brain, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { MemoryStatus } from "../types";

/** Book memory status in the book header: progress while it's written, a button if it's missing. */
export default function BookMemory({ bookId, notify }: { bookId: number; notify: (msg: string) => void }) {
  const [st, setSt] = useState<MemoryStatus | null>(null);

  const load = useCallback(() => api.memory(bookId).then(setSt).catch(() => setSt(null)), [bookId]);
  useEffect(() => {
    setSt(null);
    load();
  }, [load]);

  const running = st?.job?.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(load, 3000);
    return () => window.clearInterval(t);
  }, [running, load]);

  if (!st || !st.chapters) return null;
  const complete = st.done >= st.chapters;
  const build = async () => {
    try {
      setSt(await api.buildMemory(bookId));
    } catch (e) {
      notify((e as Error).message);
    }
  };

  const tip =
    "Book memory: a short summary of every chapter that the AI reads with each question, so it knows the whole story. " +
    "Chapters past your spoiler limit are never included.";
  if (running)
    return (
      <span className="flex shrink-0 items-center gap-1.5 rounded-lg border border-stone-300 px-2 py-1 text-xs text-stone-600 dark:border-stone-700 dark:text-stone-300" title={tip}>
        <Loader2 size={13} className="animate-spin" /> Memory {st.done}/{st.chapters}
      </span>
    );
  if (complete)
    return (
      <span className="flex shrink-0 items-center gap-1 rounded-lg px-1.5 py-1 text-xs text-emerald-700 dark:text-emerald-400" title={tip}>
        <Brain size={14} /> <span className="hidden lg:inline">Memory ready</span>
      </span>
    );
  return (
    <button
      onClick={build}
      className="flex shrink-0 items-center gap-1.5 rounded-lg border border-brand-300 px-2 py-1 text-xs font-medium text-brand-700 hover:bg-brand-50 dark:border-brand-800 dark:text-brand-300 dark:hover:bg-brand-950/40"
      title={`${tip} ${st.job?.status === "failed" && st.job.error ? `Last attempt failed: ${st.job.error}` : ""}`}
    >
      <Brain size={14} /> {st.done ? `Finish memory (${st.done}/${st.chapters})` : "Build book memory"}
    </button>
  );
}
