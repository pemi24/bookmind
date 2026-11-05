import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, tts, TtsUnavailable, type SpokenAudio, type TtsCatalog } from "../api";
import { speakWithBrowser } from "./playback";
import { SpeechQueue, type QueueOptions, type QueueState } from "./queue";

vi.mock("../api", async (importOriginal) => {
  const api = await importOriginal<typeof import("../api")>();
  return { ...api, tts: { ...api.tts, speak: vi.fn() } };
});
vi.mock("./playback", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./playback")>()),
  speakWithBrowser: vi.fn(() => Promise.resolve()),
}));
// jsdom has no speechSynthesis; pretend this device can speak so the fallback is possible.
vi.mock("./voices", async (importOriginal) => ({ ...(await importOriginal<typeof import("./voices")>()), canSpeakInBrowser: true }));

/** Stands in for the one <audio> element a queue plays its clips through. */
class FakeAudio {
  static all: FakeAudio[] = [];
  src = "";
  currentTime = 0;
  playbackRate = 1;
  volume = 1;
  preload = "";
  preservesPitch = false;
  paused = true;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  plays: { src: string; at: number }[] = [];
  constructor() {
    FakeAudio.all.push(this);
  }
  play() {
    this.paused = false;
    this.plays.push({ src: this.src, at: this.currentTime });
    return Promise.resolve();
  }
  pause() {
    this.paused = true;
  }
  load() {}
  removeAttribute(name: string) {
    if (name === "src") this.src = "";
  }
  /** The clip playing reaches its end. */
  finish() {
    this.paused = true;
    this.onended?.();
  }
}

const speak = vi.mocked(tts.speak);
const browserSpeak = vi.mocked(speakWithBrowser);
const flush = async () => {
  for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0));
};

const catalog: TtsCatalog = {
  providers: [
    {
      id: "piper",
      label: "Piper",
      available: true,
      reason: "",
      client_side: false,
      supports_streaming: false,
      speed_range: [0.5, 2],
      pitch: false,
      volume: true,
      voices: [{ id: "piper:amy", provider: "piper", name: "Amy", language: "en-US", accent: "", gender: "", quality: "" }],
    },
  ],
  default_voice: "piper:amy",
  max_chars: 1500,
};

let created: string[];
let revoked: string[];
let states: QueueState[];
let sentences: number[];

function makeQueue(texts: string[], opts: Partial<QueueOptions> = {}) {
  const q = new SpeechQueue(texts, {
    catalog,
    voice: "piper:amy",
    sound: { rate: 1, pitch: 1, volume: 1 },
    onChange: (s) => states.push(s),
    onSentence: (i) => sentences.push(i),
    ...opts,
  });
  return { q, audio: FakeAudio.all[FakeAudio.all.length - 1] };
}

const spokenTexts = () => speak.mock.calls.map(([body]) => body.text);

