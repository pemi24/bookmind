import { Network, Search, Sparkles, X } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import type { Entity, EntityKind, Job, Mention, Relation } from "../../types";
import { chapterLabel, useJobPolling, useWorkspace } from "../../workspace";
import { Button, EmptyState, ErrorBox, JobProgress, LocationChip, Segmented } from "../ui";
import { KIND_COLORS } from "./kindColors";

// The graph library (Cytoscape) is large: load it only when the graph view is shown.
const EntityGraph = lazy(() => import("./EntityGraph"));

const KIND_LABELS: Record<EntityKind, string> = {
  character: "Characters",
  place: "Places",
  organization: "Groups",
  term: "Terms",
  concept: "Concepts",
  theme: "Themes",
};

/** Shared by Explorer and Timeline: start/poll the one-off book analysis job. */
export function useAnalysis<T extends { job: Job | null }>(load: () => Promise<T>) {
  const { book } = useWorkspace();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setData(await load());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [load]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const running = data?.job?.status === "running";
  const job = useJobPolling(book.id, running ? "analysis" : null, () => refresh());

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      await api.startAnalysis(book.id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  };
  return { data, error, running, job: job ?? data?.job ?? null, start, starting };
}

export function AnalysisGate({
  data,
  running,
  job,
  start,
  starting,
  what,
}: {
  data: { job: Job | null } | null;
  running: boolean;
  job: Job | null;
  start: () => void;
  starting: boolean;
  what: string;
}) {
  const { chapters } = useWorkspace();
  if (running && job) return <JobProgress job={job} label={`Analyzing the book chapter by chapter (${chapters.length} chapters)…`} />;
  return (
    <EmptyState icon={<Sparkles size={22} />} title={`Build the ${what}`}>
      <p>
        BookMind reads each chapter once to extract characters, places, concepts, relationships and key events. This powers
        both the Explorer and the Timeline. It makes one AI request per chapter: about a minute in total with a
        cloud model, or a few minutes per chapter with a local model on a laptop CPU. It runs in the background.
      </p>
      {data?.job?.status === "failed" && <div className="mt-3 text-left"><ErrorBox>Last run failed: {data.job.error}</ErrorBox></div>}
      <Button variant="primary" className="mt-4" onClick={start} loading={starting}>
        Analyze book
      </Button>
    </EmptyState>
  );
}

