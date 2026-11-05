import { tts, TtsUnavailable, type TtsCatalog } from "../api";
import { claimAudio, extraRate, speakWithBrowser, type Sound } from "./playback";
import { BROWSER_DEFAULT, canSpeakInBrowser } from "./voices";

export type QueueStatus = "idle" | "loading" | "playing" | "paused" | "ended" | "error";

export interface QueueState {
  status: QueueStatus;
  index: number; // sentence being read (or next to read)
  total: number;
  voice: string; // the voice actually speaking
  notice: string | null; // e.g. the chosen voice failed and another one took over
  error: string | null;
}

export interface QueueOptions {
  catalog: TtsCatalog;
  voice: string; // a resolved voice id
  sound: Sound;
  ahead?: number; // server clips prepared in advance of the one playing
  /** Lock screen / headphone controls show this as the "track". */
  meta?: { title: string; artist?: string; album?: string };
  onChange: (state: QueueState) => void;
  onSentence?: (index: number) => void;
  /** Out of sentences: append() more and return true to keep going (the reader's next chapter). */
  onEnd?: () => Promise<boolean> | boolean;
}

interface Clip {
  url: string;
  speed: number; // the speed it was synthesized at (the browser makes up the rest)
  note: string | null;
}

/**
 * Reads sentences one after another. Server voices: the next few clips are synthesized while one
 * plays, so there's no wait between sentences; each clip is freed once it has played. Browser
 * voices: spoken by the browser. If the server can't speak at all, it carries on with the
 * device's own voice and says so.
 */
export class SpeechQueue {
  private sentences: string[];
  private index = 0;
  private status: QueueStatus = "idle";
  private voice: string;
  private sound: Sound;
  private notice: string | null = null;
  private error: string | null = null;
  private clips = new Map<number, { clip: Promise<Clip>; ctrl: AbortController }>();
  private audio = new Audio();
  private generation = 0; // each play() run; stale runs stop at their next check
  private sentenceCtrl: AbortController | null = null;
  private resumeAt = 0; // seconds into the current server clip, after a pause
  private release: (() => void) | null = null;

  constructor(
    sentences: string[],
    private opts: QueueOptions,
  ) {
    this.sentences = [...sentences];
    this.voice = opts.voice;
    this.sound = opts.sound;
    this.audio.preload = "auto";
    this.audio.preservesPitch = true;
  }

  get state(): QueueState {
    return { status: this.status, index: this.index, total: this.sentences.length, voice: this.voice, notice: this.notice, error: this.error };
  }

  private emit(change: Partial<{ status: QueueStatus; notice: string | null; error: string | null }> = {}) {
    Object.assign(this, change);
    this.mediaState();
    this.opts.onChange(this.state);
  }

  private get browserVoice() {
    return this.voice.startsWith("browser:");
  }

  /* ---------- controls ---------- */

  play(from = this.index) {
    if (from !== this.index) this.resumeAt = 0;
    this.index = Math.max(0, Math.min(from, this.sentences.length));
    const gen = ++this.generation;
    this.sentenceCtrl?.abort();
    if (!this.release) this.release = claimAudio(() => this.stop());
    this.setupMediaSession();
    this.error = null;
    void this.loop(gen);
  }

  pause() {
    if (this.status !== "playing" && this.status !== "loading") return;
    if (!this.browserVoice && this.audio.src) this.resumeAt = this.audio.currentTime;
    this.generation++;
    this.sentenceCtrl?.abort();
    this.emit({ status: "paused" });
  }

  resume() {
    if (this.status === "paused" || this.status === "idle" || this.status === "error") this.play();
    else if (this.status === "ended") this.play(0);
  }

  toggle() {
    if (this.status === "playing" || this.status === "loading") this.pause();
    else this.resume();
  }

  stop() {
    this.generation++;
    this.sentenceCtrl?.abort();
    this.audio.pause();
    this.audio.removeAttribute("src");
    this.audio.load();
    this.resumeAt = 0;
    this.clearClips();
    this.release?.();
    this.release = null;
    this.clearMediaSession();
    this.emit({ status: "idle" });
  }

  /** Jump to a sentence; keeps playing if it was. */
  seek(index: number) {
    const target = Math.max(0, Math.min(index, this.sentences.length - 1));
    this.resumeAt = 0;
    if (this.status === "playing" || this.status === "loading") this.play(target);
    else {
      this.index = target;
      this.opts.onSentence?.(target);
      this.emit();
    }
  }

  append(more: string[]) {
    this.sentences.push(...more);
    this.emit();
  }

  /** Speed and volume apply at once, to the clip that's playing too. */
  setSound(sound: Sound) {
    const restartBrowser = this.browserVoice && (sound.rate !== this.sound.rate || sound.pitch !== this.sound.pitch) && this.status === "playing";
    this.sound = sound;
    const clip = this.clips.get(this.index);
    if (clip && !this.browserVoice) {
      void clip.clip.then(
        (c) => {
          this.audio.playbackRate = this.sound.rate / c.speed;
        },
        () => {},
      );
    }
    this.audio.volume = Math.min(1, Math.max(0, sound.volume));
    if (restartBrowser) this.play(); // the browser can't change an utterance mid-way
  }

  setVoice(voice: string) {
    if (voice === this.voice) return;
    this.voice = voice;
    this.notice = null;
    this.clearClips();
    this.resumeAt = 0;
    if (this.status === "playing" || this.status === "loading") this.play();
    else this.emit();
  }

  destroy() {
    this.stop();
  }

  /** What the lock screen shows, e.g. when reading moves into the next chapter. */
  setMeta(meta: NonNullable<QueueOptions["meta"]>) {
    this.opts.meta = meta;
    if (this.release && "mediaSession" in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({ title: meta.title, artist: meta.artist ?? "BookMind", album: meta.album ?? "" });
    }
  }

