import { describe, expect, it } from "vitest";
import type { TtsProvider, TtsVoice } from "../api";
import type { User } from "../types";
import { BROWSER_DEFAULT, findVoice, resolveVoice, voiceLabel, voicePrefs, type VoiceCatalog } from "./voices";

const voice = (id: string, extra: Partial<TtsVoice> = {}): TtsVoice => ({
  id,
  provider: id.split(":")[0],
  name: id.split(":")[1] || "Default",
  language: "en-US",
  accent: "",
  gender: "",
  quality: "",
  ...extra,
});

const provider = (id: string, voices: TtsVoice[], available = true): TtsProvider => ({
  id,
  label: id,
  available,
  reason: available ? "" : "offline",
  client_side: id === "browser",
  supports_streaming: false,
  speed_range: [0.5, 2],
  pitch: false,
  volume: true,
  voices,
});

const amy = voice("piper:amy", { name: "Amy", accent: "American", gender: "female" });
const ryan = voice("piper:ryan", { name: "Ryan", accent: "British", gender: "male" });
const nova = voice("cloud:nova", { name: "Nova" });
const zira = voice("browser:zira", { name: "Zira", accent: "American", gender: "female" });

function catalog(over: Partial<VoiceCatalog> = {}, providers?: TtsProvider[]): VoiceCatalog {
  return {
    providers: providers ?? [provider("piper", [amy, ryan]), provider("cloud", [nova], false), provider("browser", [zira])],
    default_voice: "piper:amy",
    max_chars: 1500,
    loading: false,
    error: null,
    ...over,
  };
}

describe("voiceLabel", () => {
  it("names the device default", () => {
    expect(voiceLabel(null)).toBe("Device default voice");
  });
  it("adds accent and gender when known", () => {
    expect(voiceLabel(amy)).toBe("Amy — American, female");
    expect(voiceLabel(voice("piper:x", { name: "X", gender: "male" }))).toBe("X — male");
    expect(voiceLabel(nova)).toBe("Nova");
  });
});

describe("findVoice", () => {
  it("finds a voice in an available provider", () => {
    const hit = findVoice(catalog(), "piper:ryan");
    expect(hit?.provider.id).toBe("piper");
    expect(hit?.voice).toBe(ryan);
  });
  it("is null for an unknown provider or voice", () => {
    expect(findVoice(catalog(), "nope:amy")).toBeNull();
    expect(findVoice(catalog(), "piper:nobody")).toBeNull();
  });
  it("is null for a voice whose provider is unavailable", () => {
    expect(findVoice(catalog(), "cloud:nova")).toBeNull();
  });
  it("gives the browser default as a voice-less hit", () => {
    expect(findVoice(catalog(), BROWSER_DEFAULT)).toEqual({ provider: expect.objectContaining({ id: "browser" }), voice: null });
  });
  it("has no browser default when the browser can't speak", () => {
    // jsdom has no speechSynthesis, so only the provider's own availability counts
    const c = catalog({}, [provider("browser", [], false)]);
    expect(findVoice(c, BROWSER_DEFAULT)).toBeNull();
  });
});

describe("resolveVoice", () => {
  it("uses the saved voice when it's available", () => {
    expect(resolveVoice(catalog(), "piper:ryan")).toEqual({
      id: "piper:ryan",
      provider: expect.objectContaining({ id: "piper" }),
      voice: ryan,
      notice: null,
    });
  });
  it("uses the server's default for an empty choice", () => {
    const r = resolveVoice(catalog(), "");
    expect(r.id).toBe("piper:amy");
    expect(r.notice).toBeNull();
  });
  it("falls back to the default voice, with a notice, when the saved one is gone", () => {
    const r = resolveVoice(catalog(), "cloud:nova");
    expect(r.id).toBe("piper:amy");
    expect(r.voice).toBe(amy);
    expect(r.notice).toBe("Your saved voice isn't available any more, so Amy is used instead.");
  });
  it("falls back to the browser default when the default voice is gone too", () => {
    const c = catalog({ default_voice: "cloud:nova" });
    const r = resolveVoice(c, "piper:gone");
    expect(r.id).toBe(BROWSER_DEFAULT);
    expect(r.provider?.id).toBe("browser");
    expect(r.voice).toBeNull();
    expect(r.notice).toBe("Your saved voice isn't available any more, so Device default voice is used instead.");
  });
  it("keeps the default voice id when it is the browser default", () => {
    const r = resolveVoice(catalog({ default_voice: BROWSER_DEFAULT }), "piper:gone");
    expect(r.id).toBe(BROWSER_DEFAULT);
    expect(r.voice).toBeNull();
  });
  it("falls back to the browser default id when nothing at all can speak", () => {
    const c = catalog({ default_voice: "cloud:nova" }, [provider("cloud", [nova], false), provider("browser", [], false)]);
    expect(resolveVoice(c, "cloud:nova")).toMatchObject({ id: BROWSER_DEFAULT, provider: null, voice: null });
  });
  it("doesn't complain while the catalog is loading", () => {
    expect(resolveVoice(catalog({ loading: true }), "cloud:nova").notice).toBeNull();
  });
  it("doesn't complain about a browser voice before the browser has listed its voices", () => {
    const c = catalog({}, [provider("piper", [amy]), provider("browser", [])]);
    const r = resolveVoice(c, "browser:zira");
    expect(r.id).toBe("piper:amy");
    expect(r.notice).toBeNull();
  });
  it("does complain about a browser voice that's missing once voices are listed", () => {
    expect(resolveVoice(catalog(), "browser:gone").notice).toContain("Amy is used instead");
  });
});

describe("voicePrefs", () => {
  it("fills in defaults", () => {
    expect(voicePrefs({ settings: {} } as User)).toEqual({
      chatVoice: "",
      readVoice: "",
      speed: 1,
      pitch: 1,
      volume: 1,
      autoRead: false,
      announceVerses: true, // books with verses: on by default
      announceChapter: true,
    });
  });
  it("reads saved settings", () => {
    const user = {
      settings: {
        tts_chat_voice: "piper:amy",
        tts_read_voice: "browser:",
        tts_speed: 1.5,
        tts_pitch: 0.8,
        tts_volume: 0.5,
        tts_auto_read: true,
        tts_announce_verses: "off",
        tts_announce_chapter: false,
      },
    };
    expect(voicePrefs(user as unknown as User)).toEqual({
      chatVoice: "piper:amy",
      readVoice: "browser:",
      speed: 1.5,
      pitch: 0.8,
      volume: 0.5,
      autoRead: true,
      announceVerses: false,
      announceChapter: false,
    });
  });
});
