import { useCallback, useMemo, useState } from "react";
import { api } from "../../api";
import type { TimelineEvent } from "../../types";
import { chapterLabel, useWorkspace } from "../../workspace";
import { ErrorBox, JobProgress, PanelShell, Segmented } from "../ui";
import { AnalysisGate, useAnalysis } from "./ExplorerPanel";

export default function TimelinePanel() {
  const { book, chapters, maxChapter, openPassage } = useWorkspace();
  const load = useCallback(() => api.timeline(book.id, maxChapter), [book.id, maxChapter]);
  const { data, error, running, job, start, starting } = useAnalysis(load);
  const [filter, setFilter] = useState<"key" | "all">("all");

  const events = (data?.events ?? []).filter((e) => filter === "all" || e.importance >= 4);
  const groups = useMemo(() => {
    const g = new Map<number, TimelineEvent[]>();
    for (const e of events) {
      const k = e.chapter_position ?? 0;
      g.set(k, [...(g.get(k) ?? []), e]);
    }
    return [...g.entries()];
  }, [events]);

  const hasData = (data?.events.length ?? 0) > 0;

  return (
    <PanelShell
      title="Timeline"
      actions={hasData && <Segmented value={filter} onChange={setFilter} label="Events shown" options={[{ value: "all", label: "All events" }, { value: "key", label: "Key events" }]} />}
    >
      {error && <ErrorBox>{error}</ErrorBox>}
      {!data && !error && <p className="text-sm text-stone-500">Loading…</p>}
      {data && !hasData && <AnalysisGate data={data} running={running} job={job} start={start} starting={starting} what="timeline" />}
      {running && hasData && job && <div className="mb-4"><JobProgress job={job} label="Re-analyzing the book…" /></div>}

      {hasData && (
        <div className="relative">
          <div className="absolute top-0 bottom-0 left-[7px] w-0.5 bg-stone-200 dark:bg-stone-800" aria-hidden />
          {groups.map(([pos, evs]) => (
            <section key={pos} className="mb-6">
              <h3 className="relative mb-3 flex items-center gap-3 pl-0 text-sm font-semibold">
                <span className="z-10 h-4 w-4 rounded-full border-4 border-stone-50 bg-stone-400 dark:border-stone-950" />
                {chapterLabel(chapters, pos)}
              </h3>
              <ol className="space-y-3 pl-7">
                {evs.map((e) => (
                  <li key={e.id} className="relative">
                    <span
                      className={`absolute top-3 -left-[25px] h-2.5 w-2.5 rounded-full ${e.importance >= 4 ? "bg-brand-600" : "bg-stone-300 dark:bg-stone-600"}`}
                      aria-hidden
                    />
                    <button
                      onClick={() => e.chapter_id && openPassage({ chapter_id: e.chapter_id, char_start: e.char_start ?? undefined, char_end: e.char_end ?? undefined })}
                      disabled={!e.chapter_id}
                      className="w-full rounded-xl border border-stone-200 bg-white p-3 text-left transition hover:border-brand-400 hover:shadow-sm dark:border-stone-800 dark:bg-stone-900"
                    >
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        <p className={`font-medium ${e.importance >= 4 ? "" : "text-stone-700 dark:text-stone-300"}`}>{e.title}</p>
                        {e.when && <span className="text-xs text-brand-600 dark:text-brand-300">{e.when}</span>}
                      </div>
                      <p className="mt-0.5 text-sm text-stone-600 dark:text-stone-400">{e.description}</p>
                      {e.page && <p className="mt-1 text-xs text-stone-400">p. {e.page} · open in reader</p>}
                    </button>
                  </li>
                ))}
              </ol>
            </section>
          ))}
          {maxChapter !== null && <p className="pl-7 text-xs text-stone-500">Spoiler guard on: events after chapter {maxChapter} are hidden.</p>}
        </div>
      )}
    </PanelShell>
  );
}
