import { X } from "lucide-react";
import { useRef, useState } from "react";
import { api } from "../../api";
import type { KindleBook } from "../../types";
import { useWorkspace } from "../../workspace";
import { Button, ErrorBox } from "../ui";

/** "Import from Kindle": pick My Clippings.txt, choose which Kindle book is this one, import. */
export default function KindleImport({ onImported }: { onImported: () => void }) {
  const { book, notify } = useWorkspace();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [books, setBooks] = useState<KindleBook[] | null>(null);
  const [choice, setChoice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setFile(null);
    setBooks(null);
    setChoice(null);
    setError(null);
  };

  const pick = async (f: File) => {
    reset();
    setFile(f);
    setBusy(true);
    try {
      const res = await api.kindlePreview(book.id, f);
      setBooks(res.books);
      setChoice(res.books[0] && res.books[0].match >= 0.6 ? res.books[0].title : null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    if (!file || !choice) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.kindleImport(book.id, file, choice);
      const parts = [
        `Imported ${r.imported} highlight${r.imported === 1 ? "" : "s"}`,
        r.imported ? `${r.located} found in the text` : null,
        r.notes_attached ? `${r.notes_attached} with your Kindle notes` : null,
        r.standalone_notes ? `${r.standalone_notes} separate note${r.standalone_notes === 1 ? "" : "s"}` : null,
        r.duplicates ? `${r.duplicates} already imported` : null,
      ].filter(Boolean);
      notify(parts.join(" · ") + ".");
      reset();
      onImported();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Button variant="ghost" onClick={() => fileRef.current?.click()} loading={busy && !books} title="Import highlights from a Kindle's My Clippings.txt">
        Import from Kindle
      </Button>
      <input
        ref={fileRef}
        type="file"
        accept=".txt,text/plain"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) pick(f);
          e.target.value = "";
        }}
      />
      {(books || error) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={reset}>
          <div
            role="dialog"
            aria-label="Import Kindle highlights"
            onClick={(e) => e.stopPropagation()}
            className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-5 shadow-xl dark:bg-stone-900"
          >
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <h3 className="font-semibold">Import Kindle highlights</h3>
                <p className="mt-0.5 text-sm text-stone-500">Which Kindle book is “{book.title}”?</p>
              </div>
              <button onClick={reset} className="rounded p-1 text-stone-400 hover:text-stone-700" aria-label="Close">
                <X size={16} />
              </button>
            </div>
            {error && <div className="mt-3"><ErrorBox>{error}</ErrorBox></div>}
            {books && (
              <ul className="mt-3 space-y-1.5">
                {books.map((b) => (
                  <li key={b.title}>
                    <label className={`flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2 text-sm ${choice === b.title ? "border-brand-500 bg-brand-50 dark:bg-brand-950/40" : "border-stone-200 hover:border-stone-300 dark:border-stone-700"}`}>
                      <input type="radio" name="kindle-book" className="mt-1 accent-brand-600" checked={choice === b.title} onChange={() => setChoice(b.title)} />
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium">{b.title}</span>
                        <span className="block text-xs text-stone-500">
                          {[b.author, `${b.highlights} highlight${b.highlights === 1 ? "" : "s"}`, b.notes ? `${b.notes} note${b.notes === 1 ? "" : "s"}` : null].filter(Boolean).join(" · ")}
                        </span>
                      </span>
                      {b.match >= 0.6 && <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">likely match</span>}
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-xs text-stone-500">
              Highlights are matched to the text so they show up in the reader; ones that can't be found (a different
              edition, for example) are still saved to your notes. Importing again skips ones you already have.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={reset}>Cancel</Button>
              <Button variant="primary" onClick={run} disabled={!choice} loading={busy && !!books}>
                Import
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
