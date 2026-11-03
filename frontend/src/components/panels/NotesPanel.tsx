import { Download, NotebookPen, Pencil, Plus, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { HighlightColor, Note } from "../../types";
import { useWorkspace } from "../../workspace";
import KindleImport from "./KindleImport";
import { Button, buttonClasses, EmptyState, ErrorBox, LocationChip, Markdown, PanelShell } from "../ui";

const KIND_LABEL: Record<Note["kind"], string> = { note: "Note", answer: "Answer", passage: "Highlight", quote: "Quote" };
const QUOTE_BORDER: Record<HighlightColor, string> = {
  yellow: "border-amber-300",
  green: "border-emerald-400",
  blue: "border-sky-400",
  pink: "border-pink-400",
};

function TagEditor({ tags, onSave }: { tags: string[]; onSave: (tags: string[]) => void }) {
  const [value, setValue] = useState(tags.join(", "));
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave(value.split(/[,\s]+/).filter(Boolean));
      }}
      className="flex items-center gap-1"
    >
      <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} placeholder="tag1, tag2" className="w-48 rounded-md border border-stone-300 bg-transparent px-2 py-0.5 text-xs dark:border-stone-700" aria-label="Tags" />
      <Button type="submit" variant="ghost" className="!px-2 !py-0.5 text-xs">Save</Button>
    </form>
  );
}

export default function NotesPanel({ refreshKey }: { refreshKey: number }) {
  const { book, openPassage, notify } = useWorkspace();
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [tag, setTag] = useState<string | null>(null);
  const [editingTags, setEditingTags] = useState<number | null>(null);
  const [draft, setDraft] = useState<{ title: string; content: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.notes(book.id, tag);
      setNotes(res.notes);
      setTags(res.tags);
      if (tag && !res.tags.includes(tag)) setTag(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [book.id, tag]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const saveDraft = async () => {
    if (!draft?.content.trim()) return;
    try {
      await api.createNote(book.id, { kind: "note", title: draft.title || null, content: draft.content, tags: tag ? [tag] : [], location: {} });
      setDraft(null);
      load();
    } catch (e) {
      notify((e as Error).message);
    }
  };

  const update = async (id: number, patch: { tags?: string[] }) => {
    await api.updateNote(id, patch);
    setEditingTags(null);
    load();
  };

  const remove = async (id: number) => {
    if (!confirm("Delete this note?")) return;
    await api.deleteNote(id);
    load();
  };

  return (
    <PanelShell
      title="Notes & highlights"
      actions={
        <>
          <Button variant="ghost" onClick={() => setDraft({ title: "", content: "" })}>
            <Plus size={14} /> New note
          </Button>
          <KindleImport onImported={load} />
          {(["md", "pdf"] as const).map((fmt) => (
            <a
              key={fmt}
              href={api.exportNotesUrl(book.id, fmt, tag)}
              download
              aria-disabled={!notes?.length}
              className={`${buttonClasses("secondary")} ${notes?.length ? "" : "pointer-events-none opacity-40"}`}
            >
              <Download size={14} /> {fmt === "md" ? "Markdown" : "PDF"}
            </a>
          ))}
        </>
      }
    >
      {error && <ErrorBox>{error}</ErrorBox>}

      {tags.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          <button onClick={() => setTag(null)} className={`rounded-full px-2.5 py-0.5 text-xs ${tag === null ? "bg-brand-600 text-white" : "bg-stone-100 dark:bg-stone-800"}`}>
            All
          </button>
          {tags.map((t) => (
            <button key={t} onClick={() => setTag(t === tag ? null : t)} className={`rounded-full px-2.5 py-0.5 text-xs ${tag === t ? "bg-brand-600 text-white" : "bg-stone-100 hover:bg-stone-200 dark:bg-stone-800 dark:hover:bg-stone-700"}`}>
              #{t}
            </button>
          ))}
        </div>
      )}

      {draft && (
        <div className="mb-4 rounded-xl border border-brand-300 bg-white p-3 dark:border-brand-800 dark:bg-stone-900">
          <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} placeholder="Title (optional)" className="w-full bg-transparent text-sm font-medium outline-none" />
          <textarea autoFocus value={draft.content} onChange={(e) => setDraft({ ...draft, content: e.target.value })} rows={4} placeholder="Write a note… (Markdown supported)" className="mt-2 w-full resize-y bg-transparent text-sm outline-none" />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDraft(null)}>Cancel</Button>
            <Button variant="primary" onClick={saveDraft} disabled={!draft.content.trim()}>Save note</Button>
          </div>
        </div>
      )}

      {notes && notes.length === 0 && !draft && (
        <EmptyState icon={<NotebookPen size={22} />} title={tag ? `No notes tagged #${tag}` : "No notes yet"}>
          Save answers from the chat, quotes from the Quote finder, summaries, or select text in the reader and click “Save highlight”.
        </EmptyState>
      )}

      <ul className="space-y-3">
        {notes?.map((n) => (
          <li key={n.id} className="group rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium tracking-wide text-stone-400 uppercase">
                  {KIND_LABEL[n.kind]}
                  {n.created_at ? ` · ${new Date(n.created_at).toLocaleDateString()}` : ""}
                </p>
                {n.title && <p className="font-medium">{n.title}</p>}
              </div>
              <button onClick={() => remove(n.id)} className="rounded p-1 text-stone-400 opacity-60 group-hover:opacity-100 hover:text-red-600" aria-label="Delete note">
                <Trash2 size={14} />
              </button>
            </div>
            <div className="mt-1">
              {n.kind === "quote" || n.kind === "passage" ? (
                <>
                  <blockquote className={`border-l-4 pl-3 font-serif text-[16px] leading-relaxed ${QUOTE_BORDER[n.color ?? "yellow"]}`}>{n.content}</blockquote>
                  {n.comment && <p className="mt-2 text-sm whitespace-pre-line text-stone-600 dark:text-stone-300">✎ {n.comment}</p>}
                </>
              ) : (
                <Markdown text={n.content.replace(/\s?\[\d+(?:\s*[,–-]\s*\d+)*\]/g, "")} />
              )}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {n.location?.chapter_id && (
                <LocationChip
                  chapter={n.location.chapter_title ?? "Open in reader"}
                  page={n.location.page}
                  onClick={() => openPassage({ chapter_id: n.location.chapter_id!, char_start: n.location.char_start, char_end: n.location.char_end })}
                />
              )}
              {editingTags === n.id ? (
                <>
                  <TagEditor tags={n.tags} onSave={(t) => update(n.id, { tags: t })} />
                  <button onClick={() => setEditingTags(null)} className="text-stone-400" aria-label="Cancel"><X size={14} /></button>
                </>
              ) : (
                <>
                  {n.tags.map((t) => (
                    <span key={t} className="rounded-full bg-stone-100 px-2 py-0.5 text-xs dark:bg-stone-800">#{t}</span>
                  ))}
                  <button onClick={() => setEditingTags(n.id)} className="flex items-center gap-1 text-xs text-stone-400 hover:text-stone-700 dark:hover:text-stone-200">
                    <Pencil size={12} /> tags
                  </button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </PanelShell>
  );
}