beforeEach(() => {
  FakeAudio.all = [];
  created = [];
  revoked = [];
  states = [];
  sentences = [];
  vi.stubGlobal("Audio", FakeAudio);
  let n = 0;
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => {
      const url = `blob:clip-${n++}`;
      created.push(url);
      return url;
    }),
    revokeObjectURL: vi.fn((url: string) => revoked.push(url)),
  });
  speak.mockReset();
  speak.mockImplementation(async (body) => ({ blob: new Blob([body.text]), voice: body.voice, note: null }) as SpokenAudio);
  browserSpeak.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SpeechQueue with a server voice", () => {
  it("reads the sentences in order and ends", async () => {
    const { q, audio } = makeQueue(["One.", "Two.", "Three."]);
    q.play();
    await flush();
    expect(q.state.status).toBe("playing");
    for (let i = 0; i < 3; i++) {
      expect(q.state.index).toBe(i);
      audio.finish();
      await flush();
    }
    expect(sentences).toEqual([0, 1, 2]);
    expect(audio.plays.map((p) => p.src)).toEqual(["blob:clip-0", "blob:clip-1", "blob:clip-2"]);
    expect(spokenTexts()).toEqual(["One.", "Two.", "Three."]);
    expect(q.state).toMatchObject({ status: "ended", index: 3, total: 3 });
  });

  it("synthesizes only a few clips ahead of the one playing", async () => {
    const texts = Array.from({ length: 10 }, (_, i) => `S${i}.`);
    const { q, audio } = makeQueue(texts, { ahead: 2 });
    q.play();
    await flush();
    expect(spokenTexts()).toEqual(["S0.", "S1.", "S2."]);
    audio.finish();
    await flush();
    expect(spokenTexts()).toEqual(["S0.", "S1.", "S2.", "S3."]);
    q.stop();
  });

  it("shows loading until a slow clip arrives", async () => {
    let arrive!: (s: SpokenAudio) => void;
    speak.mockImplementationOnce(() => new Promise((r) => (arrive = r)));
    const { q } = makeQueue(["Slow."]);
    q.play();
    await flush();
    expect(q.state.status).toBe("loading");
    arrive({ blob: new Blob(["x"]), voice: "piper:amy", note: "Amy was busy" });
    await flush();
    expect(q.state).toMatchObject({ status: "playing", notice: "Amy was busy" });
    q.stop();
  });

  it("pauses and resumes where it stopped in the clip", async () => {
    const { q, audio } = makeQueue(["One.", "Two."]);
    q.play();
    await flush();
    audio.currentTime = 1.5;
    q.pause();
    expect(q.state.status).toBe("paused");
    expect(audio.paused).toBe(true);
    q.resume();
    await flush();
    expect(q.state).toMatchObject({ status: "playing", index: 0 });
    expect(audio.plays).toEqual([
      { src: "blob:clip-0", at: 0 },
      { src: "blob:clip-0", at: 1.5 },
    ]);
    expect(speak).toHaveBeenCalledTimes(2); // the clip was kept, not synthesized again
    q.toggle();
    expect(q.state.status).toBe("paused");
    q.stop();
  });

  it("seeks while paused without playing, and while playing by restarting there", async () => {
    const { q, audio } = makeQueue(["A.", "B.", "C.", "D."]);
    q.seek(2);
    expect(q.state).toMatchObject({ status: "idle", index: 2 });
    expect(sentences).toEqual([2]);
    expect(speak).not.toHaveBeenCalled();

    q.play();
    await flush();
    expect(audio.plays.at(-1)?.src).toBe(created[0]);
    expect(spokenTexts()[0]).toBe("C.");
    q.seek(99); // clamped to the last sentence
    await flush();
    expect(q.state).toMatchObject({ status: "playing", index: 3 });
    expect(audio.plays.at(-1)?.src).toBe(created[1]); // "D." was already prefetched
    const asked = speak.mock.calls.length;
    q.seek(-5);
    await flush();
    expect(q.state.index).toBe(0);
    expect(spokenTexts().slice(asked)).toEqual(["A.", "B."]); // C. and D. are still held
    q.stop();
  });

  it("restarts from the beginning when resumed after the end", async () => {
    const { q, audio } = makeQueue(["Only."]);
    q.play();
    await flush();
    audio.finish();
    await flush();
    expect(q.state.status).toBe("ended");
    q.resume();
    await flush();
    expect(q.state).toMatchObject({ status: "playing", index: 0 });
    q.stop();
  });

  it("asks for more sentences at the end", async () => {
    let calls = 0;
    const onEnd = vi.fn(() => {
      if (calls++ > 0) return false;
      q.append(["Next chapter."]);
      return true;
    });
    const { q, audio } = makeQueue(["Last of chapter one."], { onEnd });
    q.play();
    await flush();
    audio.finish();
    await flush();
    expect(q.state).toMatchObject({ status: "playing", index: 1, total: 2 });
    audio.finish();
    await flush();
    expect(q.state.status).toBe("ended");
    expect(onEnd).toHaveBeenCalledTimes(2);
  });

  it("frees each clip's blob URL once it's no longer needed", async () => {
    const { q, audio } = makeQueue(["A.", "B.", "C.", "D.", "E."], { ahead: 1 });
    q.play();
    await flush();
    audio.finish(); // A done: kept for "previous sentence"
    await flush();
    expect(revoked).toEqual([]);
    audio.finish(); // B done: A is dropped
    await flush();
    expect(revoked).toEqual(["blob:clip-0"]);
    q.stop(); // everything still held is freed
    await flush();
    expect(new Set(revoked)).toEqual(new Set(created));
    expect(audio.src).toBe("");
  });

  it("frees the clips when the voice changes", async () => {
    const { q } = makeQueue(["A.", "B."]);
    q.play();
    await flush();
    const before = [...created];
    q.setVoice("piper:other");
    await flush();
    expect(revoked).toEqual(expect.arrayContaining(before));
    expect(speak.mock.calls.slice(2).map(([body]) => [body.text, body.voice])).toEqual([
      ["A.", "piper:other"],
      ["B.", "piper:other"],
    ]);
    q.stop();
  });

  it("carries on with the browser's voice when no server voice can speak", async () => {
    speak.mockRejectedValue(new TtsUnavailable("No voice on the server could speak.", 503));
    const { q } = makeQueue(["One.", "Two."]);
    q.play();
    await flush();
    expect(browserSpeak.mock.calls.map(([text, voice]) => [text, voice])).toEqual([
      ["One.", "browser:"],
      ["Two.", "browser:"],
    ]);
    expect(q.state).toMatchObject({ status: "ended", voice: "browser:", notice: "No voice on the server could speak." });
  });

  it("stops with an error for any other failure", async () => {
    speak.mockRejectedValue(new ApiError("Text too long", 400));
    const { q } = makeQueue(["One."]);
    q.play();
    await flush();
    expect(q.state).toMatchObject({ status: "error", error: "Text too long" });
    expect(browserSpeak).not.toHaveBeenCalled();
  });

  it("reports a clip the browser can't play", async () => {
    const { q, audio } = makeQueue(["One."]);
    q.play();
    await flush();
    audio.onerror?.();
    await flush();
    expect(q.state).toMatchObject({ status: "error", error: "This sentence's audio couldn't be played." });
  });

  it("applies a new speed to the clip that's playing", async () => {
    const { q, audio } = makeQueue(["One."]);
    q.play();
    await flush();
    q.setSound({ rate: 1.5, pitch: 1, volume: 2 });
    await flush();
    expect(audio.playbackRate).toBe(1.5);
    expect(audio.volume).toBe(1);
    q.stop();
  });
});

describe("SpeechQueue with a browser voice", () => {
  it("speaks each sentence with the browser, not the server", async () => {
    const { q } = makeQueue(["One.", "Two."], { voice: "browser:zira" });
    q.play();
    await flush();
    expect(browserSpeak.mock.calls.map(([text, voice]) => [text, voice])).toEqual([
      ["One.", "browser:zira"],
      ["Two.", "browser:zira"],
    ]);
    expect(speak).not.toHaveBeenCalled();
    expect(q.state.status).toBe("ended");
  });

  it("aborts the sentence being spoken on pause", async () => {
    let signal: AbortSignal | undefined;
    browserSpeak.mockImplementationOnce((_t, _v, _s, sig) => {
      signal = sig;
      return new Promise((r) => sig?.addEventListener("abort", () => r()));
    });
    const { q } = makeQueue(["One.", "Two."], { voice: "browser:" });
    q.play();
    await flush();
    expect(q.state.status).toBe("playing");
    q.pause();
    await flush();
    expect(signal?.aborted).toBe(true);
    expect(q.state).toMatchObject({ status: "paused", index: 0 });
    q.stop();
  });
});
