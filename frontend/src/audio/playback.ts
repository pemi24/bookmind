import { tts, TtsUnavailable, type TtsCatalog } from "../api";
import { BROWSER_DEFAULT, browserVoiceById, canSpeakInBrowser, findVoice } from "./voices";

/* ---------- one thing plays at a time ---------- */

let current: { stop: () => void } | null = null;

/** Become the only thing playing: whatever played before is stopped. Returns a release function. */
export function claimAudio(stop: () => void): () => void {
  const me = { stop };
  if (current && current !== me) current.stop();
  current = me;
  return () => {
    if (current === me) current = null;
  };
}

/** Stop whatever is playing (chat reply, book, preview). */
export function stopAllAudio() {
  current?.stop();
  current = null;
}

/* ---------- primitives: each resolves when the clip ends, and stops when the signal aborts ---------- */

export interface Sound {
  rate: number; // 0.5–2
  pitch: number; // browser voices only
  volume: number; // 0–1
}

// Chrome drops the events of an utterance nothing references, so the one speaking is kept here.
const live: { utterance: SpeechSynthesisUtterance | null } = { utterance: null };

export function speakWithBrowser(text: string, voiceId: string, sound: Sound, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (!canSpeakInBrowser) return reject(new Error("This browser can't read aloud."));
    if (signal?.aborted) return resolve();
    const synth = window.speechSynthesis;
    const u = new SpeechSynthesisUtterance(text);
    const voice = browserVoiceById(voiceId);
    if (voice) {
      u.voice = voice;
      u.lang = voice.lang;
    }
    u.rate = sound.rate;
    u.pitch = sound.pitch;
    u.volume = sound.volume;
    const done = () => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    };
    const onAbort = () => {
      synth.cancel();
      done();
    };
    u.onend = done;
    u.onerror = (e) => {
      signal?.removeEventListener("abort", onAbort);
      // "interrupted"/"canceled" = stopped on purpose
      if (e.error === "interrupted" || e.error === "canceled") resolve();
      else reject(new Error(`This device's voice couldn't speak (${e.error}).`));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
    live.utterance = u;
    synth.cancel(); // a stuck queue (Chrome) would otherwise delay this forever
    synth.speak(u);
  });
}

/** Play an audio clip; rate beyond what the voice did itself is applied by the browser. */
export function playClip(blob: Blob, sound: { rate: number; volume: number }, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return resolve();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.preservesPitch = true;
    audio.playbackRate = sound.rate;
    audio.volume = Math.min(1, Math.max(0, sound.volume));
    const finish = (error?: Error) => {
      signal?.removeEventListener("abort", onAbort);
      audio.pause();
      audio.removeAttribute("src"); // free the decoded audio
      audio.load();
      URL.revokeObjectURL(url);
      error ? reject(error) : resolve();
    };
    const onAbort = () => finish();
    audio.onended = () => finish();
    audio.onerror = () => finish(new Error("This audio couldn't be played."));
    signal?.addEventListener("abort", onAbort, { once: true });
    audio.play().catch((e: Error) => finish(e.name === "NotAllowedError" ? new Error("The browser blocked playback. Press play again.") : e));
  });
}

/** Extra speed the browser has to add when a provider can't go as fast or slow as asked (Google). */
export function extraRate(catalog: TtsCatalog, voiceId: string, speed: number): { asked: number; browser: number } {
  const range = findVoice(catalog, voiceId)?.provider.speed_range ?? [0.5, 2];
  const asked = Math.min(range[1], Math.max(range[0], speed));
  return { asked, browser: speed / asked };
}

/* ---------- a voice sample ---------- */

// The server's samples are the same; browser voices are sampled here, in their own language.
const SAMPLES: Record<string, string> = {
  en: "Hello! This is how I sound reading your books aloud.",
  fr: "Bonjour ! Voici comment je lis vos livres à voix haute.",
  de: "Hallo! So klinge ich, wenn ich Ihre Bücher vorlese.",
  es: "¡Hola! Así sueno cuando leo tus libros en voz alta.",
  it: "Ciao! Ecco come suono quando leggo ad alta voce i tuoi libri.",
  pt: "Olá! É assim que eu soo lendo os seus livros em voz alta.",
};
const sampleFor = (lang = "") => SAMPLES[lang.slice(0, 2).toLowerCase()] ?? SAMPLES.en;

export interface PreviewResult {
  note: string | null; // the voice wasn't available and another one spoke
}

/** Play a short sample of a voice. Server voices that fail fall back to the browser's voice. */
export async function previewVoice(
  catalog: TtsCatalog,
  voiceId: string,
  sound: Sound,
  signal: AbortSignal,
  onStart?: () => void, // the audio is about to play (a server voice may first take a while)
): Promise<PreviewResult> {
  if (voiceId.startsWith("browser:")) {
    const lang = browserVoiceById(voiceId)?.lang ?? navigator.language;
    onStart?.();
    await speakWithBrowser(sampleFor(lang), voiceId, sound, signal);
    return { note: null };
  }
  const { asked, browser } = extraRate(catalog, voiceId, sound.rate);
  try {
    const spoken = await tts.preview(voiceId, asked, signal);
    if (signal.aborted) return { note: null };
    onStart?.();
    await playClip(spoken.blob, { rate: browser, volume: sound.volume }, signal);
    return { note: spoken.note };
  } catch (e) {
    if (signal.aborted || (e as Error).name === "AbortError") return { note: null };
    if (!(e instanceof TtsUnavailable) || !canSpeakInBrowser) throw e;
    onStart?.();
    await speakWithBrowser(sampleFor(navigator.language), BROWSER_DEFAULT, sound, signal);
    return { note: e.message };
  }
}
