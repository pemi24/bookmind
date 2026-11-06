import { useEffect, useState } from "react";
import { tts, type TtsCatalog, type TtsProvider, type TtsVoice } from "../api";
import type { User } from "../types";

/** The browser's default voice (whatever the device would use). */
export const BROWSER_DEFAULT = "browser:";

export interface VoicePrefs {
  chatVoice: string; // "" = the server's default voice
  readVoice: string;
  speed: number;
  pitch: number;
  volume: number;
  autoRead: boolean;
  announceVerses: boolean; // books with verses: say "Verse 1" before each verse
  announceChapter: boolean; // and "Genesis, chapter 1" once when a chapter starts
}

export function voicePrefs(user: User): VoicePrefs {
  const s = user.settings;
  return {
    chatVoice: s.tts_chat_voice ?? "",
    readVoice: s.tts_read_voice ?? "",
    speed: s.tts_speed ?? 1,
    pitch: s.tts_pitch ?? 1,
    volume: s.tts_volume ?? 1,
    autoRead: s.tts_auto_read ?? false,
    announceVerses: (s.tts_announce_verses ?? "every") !== "off",
    announceChapter: s.tts_announce_chapter ?? true,
  };
}

/* ---------- browser voices (Web Speech API) ---------- */

export const canSpeakInBrowser = typeof window !== "undefined" && "speechSynthesis" in window;

const REGIONS: Record<string, string> = {
  US: "American",
  GB: "British",
  AU: "Australian",
  IN: "Indian",
  IE: "Irish",
  CA: "Canadian",
  NZ: "New Zealand",
  ZA: "South African",
  FR: "French",
  BE: "Belgian",
  CH: "Swiss",
  DE: "German",
  ES: "Spanish",
  MX: "Mexican",
  IT: "Italian",
  BR: "Brazilian",
  PT: "Portuguese",
};
// Browser voices don't say who is speaking; these are the usual Windows, macOS, Android and Edge names.
const FEMALE =
  /\b(female|woman|zira|hazel|susan|heera|aria|jenny|sonia|libby|samantha|karen|moira|tessa|fiona|victoria|serena|amelie|hortense|julie|denise|natasha|clara|catherine|linda|eva|helena|elsa|paulina|monica|alice|anna|zuzana|ava|allison|emma|michelle)\b/i;
const MALE =
  /\b(male|man|david|mark|george|ravi|guy|ryan|daniel|alex|fred|thomas|paul|rishi|aaron|arthur|oliver|henri|james|richard|sean|stefan|pablo|jorge|diego|luca|claude|christopher|eric|roger|steffan|william|brian)\b/i;

function guessGender(name: string): string {
  if (/female/i.test(name)) return "female";
  if (/\bmale\b/i.test(name)) return "male";
  return FEMALE.test(name) ? "female" : MALE.test(name) ? "male" : "";
}

export function browserVoiceById(id: string): SpeechSynthesisVoice | undefined {
  if (!canSpeakInBrowser || !id.startsWith("browser:") || id === BROWSER_DEFAULT) return undefined;
  const uri = id.slice("browser:".length);
  return window.speechSynthesis.getVoices().find((v) => v.voiceURI === uri);
}

function toVoice(v: SpeechSynthesisVoice): TtsVoice {
  const [, region] = v.lang.split(/[-_]/);
  // "Microsoft Zira - English (United States)" → "Zira"; "Google UK English Female" stays as it is
  const name = v.name
    .replace(/^Microsoft\s+/, "")
    .replace(/\s+-\s+.*$/, "")
    .replace(/\s+Online \(Natural\)$/, " (natural)");
  return {
    id: `browser:${v.voiceURI}`,
    provider: "browser",
    name,
    language: v.lang,
    accent: REGIONS[region?.toUpperCase()] ?? "",
    gender: guessGender(v.name),
    quality: v.localService ? "" : "online",
  };
}