export default function ExplorerPanel({ dark }: { dark: boolean }) {
  const { book, chapters, maxChapter, openPassage } = useWorkspace();
  const load = useCallback(() => api.entities(book.id, maxChapter), [book.id, maxChapter]);
  const { data, error, running, job, start, starting } = useAnalysis(load);
  const [kind, setKind] = useState<EntityKind | "all">("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [view, setView] = useState<"graph" | "list">(() => (window.innerWidth < 768 ? "list" : "graph"));
  const [mentions, setMentions] = useState<Mention[] | null>(null);

  // Memoized so the empty lists while loading don't change identity on every render (and re-lay out the graph).
  const entities = useMemo(() => data?.entities ?? [], [data]);
  const relations = useMemo(() => data?.relations ?? [], [data]);
  const byId = useMemo(() => new Map(entities.map((e) => [e.id, e])), [entities]);
  const kinds = useMemo(() => [...new Set(entities.map((e) => e.kind))], [entities]);

  const filtered = entities.filter(
    (e) =>
      (kind === "all" || e.kind === kind) &&
      (!query || [e.name, ...e.aliases].some((n) => n.toLowerCase().includes(query.toLowerCase()))),
  );
  const graphEntities = useMemo(() => (kind === "all" ? entities : entities.filter((e) => e.kind === kind)), [entities, kind]);
  const graphRelations = useMemo(() => {
    const ids = new Set(graphEntities.map((e) => e.id));
    return relations.filter((r) => ids.has(r.source) && ids.has(r.target));
  }, [graphEntities, relations]);

  const sel = selected !== null ? byId.get(selected) ?? null : null;

  useEffect(() => {
    setMentions(null);
    if (sel) api.mentions(sel.id, maxChapter).then(setMentions).catch(() => setMentions([]));
  }, [sel, maxChapter]);

  if (!data && !error) return <div className="p-6 text-sm text-stone-500">Loading…</div>;

  const hasData = entities.length > 0;
  const fiction = book.is_fiction !== false;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-stone-200 px-4 py-2 dark:border-stone-800">
        <h2 className="mr-2 font-semibold">{fiction ? "Characters & world" : "Concepts"}</h2>
        {hasData && (
          <>
            <div className="flex items-center gap-1 rounded-lg border border-stone-300 px-2 dark:border-stone-700">
              <Search size={14} className="text-stone-400" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter…" className="w-28 bg-transparent py-1 text-sm outline-none" aria-label="Filter entities" />
            </div>
            <select value={kind} onChange={(e) => setKind(e.target.value as EntityKind | "all")} className="rounded-lg border border-stone-300 bg-white px-2 py-1 text-sm dark:border-stone-700 dark:bg-stone-900" aria-label="Kind">
              <option value="all">All kinds ({entities.length})</option>
              {kinds.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABELS[k]} ({entities.filter((e) => e.kind === k).length})
                </option>
              ))}
            </select>
            <Segmented value={view} onChange={setView} label="View" options={[{ value: "graph", label: fiction ? "Relationship graph" : "Concept map" }, { value: "list", label: "Glossary" }]} />
            <Button variant="ghost" className="ml-auto" onClick={start} loading={starting || running} title="Re-run the analysis">
              <Sparkles size={14} /> Re-analyze
            </Button>
          </>
        )}
      </div>
      {error && <div className="p-4"><ErrorBox>{error}</ErrorBox></div>}
      {running && hasData && job && <div className="p-4"><JobProgress job={job} label="Re-analyzing the book…" /></div>}

      {!hasData ? (
        <div className="overflow-y-auto p-4">
          <AnalysisGate data={data} running={running} job={job} start={start} starting={starting} what={fiction ? "character explorer" : "concept map"} />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <div className="min-h-0 flex-1">
            {view === "graph" ? (
              <div className="relative h-full min-h-[320px]">
                <Suspense fallback={<p className="p-4 text-sm text-stone-500">Loading graph…</p>}>
                  <EntityGraph entities={graphEntities} relations={graphRelations} selectedId={selected} onSelect={setSelected} dark={dark} />
                </Suspense>
                <div className="pointer-events-none absolute bottom-2 left-2 flex flex-wrap gap-2 rounded-lg bg-white/80 px-2 py-1 text-[11px] dark:bg-stone-900/80">
                  {kinds.map((k) => (
                    <span key={k} className="flex items-center gap-1">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: KIND_COLORS[k] }} />
                      {KIND_LABELS[k]}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <ul className="h-full overflow-y-auto p-3">
                {filtered.map((e) => (
                  <li key={e.id}>
                    <button onClick={() => setSelected(e.id)} className={`w-full rounded-lg px-3 py-2 text-left transition ${selected === e.id ? "bg-brand-50 dark:bg-brand-900/30" : "hover:bg-stone-100 dark:hover:bg-stone-800"}`}>
                      <span className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: KIND_COLORS[e.kind] }} />
                        <span className="font-medium">{e.name}</span>
                        <span className="text-xs text-stone-400">{"★".repeat(Math.min(e.importance, 5))}</span>
                      </span>
                      <span className="mt-0.5 line-clamp-2 block pl-4.5 text-sm text-stone-500">{e.description}</span>
                    </button>
                  </li>
                ))}
                {filtered.length === 0 && <li className="p-3 text-sm text-stone-500">No matches.</li>}
              </ul>
            )}
          </div>

          {sel && (
            <EntityDetails
              entity={sel}
              relations={relations.filter((r) => r.source === sel.id || r.target === sel.id)}
              byId={byId}
              mentions={mentions}
              chapterTitle={(p) => chapterLabel(chapters, p)}
              onSelect={setSelected}
              onClose={() => setSelected(null)}
              onOpen={(m) => openPassage(m)}
            />
          )}
        </div>
      )}
      {hasData && maxChapter !== null && (
        <p className="border-t border-stone-200 px-4 py-1.5 text-xs text-stone-500 dark:border-stone-800">
          Spoiler guard on: showing only what's known by chapter {maxChapter}.
        </p>
      )}
    </div>
  );
}

