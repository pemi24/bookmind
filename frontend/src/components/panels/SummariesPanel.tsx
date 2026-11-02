import { BookmarkPlus, Copy, FileText, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { Length, SummaryResult } from "../../types";
import { useJobPolling, useWorkspace } from "../../workspace";
import { Button, ChapterSelect, EmptyState, ErrorBox, JobProgress, Markdown, PanelShell, Segmented } from "../ui";

const LENGTHS: { value: Length; label: string }[] = [
  { value: "short", label: "Short" },
  { value: "medium", label: "Medium" },
  { value: "detailed", label: "Detailed" },
];

export default function SummariesPanel() {
  const { book, chapters, maxChapter, saveNote, notify } = useWorkspace();
  const [chapterId, setChapterId] = useState<number | null>(null);
  const [length, setLength] = useState<Length>("medium");
  const [result, setResult] = useState<SummaryResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A chapter beyond the spoiler limit can't stay selected.
  useEffect(() => {
    const ch = chapters.find((c) => c.id === chapterId);
    if (ch && maxChapter !== null && ch.position > maxChapter) setChapterId(null);
  }, [maxChapter, chapterId, chapters]);

  const params = { chapter_id: chapterId, length, max_chapter: maxChapter };

  const load = useCallback(async () => {
    setError(null);
    try {
      setResult(await api.summary(book.id, { chapter_id: chapterId, length, max_chapter: maxChapter }));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [book.id, chapterId, length, maxChapter]);

  useEffect(() => {
    setResult(null);
    load();
  }, [load]);

  const generate = async (refresh = false) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.summarize(book.id, { ...params, refresh }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const runningJob = result && result.status === "running" ? result.job : null;
  const polled = useJobPolling(book.id, runningJob?.kind ?? null, (job) => {
    if (job.status === "done") load();
    else setResult({ status: "failed", job });
  });

  const scopeName = chapterId ? chapters.find((c) => c.id === chapterId)?.title ?? "Chapter" : "Whole book";
  const summary = result?.status === "done" ? result.summary : null;

  return (
    <PanelShell
      title="Summaries"
      actions={
        <>
          <ChapterSelect chapters={chapters} value={chapterId} onChange={setChapterId} maxChapter={maxChapter} />
          <Segmented value={length} options={LENGTHS} onChange={setLength} label="Summary length" />
        </>
      }
    >
      {error && <ErrorBox>{error}</ErrorBox>}

      {result?.status === "failed" && !busy && (
        <div className="space-y-3">
          <ErrorBox>The last attempt failed: {result.job.error ?? "unknown error"}</ErrorBox>
          <Button variant="primary" onClick={() => generate(true)}>
            Try again
          </Button>
        </div>
      )}

      {runningJob && <JobProgress job={polled ?? runningJob} label={`Summarizing ${scopeName.toLowerCase()}…`} />}

      {result?.status === "missing" && !busy && (
        <EmptyState icon={<FileText size={22} />} title={`No ${length} summary of “${scopeName}” yet`}>
          <p>
            {chapterId
              ? "Generated from the chapter's text."
              : maxChapter
                ? `Covers chapters 1–${maxChapter} only (spoiler guard).`
                : "Covers the whole book. Long books are summarized chapter by chapter first, which takes a little while."}
          </p>
          <Button variant="primary" className="mt-4" onClick={() => generate()}>
            Generate summary
          </Button>
        </EmptyState>
      )}

      {busy && !runningJob && (
        <div className="space-y-2 rounded-xl border border-stone-200 p-5 dark:border-stone-800" aria-busy>
          {[90, 100, 75, 95, 60].map((w, i) => (
            <div key={i} className="h-3 animate-pulse rounded bg-stone-200 dark:bg-stone-800" style={{ width: `${w}%` }} />
          ))}
          <p className="pt-2 text-xs text-stone-500">Reading the chapter and writing a summary…</p>
        </div>
      )}

      {summary && !busy && (
        <article className="rounded-xl border border-stone-200 bg-white p-5 dark:border-stone-800 dark:bg-stone-900">
          <p className="mb-2 text-xs font-medium tracking-wide text-stone-400 uppercase">
            {scopeName} · {length}
            {summary.up_to_chapter ? ` · chapters 1–${summary.up_to_chapter}` : ""}
          </p>
          <Markdown text={summary.content} />
          <div className="mt-4 flex flex-wrap gap-2 border-t border-stone-100 pt-3 dark:border-stone-800">
            <Button
              variant="ghost"
              onClick={() => navigator.clipboard.writeText(summary.content).then(() => notify("Summary copied."))}
            >
              <Copy size={14} /> Copy
            </Button>
            <Button
              variant="ghost"
              onClick={() =>
                saveNote({
                  kind: "note",
                  title: `${length[0].toUpperCase() + length.slice(1)} summary — ${scopeName}`,
                  content: summary.content,
                  tags: ["summary"],
                  location: chapterId ? { chapter_id: chapterId, chapter_title: scopeName } : {},
                })
              }
            >
              <BookmarkPlus size={14} /> Save to notes
            </Button>
            <Button variant="ghost" onClick={() => generate(true)}>
              <RefreshCw size={14} /> Regenerate
            </Button>
          </div>
        </article>
      )}
    </PanelShell>
  );
}