function useBrowserVoices(): SpeechSynthesisVoice[] {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>(() => (canSpeakInBrowser ? window.speechSynthesis.getVoices() : []));
  useEffect(() => {
    if (!canSpeakInBrowser) return;
    const update = () => setVoices(window.speechSynthesis.getVoices()); // Chrome loads them after the page
    update();
    window.speechSynthesis.addEventListener("voiceschanged", update);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", update);
  }, []);
  return voices;
}

/* ---------- the whole catalog ---------- */

let catalogRequest: Promise<TtsCatalog> | null = null;
/** The server's voices, fetched once per page load (reload() after a change on the server). */
export function loadCatalog(reload = false): Promise<TtsCatalog> {
  if (!catalogRequest || reload) {
    catalogRequest = tts.voices().catch((e) => {
      catalogRequest = null; // try again next time
      throw e;
    });
  }
  return catalogRequest;
}

export interface VoiceCatalog extends TtsCatalog {
  loading: boolean;
  error: string | null;
}

/** Every voice on offer: the server's providers, with the browser's own voices filled in. */
export function useVoiceCatalog(): VoiceCatalog {
  const [server, setServer] = useState<TtsCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const browser = useBrowserVoices();
  useEffect(() => {
    loadCatalog()
      .then(setServer)
      .catch((e) => setError(e.message));
  }, []);
  const browserProvider = (p?: TtsProvider): TtsProvider => ({
    id: "browser",
    label: "Browser voices (this device)",
    client_side: true,
    supports_streaming: true,
    speed_range: [0.5, 2],
    pitch: true,
    volume: true,
    ...p,
    available: canSpeakInBrowser && browser.length > 0,
    reason: !canSpeakInBrowser ? "This browser can't speak." : browser.length ? "" : "This browser has no voices installed.",
    voices: [...browser].sort((a, b) => a.lang.localeCompare(b.lang) || a.name.localeCompare(b.name)).map(toVoice),
  });
  const providers = server ? server.providers.map((p) => (p.id === "browser" ? browserProvider(p) : p)) : [browserProvider()];
  return {
    providers,
    default_voice: server?.default_voice ?? BROWSER_DEFAULT,
    max_chars: server?.max_chars ?? 1500,
    loading: !server && !error,
    error,
  };
}

export function findVoice(catalog: TtsCatalog, id: string): { provider: TtsProvider; voice: TtsVoice | null } | null {
  const providerId = id.split(":", 1)[0];
  const provider = catalog.providers.find((p) => p.id === providerId);
  if (!provider) return null;
  if (id === BROWSER_DEFAULT) return provider.available || canSpeakInBrowser ? { provider, voice: null } : null;
  const voice = provider.available ? provider.voices.find((v) => v.id === id) : undefined;
  return voice ? { provider, voice } : null;
}

export function voiceLabel(v: TtsVoice | null): string {
  if (!v) return "Device default voice";
  const details = [v.accent, v.gender].filter(Boolean).join(", ");
  return details ? `${v.name} — ${details}` : v.name;
}

export interface ResolvedVoice {
  id: string; // the voice that will speak
  provider: TtsProvider | null;
  voice: TtsVoice | null; // null = the browser's default voice
  notice: string | null; // set when a saved voice isn't available any more
}

/** The voice to use for a saved choice ("" = the server's default), falling back when it's gone. */
export function resolveVoice(catalog: VoiceCatalog, saved: string): ResolvedVoice {
  const wanted = saved || catalog.default_voice;
  const hit = findVoice(catalog, wanted);
  if (hit) return { id: wanted, ...hit, notice: null };
  const fallback = findVoice(catalog, catalog.default_voice) ?? findVoice(catalog, BROWSER_DEFAULT);
  const id = fallback?.voice?.id ?? BROWSER_DEFAULT; // a hit without a voice is the browser default
  // Browser voices are known only once the browser lists them: don't complain while it's loading.
  const waiting = catalog.loading || (wanted.startsWith("browser:") && !catalog.providers.find((p) => p.id === "browser")?.voices.length);
  return {
    id,
    provider: fallback?.provider ?? null,
    voice: fallback?.voice ?? null,
    notice: waiting ? null : `Your saved voice isn't available any more, so ${voiceLabel(fallback?.voice ?? null).split(" — ")[0]} is used instead.`,
  };
}
