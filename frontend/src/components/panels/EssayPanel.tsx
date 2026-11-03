import { BookmarkPlus, Copy, Download, PenLine } from "lucide-react";
import { useState } from "react";
import { api } from "../../api";
import type { Essay } from "../../types";
import { useWorkspace } from "../../workspace";
import { Button, EmptyState, ErrorBox, LocationChip, PanelShell } from "../ui";

const EXAMPLES = [
  "The novel argues that curiosity matters more than obedience.",
  "Deception is presented as a strength, not a flaw.",
];

/** Essay helper: a thesis in, an outline out, every supporting quote verified against the book. */
export default function EssayPanel() {
  const { book, maxChapter, openPassage, saveNote, notify } = useWorkspace();
  const [thesis, setThesis] = useState("");
  const [sections, setSections] = useState(3);
  const [essay, setEssay] = useState<Essay | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const build = async () => {
    if (thesis.trim().length < 5) return;
    setBusy(true);
    setError(null);
    try {
      setEssay(await api.essay(book.id, { thesis: thesis.trim(), max_chapter: maxChapter, sections }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const withMarkdown = async (fn: (md: string) => void | Promise<void>) => {
    if (!essay) return;
    try {
      await fn(await api.essayMarkdown(book.id, essay));
    } catch (e) {
      notify((e as Error).message);
    }
  };

  const download = (md: string) => {
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "essay-outline.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <PanelShell
      title="Essay helper"
      actions={
        essay && (
          <>
            <Button variant="ghost" onClick={() => withMarkdown((md) => navigator.clipboard.writeText(md).then(() => notify("Outline copied.")))}>
              <Copy size={14} /> Copy
            </Button>
            <Button variant="ghost" onClick={() => withMarkdown(download)}>
              <Download size={14} /> Markdown
            </Button>
            <Button variant="ghost" onClick={() => withMarkdown((md) => saveNote({ kind: "note", title: `Essay: ${essay.title}`, content: md, tags: ["essay"], location: {} }))}>
              <BookmarkPlus size={14} /> Save to notes
            </Button>
          </>
        )
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          build();
        }}
        className="rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900"
      >
        <label htmlFor="thesis" className="text-sm font-medium">Your thesis</label>
        <textarea
          id="thesis"
          value={thesis}
          onChange={(e) => setThesis(e.target.value)}
          rows={2}
          maxLength={600}
          placeholder={`e.g. ${EXAMPLES[book.is_fiction === false ? 1 : 0]}`}
          className="mt-1 w-full resize-y rounded-lg border border-stone-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-brand-500 dark:border-stone-700"
        />
        <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-1.5">
            Body sections
            <select value={sections} onChange={(e) => setSections(Number(e.target.value))} className="rounded-lg border border-stone-300 bg-transparent px-2 py-1 dark:border-stone-700">
              {[2, 3, 4, 5].map((n) => (
                <option key={n} value={n} className="dark:bg-stone-900">{n}</option>
              ))}
            </select>
          </label>
          <Button type="submit" variant="primary" loading={busy} disabled={thesis.trim().length < 5}>
            {busy ? "Building outline…" : "Build outline"}
          </Button>
          {maxChapter !== null && <span className="text-xs text-stone-500">Using chapters 1–{maxChapter} only (spoiler guard).</span>}
        </div>
      </form>

      {error && <div className="mt-4"><ErrorBox>{error}</ErrorBox></div>}

      {!essay && !busy && !error && (
        <EmptyState icon={<PenLine size={22} />} title="Plan an essay with real evidence">
          Write the argument you want to make. You'll get an outline with a sharpened thesis, body sections, a counter-argument and a
          conclusion, supported by quotes checked word for word against the book.
        </EmptyState>
      )}

      {essay && (
        <article className="mt-5 space-y-5">
          <header>
            <h2 className="text-xl font-semibold">{essay.title}</h2>
            <p className="mt-2 rounded-lg bg-brand-50 px-3 py-2 text-sm dark:bg-brand-950/40">
              <span className="font-semibold">Thesis: </span>
              {essay.thesis}
            </p>
          </header>
          <section>
            <h3 className="text-sm font-semibold tracking-wide text-stone-500 uppercase">Introduction</h3>
            <p className="mt-1 text-[15px]">{essay.introduction}</p>
          </section>
          {essay.sections.map((s, i) => (
            <section key={i} className="rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
              <h3 className="font-semibold">
                {i + 1}. {s.heading}
              </h3>
              <p className="mt-1 text-[15px]">{s.point}</p>
              {s.evidence.length === 0 && <p className="mt-2 text-xs text-stone-500">No verified quote supports this point; look for evidence yourself.</p>}
              <ul className="mt-3 space-y-3">
                {s.evidence.map((ev) => (
                  <li key={`${ev.chapter_id}-${ev.char_start}`}>
                    <blockquote className="border-l-4 border-amber-300 pl-3 font-serif text-[15px] leading-relaxed">“{ev.quote}”</blockquote>
                    <p className="mt-1 text-sm text-stone-600 dark:text-stone-300">{ev.explanation}</p>
                    <div className="mt-1">
                      <LocationChip chapter={ev.chapter_title} page={ev.page} onClick={() => openPassage(ev)} />
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          <section>
            <h3 className="text-sm font-semibold tracking-wide text-stone-500 uppercase">Counter-argument</h3>
            <p className="mt-1 text-[15px]">{essay.counterargument}</p>
          </section>
          <section>
            <h3 className="text-sm font-semibold tracking-wide text-stone-500 uppercase">Conclusion</h3>
            <p className="mt-1 text-[15px]">{essay.conclusion}</p>
          </section>
          {essay.dropped_quotes > 0 && (
            <p className="text-xs text-stone-500">
              {essay.dropped_quotes} suggested quote{essay.dropped_quotes === 1 ? " was" : "s were"} left out because {essay.dropped_quotes === 1 ? "it isn't" : "they aren't"} word for word in the book.
            </p>
          )}
        </article>
      )}
    </PanelShell>
  );
}
