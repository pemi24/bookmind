import { Loader2, Play, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { claimAudio, previewVoice, type Sound } from "../audio/playback";
import { BROWSER_DEFAULT, findVoice, voiceLabel, type VoiceCatalog } from "../audio/voices";
import { Button } from "./ui";

const select =
  "w-full min-w-0 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 dark:border-stone-700 dark:bg-stone-900";

/** A voice dropdown grouped by provider ("" = the server's default voice, when allowDefault). */
export function VoiceSelect({
  catalog,
  value,
  onChange,
  allowDefault = true,
  id,
  className = "",
}: {
  catalog: VoiceCatalog;
  value: string;
  onChange: (id: string) => void;
  allowDefault?: boolean;
  id?: string;
  className?: string;
}) {
  const fallback = findVoice(catalog, catalog.default_voice);
  // a saved voice that isn't listed any more stays visible, so the dropdown doesn't lie about it
  const missing = value && value !== BROWSER_DEFAULT && !findVoice(catalog, value) && !catalog.loading;
  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={`${select} ${className}`}>
      {allowDefault && <option value="">Server default ({voiceLabel(fallback?.voice ?? null)})</option>}
      {missing && <option value={value}>Unavailable voice ({value.split(":").slice(1).join(":") || value})</option>}
      {catalog.providers.map((p) =>
        p.available ? (
          <optgroup key={p.id} label={p.label}>
            {p.id === "browser" && <option value={BROWSER_DEFAULT}>Device default voice</option>}
            {p.voices.map((v) => (
              <option key={v.id} value={v.id}>
                {voiceLabel(v)}
                {v.language && p.id === "browser" ? ` (${v.language})` : ""}
              </option>
            ))}
          </optgroup>
        ) : (
          <optgroup key={p.id} label={`${p.label}: unavailable`}>
            <option disabled value={`unavailable:${p.id}`}>
              {p.reason || "Not available on this server."}
            </option>
          </optgroup>
        ),
      )}
    </select>
  );
}

/** Plays a short sample of a voice; a second press stops it. */
export function PreviewButton({ catalog, voiceId, sound }: { catalog: VoiceCatalog; voiceId: string; sound: Sound }) {
  const [state, setState] = useState<"idle" | "loading" | "slow" | "playing">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  const play = async () => {
    if (abort.current) {
      abort.current.abort();
      return;
    }
    const ctrl = new AbortController();
    abort.current = ctrl;
    const release = claimAudio(() => ctrl.abort());
    setMessage(null);
    const server = !voiceId.startsWith("browser:");
    setState(server ? "loading" : "playing");
    // a Piper voice's first sentence waits for it to load (several seconds)
    const slow = window.setTimeout(() => setState((s) => (s === "loading" ? "slow" : s)), 1500);
    try {
      const { note } = await previewVoice(catalog, voiceId, sound, ctrl.signal, () => setState("playing"));
      if (note) setMessage(note);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      window.clearTimeout(slow);
      release();
      if (abort.current === ctrl) abort.current = null;
      setState("idle");
    }
  };

  const label = { idle: "Preview", loading: "Loading…", slow: "Loading voice…", playing: "Stop" }[state];
  return (
    <span className="inline-flex flex-col gap-1">
      <Button type="button" onClick={play} disabled={!voiceId && !catalog.default_voice} title="Play a short sample of this voice">
        {state === "idle" ? <Play size={14} /> : state === "playing" ? <Square size={14} /> : <Loader2 size={14} className="animate-spin" />}
        {label}
      </Button>
      {state === "slow" && <span className="text-xs text-stone-500">The first sample of a voice can take up to 20 seconds while it loads.</span>}
      {message && <span className="text-xs text-amber-700 dark:text-amber-400">{message}</span>}
    </span>
  );
}

/** A labelled range slider, e.g. speed 0.5×–2×. */
export function AudioSlider({
  label,
  value,
  onChange,
  min,
  max,
  step,
  format,
  disabled,
  hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  disabled?: boolean;
  hint?: string;
}) {
  return (
    <label className={`block ${disabled ? "opacity-50" : ""}`}>
      <span className="mb-1 flex items-baseline justify-between text-sm font-medium text-stone-700 dark:text-stone-300">
        {label} <span className="font-normal tabular-nums text-stone-500">{format(value)}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-brand-600"
      />
      {hint && <span className="mt-0.5 block text-xs text-stone-500">{hint}</span>}
    </label>
  );
}

export const formatSpeed = (v: number) => `${Number(v.toFixed(2))}×`;
export const formatPercent = (v: number) => `${Math.round(v * 100)}%`;