  /* ---------- the reading loop ---------- */

  private async loop(gen: number) {
    while (gen === this.generation) {
      if (this.index >= this.sentences.length) {
        const more = this.opts.onEnd ? await this.opts.onEnd() : false;
        if (gen !== this.generation) return;
        if (more && this.index < this.sentences.length) continue;
        this.release?.();
        this.release = null;
        this.emit({ status: "ended" });
        return;
      }
      const i = this.index;
      this.opts.onSentence?.(i);
      if (gen !== this.generation) return; // paused by onSentence (e.g. a sleep timer at a chapter's end)
      const ctrl = new AbortController();
      this.sentenceCtrl = ctrl;
      try {
        if (this.browserVoice) {
          this.emit({ status: "playing" });
          await speakWithBrowser(this.sentences[i], this.voice, this.sound, ctrl.signal);
        } else {
          this.prefetch(i);
          const pending = this.clips.get(i)!.clip;
          let ready = false;
          void pending.then(
            () => (ready = true),
            () => {},
          );
          await Promise.resolve(); // a clip already synthesized is ready by now
          if (!ready) this.emit({ status: "loading" });
          const clip = await pending;
          if (gen !== this.generation) return;
          if (clip.note && clip.note !== this.notice) this.notice = clip.note;
          this.emit({ status: "playing" });
          await this.playClip(clip, ctrl.signal);
        }
      } catch (e) {
        if (gen !== this.generation) return;
        if (e instanceof TtsUnavailable && canSpeakInBrowser) {
          // nothing on the server can speak: carry on with this device's voice
          this.voice = BROWSER_DEFAULT;
          this.notice = e.message;
          this.clearClips();
          continue;
        }
        this.release?.();
        this.release = null;
        this.emit({ status: "error", error: (e as Error).message });
        return;
      }
      if (gen !== this.generation) return;
      this.resumeAt = 0;
      this.dropClip(i - 1); // keep the one just read, for "previous sentence"
      this.index = i + 1;
    }
  }

  private playClip(clip: Clip, signal: AbortSignal): Promise<void> {
    return new Promise((resolve, reject) => {
      const a = this.audio;
      const startAt = this.resumeAt;
      const cleanup = () => {
        a.onended = a.onerror = null;
        signal.removeEventListener("abort", onAbort);
      };
      const onAbort = () => {
        a.pause();
        cleanup();
        resolve();
      };
      a.onended = () => {
        cleanup();
        resolve();
      };
      a.onerror = () => {
        cleanup();
        reject(new Error("This sentence's audio couldn't be played."));
      };
      signal.addEventListener("abort", onAbort, { once: true });
      if (a.src !== clip.url) a.src = clip.url;
      if (startAt > 0) a.currentTime = startAt;
      a.playbackRate = this.sound.rate / clip.speed;
      a.volume = Math.min(1, Math.max(0, this.sound.volume));
      a.play().catch((e: Error) => {
        if (signal.aborted) return;
        cleanup();
        reject(e.name === "NotAllowedError" ? new Error("The browser blocked playback. Press play again.") : e);
      });
    });
  }

  /* ---------- clips synthesized ahead ---------- */

  private prefetch(from: number) {
    const ahead = this.opts.ahead ?? 3;
    for (let j = from; j <= from + ahead && j < this.sentences.length; j++) {
      if (this.clips.has(j)) continue;
      const ctrl = new AbortController();
      const { asked } = extraRate(this.opts.catalog, this.voice, this.sound.rate);
      const clip = tts.speak({ text: this.sentences[j], voice: this.voice, speed: asked }, ctrl.signal).then((s) => ({
        url: URL.createObjectURL(s.blob),
        speed: asked,
        note: s.note,
      }));
      clip.catch(() => {}); // handled when its turn comes
      this.clips.set(j, { clip, ctrl });
    }
  }

  private dropClip(j: number) {
    const entry = this.clips.get(j);
    if (!entry) return;
    entry.ctrl.abort();
    void entry.clip.then(
      (c) => URL.revokeObjectURL(c.url),
      () => {},
    );
    this.clips.delete(j);
  }

  private clearClips() {
    for (const j of [...this.clips.keys()]) this.dropClip(j);
  }

  /* ---------- lock screen, headphones and media keys ---------- */

  private setupMediaSession() {
    const meta = this.opts.meta;
    if (!meta || !("mediaSession" in navigator)) return;
    const ms = navigator.mediaSession;
    ms.metadata = new MediaMetadata({ title: meta.title, artist: meta.artist ?? "BookMind", album: meta.album ?? "" });
    const handlers: [MediaSessionAction, MediaSessionActionHandler][] = [
      ["play", () => this.resume()],
      ["pause", () => this.pause()],
      ["stop", () => this.stop()],
      ["nexttrack", () => this.seek(this.index + 1)],
      ["previoustrack", () => this.seek(this.index - 1)],
    ];
    for (const [action, handler] of handlers) {
      try {
        ms.setActionHandler(action, handler);
      } catch {
        /* not supported by this browser */
      }
    }
  }

  private mediaState() {
    if (!this.opts.meta || !("mediaSession" in navigator)) return;
    navigator.mediaSession.playbackState =
      this.status === "playing" || this.status === "loading" ? "playing" : this.status === "paused" ? "paused" : "none";
  }

  private clearMediaSession() {
    if (!this.opts.meta || !("mediaSession" in navigator)) return;
    for (const action of ["play", "pause", "stop", "nexttrack", "previoustrack"] as MediaSessionAction[]) {
      try {
        navigator.mediaSession.setActionHandler(action, null);
      } catch {
        /* not supported */
      }
    }
    navigator.mediaSession.metadata = null;
  }
}
