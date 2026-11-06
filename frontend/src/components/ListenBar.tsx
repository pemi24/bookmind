import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Headphones,
  Keyboard,
  Loader2,
  LocateFixed,
  Pause,
  Play,
  Settings2,
  SkipBack,
  SkipForward,
  Timer,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { account } from "../api";
import type { useBookPlayer } from "../audio/useBookPlayer";
import type { ChapterInfo, User } from "../types";
import { AudioSlider, formatSpeed, VoiceSelect } from "./VoicePicker";

type Player = ReturnType<typeof useBookPlayer>;

export const SHORTCUTS = "Space: play/pause · ← →: sentence · Shift+← →: paragraph";

function Popover({ open, onClose, children, className = "" }: { open: boolean; onClose: () => void; children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.parentElement?.contains(e.target as Node) && onClose();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      ref={ref}
      className={`absolute right-0 bottom-full z-30 mb-2 rounded-xl border border-stone-200 bg-white p-3 shadow-xl dark:border-stone-700 dark:bg-stone-900 ${className}`}
    >
      {children}
    </div>
  );
}

/** The reader's read-aloud controls: start (here, or where you left off) and, once playing, the player. */
export default function ListenBar({
  player,
  chapters,
  shownChapter,
  hereOffset,
  follow,
  onFollow,
  user,
  onUser,
}: {
  player: Player;
  chapters: ChapterInfo[];
  shownChapter: ChapterInfo | null;
  hereOffset: () => number; // the paragraph at the top of the screen
  follow: boolean;
  onFollow: (v: boolean) => void;
  user: User;
  onUser: (u: User) => void;
}) {
  const [menu, setMenu] = useState<"settings" | "sleep" | null>(null);
  const [speed, setSpeed] = useState(player.prefs.speed);
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveTimer = useRef<number>();
  const [, tick] = useState(0);
  useEffect(() => setSpeed(player.prefs.speed), [player.prefs.speed]);
  // the sleep countdown
  useEffect(() => {
    if (player.sleep.kind !== "time") return;
    const t = window.setInterval(() => tick((n) => n + 1), 15_000);
    return () => window.clearInterval(t);
  }, [player.sleep]);

  const savePrefs = (prefs: Partial<User["settings"]>, delay = 0) => {
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      account
        .updatePreferences(prefs)
        .then((r) => onUser(r.user))
        .catch((e) => setSaveError((e as Error).message));
    }, delay);
  };

  const btn = "rounded-md p-1.5 text-stone-600 hover:bg-stone-100 disabled:opacity-30 dark:text-stone-300 dark:hover:bg-stone-800";
  const { state, current, listening } = player;
  const verses = !!current?.kind; // reading a book with verses
  const unit = verses ? "verse" : "sentence";
  const saved = listening && chapters.find((c) => c.position === listening.position);
  const message = player.error ?? player.notice ?? saveError;

  if (!player.active) {
    return (
      <div className="flex flex-wrap items-center gap-2 border-t border-stone-200 px-3 py-2 font-sans text-sm dark:border-stone-800">
        <button
          onClick={() => shownChapter && player.readFrom(shownChapter.id, hereOffset())}
          disabled={!shownChapter}
          className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          title="Read aloud from the top of the page"
        >
          <Headphones size={15} /> Listen
        </button>
        {saved && (
          <button
            onClick={() => player.readFrom(saved.id, listening!.offset)}
            className="flex min-w-0 items-center gap-1.5 rounded-lg border border-stone-300 px-3 py-1.5 hover:bg-stone-50 dark:border-stone-700 dark:hover:bg-stone-800"
            title="Carry on from where you stopped listening"
          >
            <Play size={14} className="shrink-0" />
            <span className="truncate">
              Continue listening · Ch. {saved.position}
              <span className="hidden sm:inline"> {saved.title}</span>
            </span>
          </button>
        )}
        {message && <p className="basis-full text-xs text-amber-700 dark:text-amber-400">{message}</p>}
      </div>
    );
  }

  const status = state?.status ?? "loading";
  const loading = player.preparing || status === "loading";
  const playing = status === "playing" || loading;
  const progress = player.chapterProgress;
  const chapterIdx = chapters.findIndex((c) => c.id === current?.chapterId);
  const sleepLabel =
    player.sleep.kind === "time"
      ? `${Math.max(1, Math.round((player.sleep.until - Date.now()) / 60_000))} min`
      : player.sleep.kind === "chapter"
        ? "End of ch."
        : null;

  return (
    <div className="border-t border-stone-200 font-sans dark:border-stone-800" data-reader-ui>
      {progress && progress.count > 0 && (
        <div className="h-0.5 bg-stone-100 dark:bg-stone-800">
          <div className="h-full bg-emerald-500 transition-[width]" style={{ width: `${((progress.index + 1) / progress.count) * 100}%` }} />
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-1 gap-y-1 px-2 py-1.5">
        <div className="flex items-center" role="group" aria-label="Read-aloud controls" title={SHORTCUTS}>
          <button
            onClick={() => player.chapter(-1)}
            disabled={chapterIdx <= 0 && (progress?.index ?? 0) < 3}
            className={`${btn} hidden sm:block`}
            title="Previous chapter (or this chapter's start)"
          >
            <SkipBack size={16} />
          </button>
          <button onClick={() => player.paragraph(-1)} className={btn} title="Previous paragraph (Shift+←)">
            <ChevronsLeft size={17} />
          </button>
          <button onClick={() => player.sentence(-1)} className={btn} title={`Previous ${unit} (←)`} aria-label={`Previous ${unit}`}>
            <ChevronLeft size={17} />
          </button>
          <button
            onClick={player.toggle}
            className="mx-0.5 flex h-9 w-9 items-center justify-center rounded-full bg-brand-600 text-white hover:bg-brand-700"
            title={playing ? "Pause (Space)" : "Play (Space)"}
            aria-label={playing ? "Pause" : "Play"}
          >
            {loading ? <Loader2 size={17} className="animate-spin" /> : playing ? <Pause size={17} /> : <Play size={17} className="translate-x-px" />}
          </button>
          <button onClick={() => player.sentence(1)} className={btn} title={`Next ${unit} (→)`} aria-label={`Next ${unit}`}>
            <ChevronRight size={17} />
          </button>
          <button onClick={() => player.paragraph(1)} className={btn} title="Next paragraph (Shift+→)">
            <ChevronsRight size={17} />
          </button>
          <button
            onClick={() => player.chapter(1)}
            disabled={chapterIdx < 0 || chapterIdx >= chapters.length - 1}
            className={`${btn} hidden sm:block`}
            title="Next chapter"
          >
            <SkipForward size={16} />
          </button>
        </div>

        <div className="min-w-0 flex-1 px-1 text-xs text-stone-500" aria-live="off">
          {current && (
            <p className="truncate">
              {verses ? (
                <span className="font-medium text-stone-700 dark:text-stone-200">{current.title}</span>
              ) : (
                <>
                  <span className="font-medium text-stone-700 dark:text-stone-200">Ch. {current.position}</span> {current.title}
                </>
              )}
            </p>
          )}
          <p className="truncate tabular-nums">
            {loading
              ? "Getting the voice ready…"
              : status === "paused"
                ? "Paused"
                : status === "ended"
                  ? "End of the book"
                  : verses && current
                    ? current.verse != null
                      ? `Verse ${current.verse}${current.verse_end ? `–${current.verse_end}` : ""}`
                      : current.kind === "title"
                        ? "Title"
                        : "Chapter"
                    : progress
                      ? `Sentence ${progress.index + 1} of ${progress.count}`
                      : ""}
            {sleepLabel && ` · sleep in ${sleepLabel}`}
          </p>
        </div>

        <div className="relative flex items-center">
          <button
            onClick={() => setMenu(menu === "sleep" ? null : "sleep")}
            className={`${btn} ${sleepLabel ? "!text-brand-600 dark:!text-brand-300" : ""}`}
            title="Sleep timer"
            aria-expanded={menu === "sleep"}
          >
            <Timer size={16} />
          </button>
          <Popover open={menu === "sleep"} onClose={() => setMenu(null)} className="w-44 p-1 text-sm">
            <p className="px-2 py-1 text-xs font-medium text-stone-500">Stop reading after</p>
            {([15, 30, 60] as const).map((m) => (
              <button
                key={m}
                onClick={() => (player.setSleep(m), setMenu(null))}
                className="block w-full rounded-md px-2 py-1.5 text-left hover:bg-stone-100 dark:hover:bg-stone-800"
              >
                {m} minutes
              </button>
            ))}
            <button
              onClick={() => (player.setSleep("chapter"), setMenu(null))}
              className="block w-full rounded-md px-2 py-1.5 text-left hover:bg-stone-100 dark:hover:bg-stone-800"
            >
              End of this chapter
            </button>
            {player.sleep.kind !== "off" && (
              <button
                onClick={() => (player.setSleep("off"), setMenu(null))}
                className="block w-full rounded-md px-2 py-1.5 text-left text-red-600 hover:bg-stone-100 dark:hover:bg-stone-800"
              >
                Turn off
              </button>
            )}
          </Popover>

          <button
            onClick={() => setMenu(menu === "settings" ? null : "settings")}
            className={btn}
            title="Voice, speed and following along"
            aria-expanded={menu === "settings"}
          >
            <Settings2 size={16} />
          </button>
          <Popover open={menu === "settings"} onClose={() => setMenu(null)} className="w-72 space-y-3 text-sm">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-stone-500">Voice for reading books</span>
              <VoiceSelect catalog={player.catalog} value={user.settings.tts_read_voice ?? ""} onChange={(v) => savePrefs({ tts_read_voice: v })} />
            </label>
            <AudioSlider
              label="Speed"
              value={speed}
              min={0.5}
              max={2}
              step={0.05}
              format={formatSpeed}
              onChange={(v) => {
                setSpeed(v);
                player.setSound({ rate: v });
                savePrefs({ tts_speed: v }, 600);
              }}
            />
            {verses && (
              <fieldset className="space-y-2 rounded-lg border border-stone-200 p-2 dark:border-stone-700">
                <legend className="px-1 text-xs font-medium text-stone-500">Chapters and verses</legend>
                <label className="flex items-center justify-between gap-2">
                  <span>Announce verse numbers</span>
                  <select
                    value={player.prefs.announceVerses ? "every" : "off"}
                    onChange={(e) => savePrefs({ tts_announce_verses: e.target.value as "every" | "off" })}
                    className="rounded-md border border-stone-300 bg-transparent px-1.5 py-0.5 text-sm dark:border-stone-700 dark:bg-stone-900"
                  >
                    <option value="every">Every verse</option>
                    <option value="off">Off</option>
                  </select>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={player.prefs.announceChapter}
                    onChange={(e) => savePrefs({ tts_announce_chapter: e.target.checked })}
                    className="accent-brand-600"
                  />
                  Announce each chapter
                </label>
              </fieldset>
            )}
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={follow} onChange={(e) => onFollow(e.target.checked)} className="accent-brand-600" />
              <span className="flex items-center gap-1">
                <LocateFixed size={14} /> Follow along (scroll to the sentence)
              </span>
            </label>
            <p className="flex items-start gap-1.5 text-xs text-stone-500">
              <Keyboard size={14} className="mt-px shrink-0" /> {SHORTCUTS}. Tap a paragraph to read from there.
            </p>
          </Popover>

          <button onClick={player.stop} className={btn} title="Stop listening" aria-label="Stop listening">
            <X size={17} />
          </button>
        </div>
      </div>
      {message && <p className="px-3 pb-1.5 text-xs text-amber-700 dark:text-amber-400">{message}</p>}
    </div>
  );
}
