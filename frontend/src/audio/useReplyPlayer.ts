import { useCallback, useEffect, useRef, useState } from "react";
import { tts } from "../api";
import type { User } from "../types";
import { SpeechQueue, type QueueState } from "./queue";
import { resolveVoice, useVoiceCatalog, voicePrefs } from "./voices";

export interface ReplyPlayback extends QueueState {
  message: number; // index of the reply being read
}

/** Plain sentences without the server (offline): a rough split, better than nothing. */
function localSentences(markdown: string): string[] {
  const plain = markdown
    .replace(/\[\d+(?:\s*[,;–-]\s*\d+)*\]/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[*_#>`|]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return (
    plain
      .match(/[^.!?…]+[.!?…]+["'”’)]*|[^.!?…]+$/g)
      ?.map((s) => s.trim())
      .filter(Boolean) ?? []
  );
}

/** Reads chat replies aloud, one at a time, with the account's chat voice and settings. */
export function useReplyPlayer(user: User) {
  const catalog = useVoiceCatalog();
  const prefs = voicePrefs(user);
  const resolved = resolveVoice(catalog, prefs.chatVoice);
  const [playback, setPlayback] = useState<ReplyPlayback | null>(null);
  const queue = useRef<SpeechQueue | null>(null);
  const request = useRef(0);
  const latest = useRef({ catalog, resolved, prefs });
  latest.current = { catalog, resolved, prefs };

  const stop = useCallback(() => {
    request.current++;
    queue.current?.destroy();
    queue.current = null;
    setPlayback(null);
  }, []);

  useEffect(() => stop, [stop]);

  // settings changed (saved in another tab, or Settings) while a reply is playing
  useEffect(() => {
    queue.current?.setSound({ rate: prefs.speed, pitch: prefs.pitch, volume: prefs.volume });
  }, [prefs.speed, prefs.pitch, prefs.volume]);
  useEffect(() => {
    queue.current?.setVoice(resolved.id);
  }, [resolved.id]);

  /** Listen to a reply; on the reply already playing, pause or resume it. */
  const listen = useCallback(
    async (message: number, markdown: string) => {
      if (queue.current && playback?.message === message && playback.status !== "ended" && playback.status !== "error") {
        queue.current.toggle();
        return;
      }
      stop();
      const mine = ++request.current;
      const { catalog, resolved, prefs } = latest.current;
      setPlayback({ message, status: "loading", index: 0, total: 0, voice: resolved.id, notice: resolved.notice, error: null });
      let sentences: string[];
      try {
        sentences = (await tts.sentences(markdown)).sentences;
      } catch {
        sentences = localSentences(markdown);
      }
      if (mine !== request.current) return; // another reply was started meanwhile
      if (!sentences.length) {
        setPlayback(null);
        return;
      }
      const q = new SpeechQueue(sentences, {
        catalog,
        voice: resolved.id,
        sound: { rate: prefs.speed, pitch: prefs.pitch, volume: prefs.volume },
        onChange: (s) => {
          if (queue.current !== q) return;
          if (s.status === "idle") {
            // stopped, e.g. because the book reader or a preview started playing
            queue.current = null;
            setPlayback(null);
            return;
          }
          setPlayback({ ...s, message, notice: s.notice ?? resolved.notice });
        },
      });
      queue.current = q;
      q.play();
    },
    [playback, stop],
  );

  return { playback, listen, stop, autoRead: prefs.autoRead };
}