function EntityDetails({
  entity,
  relations,
  byId,
  mentions,
  chapterTitle,
  onSelect,
  onClose,
  onOpen,
}: {
  entity: Entity;
  relations: Relation[];
  byId: Map<number, Entity>;
  mentions: Mention[] | null;
  chapterTitle: (position: number) => string;
  onSelect: (id: number) => void;
  onClose: () => void;
  onOpen: (m: Mention) => void;
}) {
  return (
    <aside className="max-h-[50%] overflow-y-auto border-t border-stone-200 bg-white p-4 md:max-h-none md:w-96 md:border-t-0 md:border-l dark:border-stone-800 dark:bg-stone-900">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs tracking-wide uppercase" style={{ color: KIND_COLORS[entity.kind] }}>
            {entity.kind}
          </p>
          <h3 className="text-lg font-semibold">{entity.name}</h3>
          {entity.aliases.some((a) => a.toLowerCase() !== entity.name.toLowerCase()) && (
            <p className="text-xs text-stone-500">Also: {entity.aliases.filter((a) => a.toLowerCase() !== entity.name.toLowerCase()).join(", ")}</p>
          )}
        </div>
        <button onClick={onClose} className="rounded p-1 text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800" aria-label="Close details">
          <X size={16} />
        </button>
      </div>

      <ol className="mt-3 space-y-2 border-l-2 border-stone-200 pl-3 dark:border-stone-700">
        {entity.details.map((d) => (
          <li key={d.chapter} className="text-sm">
            <span className="text-xs font-medium text-stone-400">{chapterTitle(d.chapter)}</span>
            <p>{d.text}</p>
          </li>
        ))}
      </ol>

      {relations.length > 0 && (
        <>
          <h4 className="mt-4 mb-1 text-xs font-medium tracking-wide text-stone-400 uppercase">
            <Network size={12} className="mr-1 inline" /> Connections
          </h4>
          <ul className="space-y-1 text-sm">
            {relations.map((r) => {
              const other = byId.get(r.source === entity.id ? r.target : r.source);
              if (!other) return null;
              return (
                <li key={r.id}>
                  {r.source === entity.id ? (
                    <>
                      <span className="text-stone-500">{r.relation}</span>{" "}
                      <button className="font-medium text-brand-600 hover:underline dark:text-brand-300" onClick={() => onSelect(other.id)}>
                        {other.name}
                      </button>
                    </>
                  ) : (
                    <>
                      <button className="font-medium text-brand-600 hover:underline dark:text-brand-300" onClick={() => onSelect(other.id)}>
                        {other.name}
                      </button>{" "}
                      <span className="text-stone-500">{r.relation}</span> {entity.name}
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}

      <h4 className="mt-4 mb-1 text-xs font-medium tracking-wide text-stone-400 uppercase">Mentions in the text</h4>
      {mentions === null ? (
        <p className="text-sm text-stone-500">Loading…</p>
      ) : mentions.length === 0 ? (
        <p className="text-sm text-stone-500">No exact mentions found.</p>
      ) : (
        <ul className="space-y-2">
          {mentions.map((m) => (
            <li key={m.chunk_id} className="rounded-lg bg-stone-50 p-2 text-sm dark:bg-stone-800/60">
              <LocationChip chapter={m.chapter_title} page={m.page_start} onClick={() => onOpen(m)} />
              <p className="mt-0.5 line-clamp-3 text-stone-600 dark:text-stone-300">{m.text}</p>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
