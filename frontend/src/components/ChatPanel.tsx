import { BookmarkPlus, BookOpen, Copy, History, Loader2, Mic, MicOff, Pause, Pencil, Play, Plus, Quote, RotateCcw, SendHorizonal, Square, Trash2, Volume2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, streamChat } from "../api";
import { useReplyPlayer, type ReplyPlayback } from "../audio/useReplyPlayer";
import type { ChatMessage, ConversationSummary, Source, Style } from "../types";
import { useWorkspace } from "../workspace";
import AnswerMarkdown, { stripCitations } from "./AnswerMarkdown";
import { Segmented } from "./ui";

const STYLES: { value: Style; label: string }[] = [
  { value: "default", label: "Normal" },
  { value: "eli5", label: "ELI5" },
  { value: "student", label: "Student" },
  { value: "expert", label: "Expert" },
  { value: "analogy", label: "Analogy" },
];

type Mode = "ask" | "persona" | "compare";

/* ---------- Web Speech API (optional; feature-detected) ---------- */
/* eslint-disable @typescript-eslint/no-explicit-any -- speech recognition isn't in TypeScript's DOM types */
const SpeechRecognitionImpl: any =
  typeof window !== "undefined" ? (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition : undefined;
/* eslint-enable @typescript-eslint/no-explicit-any */

function plainText(markdown: string): string {
  return markdown.replace(/\[\d+(?:\s*[,–-]\s*\d+)*\]/g, "").replace(/[*_#>`]/g, "").replace(/\s+/g, " ").trim();
}

// Mirrors the server's is_not_found(): models word "not in the book" many ways.
const NOT_FOUND =
  /(?:does|do|did)(?:n.?t| not) (?:say|state|mention|tell|specify|name|reveal|contain|include|provide|give|show|indicate|identify|explain)|(?:could|can)(?:n.?t| ?not) find|not (?:mentioned|stated|specified|named|given|provided|found|covered|in the (?:book|passages))|no (?:information|mention)/i;

// Mirrors starter_questions() on the server: the book's own suggestions, topped up with general ones.
/* ---------- Welcome greeting: "{title}" marks where the book's title goes ---------- */
const GREETINGS = [
  "Hello! How can I assist you with {title}?",
  "Hi there! What would you like to know about {title}?",
  "Welcome! How can I help you with {title} today?",
  "Hello! What can I help you find in {title}?",
  "Hi! What would you like to explore in {title}?",
  "Ready to dive into {title}?",
  "Where shall we start with {title}?",
  "What's on your mind about {title}?",
  "Let's talk about {title}. What would you like to know?",
  "Curious about something in {title}?",
  "Good to see you! What shall we discover in {title} today?",
  "Pull up a chair. What would you like to explore in {title}?",
  "Happy reading! How can I help with {title}?",
  "Let's open {title} together. What would you like to know?",
  "Studying {title}? Ask me anything, from characters to themes.",
  "What part of {title} would you like to understand better?",
  "Need help with {title}? Ask about a chapter, a character or a quote.",
];
const RETURNING_GREETINGS = ["Welcome back to {title}. What are you wondering about?"];
const TIME_GREETINGS: { from: number; to: number; text: string }[] = [
  { from: 5, to: 12, text: "Good morning! What shall we explore in {title} today?" },
  { from: 12, to: 17, text: "Good afternoon! How can I help with {title}?" },
  { from: 17, to: 22, text: "Good evening! Settling in with {title}?" },
  { from: 22, to: 29, text: "Late-night reading? What would you like to know about {title}?" }, // 22:00-04:59
];

/** A greeting for a new chat: any general one, the one for this time of day, "welcome back" for a returning reader. */
function pickGreeting(returning: boolean, hour = new Date().getHours()): [string, string] {
  const h = hour < 5 ? hour + 24 : hour;
  const pool = [
    ...GREETINGS,
    ...TIME_GREETINGS.filter((g) => h >= g.from && h < g.to).map((g) => g.text),
    ...(returning ? RETURNING_GREETINGS : []),
  ];
  const [before, after] = pool[Math.floor(Math.random() * pool.length)].split("{title}");
  return [before, after ?? ""];
}

const DEFAULT_STARTERS = ["What is this book about?", "Who are the main characters?", "Summarize the first chapter.", "What are the main themes?"];

function starterQuestions(suggested: string[]): string[] {
  const out = suggested.filter((q) => q.trim());
  for (const q of DEFAULT_STARTERS) {
    if (out.length >= 5) break;
    if (!out.includes(q)) out.push(q);
  }
  return out.slice(0, 5);
}

/** How many source chips SourceList would show for this answer. */
function sourceCount(m: ChatMessage): number {
  if (m.cited.length) return m.sources.filter((s) => m.cited.includes(s.marker)).length;
  return NOT_FOUND.test(m.content) ? 0 : Math.min(m.sources.length, 3);
}

const replyAction = "flex items-center gap-1 rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800";

/** Listen to a reply: play/pause, stop, and how far it has got. */
function ReplyAudio({ playback, onListen, onStop }: { playback: ReplyPlayback | null; onListen: () => void; onStop: () => void }) {
  if (!playback)
    return (
      <button onClick={onListen} className={replyAction} title="Read this answer aloud">
        <Volume2 size={14} /> Listen
      </button>
    );
  const { status, index, total, notice, error } = playback;
  const busy = status === "loading";
  const playing = status === "playing" || busy;
  const done = status === "ended";
  const progress = total ? Math.min(1, (done ? total : index + (playing && !busy ? 0.5 : 0)) / total) : 0;
  return (
    <div className="flex basis-full flex-col gap-1 sm:basis-auto">
      <div className="flex items-center gap-1" role="group" aria-label="Listening">
        <button onClick={onListen} className={`${replyAction} font-medium text-brand-700 dark:text-brand-300`} title={playing ? "Pause (keeps your place)" : done ? "Listen again" : "Resume"}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : playing ? <Pause size={14} /> : <Play size={14} />}
          {busy ? (index === 0 ? "Preparing…" : "Loading…") : playing ? "Pause" : done ? "Again" : "Resume"}
        </button>
        <button onClick={onStop} className={replyAction} title="Stop reading">
          <Square size={13} /> Stop
        </button>
        {total > 0 && (
          <span className="flex items-center gap-1.5 px-1 text-xs text-stone-400 tabular-nums" aria-live="off">
            <span className="h-1 w-16 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-700">
              <span className="block h-full bg-brand-500 transition-all" style={{ width: `${progress * 100}%` }} />
            </span>
            {done ? "Done" : `${Math.min(index + 1, total)}/${total}`}
          </span>
        )}
      </div>
      {(error || notice) && <p className={`px-2 text-xs ${error ? "text-red-600 dark:text-red-400" : "text-amber-700 dark:text-amber-400"}`}>{error ?? notice}</p>}
    </div>
  );
}

function SourceList({ sources, cited, answer, onCite }: { sources: Source[]; cited: number[]; answer: string; onCite: (s: Source) => void }) {
  // Small local models sometimes forget the [n] markers: still show what the answer was based on.
  const fallback = cited.length === 0 && !NOT_FOUND.test(answer);
  const shown = fallback ? sources.slice(0, 3) : sources.filter((s) => cited.includes(s.marker));
  if (!shown.length) return null;
  const multiBook = new Set(sources.map((s) => s.book_id)).size > 1;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      {fallback && <span className="text-xs text-stone-400">Based on passages:</span>}
      {shown.map((s) => (
        <button
          key={s.marker}
          onClick={() => onCite(s)}
          className="flex max-w-full items-center gap-1.5 rounded-lg border border-stone-200 bg-stone-50 px-2 py-1 text-left text-xs text-stone-600 transition hover:border-brand-400 hover:text-brand-700 dark:border-stone-700 dark:bg-stone-800/60 dark:text-stone-300 dark:hover:text-brand-200"
        >
          <span className="font-semibold text-brand-600 dark:text-brand-300">[{s.marker}]</span>
          <span className="truncate">
            {multiBook ? `${s.book_title} · ` : ""}
            {s.chapter_title}
            {s.page_start ? ` · p. ${s.page_start}` : ""}
          </span>
        </button>
      ))}
    </div>
  );
}

export default function ChatPanel({ onCite }: { onCite: (s: Source) => void }) {
  const { book, books, maxChapter, saveNote, notify, user } = useWorkspace();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [style, setStyle] = useState<Style>("default");
  const [mode, setMode] = useState<Mode>("ask");
  const [persona, setPersona] = useState("");
  const [characters, setCharacters] = useState<string[]>([]);
  const [compareIds, setCompareIds] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [listening, setListening] = useState(false);
  const { playback, listen, stop: stopListening, autoRead } = useReplyPlayer(user);
  const [editing, setEditing] = useState<{ index: number; text: string } | null>(null);
  const [citesShown, setCitesShown] = useState<Set<number>>(new Set()); // answers whose sources are visible
  const [greetingSeed, setGreetingSeed] = useState(0); // new chat -> new greeting
  const abortRef = useRef<AbortController | null>(null);
  const recRef = useRef<{ stop: () => void } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const others = books.filter((b) => b.id !== book.id && b.status === "ready");

  const [historyFor, setHistoryFor] = useState<number | null>(null); // book whose chat history has loaded
  const loadConversations = useCallback(() => {
    api
      .conversations(book.id)
      .then(setConversations)
      .catch(() => {})
      .finally(() => setHistoryFor(book.id));
  }, [book.id]);

  // Picked once the history is known (so "welcome back" can apply) and again for each new chat.
  const historyReady = historyFor === book.id;
  const greeting = useMemo(
    () => pickGreeting(conversations.length > 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [book.id, greetingSeed, historyReady],
  );

  useEffect(() => {
    abortRef.current?.abort();
    stopListening();
    setConversationId(null);
    setMessages([]);
    setCitesShown(new Set());
    setEditing(null);
    setMode("ask");
    setCompareIds([]);
    setPersona("");
    loadConversations();
  }, [book.id, loadConversations, stopListening]);

  // Character names for persona mode (if the book has been analyzed), within the spoiler limit.
  useEffect(() => {
    api
      .entities(book.id, maxChapter)
      .then((r) => setCharacters(r.entities.filter((e) => e.kind === "character").map((e) => e.name)))
      .catch(() => setCharacters([]));
  }, [book.id, maxChapter]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => () => {
    abortRef.current?.abort();
    recRef.current?.stop();
  }, []);

  // Auto-read: a reply that has just finished arriving starts playing (not ones loaded from history).
  const lastPending = useRef(false);
  useEffect(() => {
    const last = messages[messages.length - 1];
    const wasPending = lastPending.current;
    lastPending.current = !!(last?.role === "assistant" && last.pending);
    if (autoRead && wasPending && last?.role === "assistant" && !last.pending && last.content && !last.error) {
      void listen(messages.length - 1, last.content);
    }
  }, [messages, autoRead, listen]);

  const openConversation = async (id: number) => {
    setShowHistory(false);
    abortRef.current?.abort();
    stopListening();
    const c = await api.conversation(id);
    setConversationId(id);
    setMessages(c.messages);
    setCitesShown(new Set());
    setEditing(null);
    setMode(c.mode === "persona" ? "persona" : c.mode === "compare" ? "compare" : "ask");
    setPersona(c.persona ?? "");
    setCompareIds(c.book_ids.filter((b) => b !== book.id));
  };

  const newConversation = () => {
    abortRef.current?.abort();
    stopListening();
    setConversationId(null);
    setMessages([]);
    setCitesShown(new Set());
    setEditing(null);
    setGreetingSeed((n) => n + 1);
  };

  const changeMode = (m: Mode) => {
    setMode(m);
    newConversation(); // modes are per conversation
  };

  const toggleCites = (i: number) =>
    setCitesShown((s) => {
      const next = new Set(s);
      if (!next.delete(i)) next.add(i);
      return next;
    });

  const updateLast = (fn: (m: ChatMessage) => ChatMessage) => setMessages((ms) => [...ms.slice(0, -1), fn(ms[ms.length - 1])]);

  /** Send a question. With `resendAt`, the user message at that index (and everything after it) is replaced. */
  const send = async (text: string, resendAt?: number) => {
    const q = text.trim();
    if (!q || busy) return;
    const replaced = resendAt !== undefined ? messages[resendAt] : undefined;
    if (mode === "persona" && !persona.trim()) {
      notify("Choose a character to talk to first.");
      return;
    }
    if (mode === "compare" && compareIds.length === 0) {
      notify("Pick at least one other book to compare with.");
      return;
    }
    if (resendAt === undefined) setInput("");
    setEditing(null);
    if (resendAt !== undefined) setCitesShown((s) => new Set([...s].filter((j) => j < resendAt)));
    setBusy(true);
    setMessages((ms) => [
      ...(resendAt !== undefined ? ms.slice(0, resendAt) : ms),
      { role: "user", content: q, sources: [], cited: [] },
      { role: "assistant", content: "", sources: [], cited: [], pending: true, stage: "searching" },
    ]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    await streamChat(
      book.id,
      {
        message: q,
        conversation_id: conversationId,
        style,
        spoiler_chapter: maxChapter,
        persona: mode === "persona" ? persona.trim() : null,
        compare_book_ids: mode === "compare" ? compareIds : [],
        // Without a saved id (e.g. the first send failed early) there is nothing to replace server-side.
        resend_from: replaced?.id ?? null,
      },
      {
        onConversation: (id, userMessageId) => {
          setConversationId(id);
          setMessages((ms) => ms.map((m, j) => (j === ms.length - 2 ? { ...m, id: userMessageId } : m)));
        },
        onStage: (stage) => updateLast((m) => ({ ...m, stage })),
        onSources: (sources) => updateLast((m) => ({ ...m, sources })),
        onReset: () => updateLast((m) => ({ ...m, content: "", cited: [] })),
        onDelta: (t) => updateLast((m) => ({ ...m, content: m.content + t })),
        onDone: (id, cited) => updateLast((m) => ({ ...m, id, cited, pending: false })),
        onError: (error) => updateLast((m) => ({ ...m, error, pending: false })),
      },
      ctrl.signal,
    );
    updateLast((m) => ({ ...m, pending: false }));
    setBusy(false);
    loadConversations();
  };

  const stop = () => {
    abortRef.current?.abort();
    lastPending.current = false; // a reply cut short isn't read aloud automatically
    updateLast((m) => ({ ...m, pending: false, error: m.content ? undefined : "Stopped." }));
    setBusy(false);
  };

  const deleteConversation = async (c: ConversationSummary) => {
    if (!confirm(`Delete the chat “${c.title}”? This cannot be undone.`)) return;
    try {
      await api.deleteConversation(c.id);
      if (c.id === conversationId) newConversation();
    } catch (e) {
      notify((e as Error).message);
    }
    loadConversations();
  };

  const [renaming, setRenaming] = useState<{ id: number; title: string } | null>(null);
  const saveRename = async () => {
    if (!renaming) return;
    const title = renaming.title.trim();
    setRenaming(null);
    if (!title) return;
    setConversations((cs) => cs.map((c) => (c.id === renaming.id ? { ...c, title } : c)));
    try {
      await api.renameConversation(renaming.id, title.slice(0, 120));
    } catch (e) {
      notify((e as Error).message);
      loadConversations();
    }
  };

  const toggleMic = () => {
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const rec = new SpeechRecognitionImpl();
    rec.lang = navigator.language || "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    const base = input ? input.trimEnd() + " " : "";
    rec.onresult = (e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => {
      const text = Array.from(e.results).map((r) => r[0].transcript).join("");
      setInput(base + text);
    };
    rec.onerror = (e: { error: string }) => {
      if (e.error === "not-allowed") notify("Microphone access was blocked by the browser.");
      else if (e.error !== "aborted" && e.error !== "no-speech") notify(`Voice input error: ${e.error}`);
    };
    rec.onend = () => setListening(false);
    recRef.current = rec;
    rec.start();
    setListening(true);
  };


  const saveAnswer = (i: number, m: ChatMessage) => {
    const question = messages[i - 1]?.role === "user" ? messages[i - 1].content : undefined;
    const first = m.sources.find((s) => m.cited.includes(s.marker));
    saveNote({
      kind: "answer",
      title: question ? question.slice(0, 200) : null,
      content: m.content,
      message_id: m.id ?? null,
      chunk_id: first?.chunk_id ?? null,
      tags: [],
      location: first ? { chapter_id: first.chapter_id, chapter_title: first.chapter_title, page: first.page_start, char_start: first.char_start, char_end: first.char_end } : {},
    });
  };

  const placeholder =
    mode === "persona" && persona ? `Say something to ${persona}…` : mode === "compare" ? "Ask a question across the selected books…" : "Ask a question about the book…";

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Toolbar */}
      <div className="relative flex flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-stone-200 px-2 py-1.5 sm:px-4 dark:border-stone-800">
        <button
          onClick={() => setShowHistory((v) => !v)}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800"
        >
          <History size={16} /> <span className="hidden sm:inline">History</span>
          {conversations.length ? ` (${conversations.length})` : ""}
        </button>
        <button onClick={newConversation} className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800">
          <Plus size={16} /> <span className="whitespace-nowrap">New chat</span>
        </button>
        <Segmented
          value={mode}
          onChange={changeMode}
          label="Chat mode"
          options={[
            { value: "ask", label: "Ask the book" },
            { value: "persona" as Mode, label: "Talk to a character" }, // people in non-fiction count too (a Bible, a biography)
            ...(others.length ? [{ value: "compare" as Mode, label: "Compare books" }] : []),
          ]}
        />
        <div className="ml-auto max-w-full min-w-0">
          <Segmented value={style} onChange={setStyle} label="Answer style" options={STYLES} />
        </div>

        {mode === "persona" && (
          <div className="flex w-full items-center gap-2 text-sm">
            <label htmlFor="persona" className="text-stone-500">Character:</label>
            <input
              id="persona"
              list="persona-options"
              value={persona}
              onChange={(e) => {
                setPersona(e.target.value);
                if (conversationId) newConversation();
              }}
              placeholder={characters.length ? "Pick or type a name" : "Type a character's name"}
              className="min-w-0 flex-1 rounded-md border border-stone-300 bg-transparent px-2 py-1 sm:max-w-xs dark:border-stone-700"
            />
            <datalist id="persona-options">
              {characters.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            {!characters.length && <span className="hidden text-xs text-stone-400 sm:inline">Run Explore → Analyze for suggestions</span>}
          </div>
        )}
        {mode === "compare" && (
          <div className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="text-stone-500">Compare with:</span>
            {others.map((b) => (
              <label key={b.id} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  className="accent-brand-600"
                  checked={compareIds.includes(b.id)}
                  onChange={(e) => {
                    setCompareIds((ids) => (e.target.checked ? [...ids, b.id] : ids.filter((x) => x !== b.id)));
                    if (conversationId) newConversation();
                  }}
                />
                <span className="max-w-[14rem] truncate">{b.title}</span>
              </label>
            ))}
          </div>
        )}

        {showHistory && (
          <div className="absolute top-full left-2 z-20 mt-1 max-h-80 w-80 max-w-[calc(100vw-1rem)] overflow-y-auto rounded-lg border border-stone-200 bg-white p-1 shadow-lg dark:border-stone-700 dark:bg-stone-900">
            {conversations.length === 0 && <p className="p-3 text-sm text-stone-500">No saved conversations yet.</p>}
            {conversations.map((c) => (
              <div key={c.id} className={`group flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm hover:bg-stone-100 dark:hover:bg-stone-800 ${c.id === conversationId ? "bg-stone-100 dark:bg-stone-800" : ""}`}>
                {renaming?.id === c.id ? (
                  <input
                    autoFocus
                    value={renaming.title}
                    maxLength={120}
                    onChange={(e) => setRenaming({ id: c.id, title: e.target.value })}
                    onBlur={saveRename}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") saveRename();
                      if (e.key === "Escape") setRenaming(null);
                    }}
                    aria-label="Chat name"
                    className="min-w-0 flex-1 rounded border border-brand-400 bg-transparent px-1.5 py-0.5 outline-none"
                  />
                ) : (
                  <button className="min-w-0 flex-1 text-left" onClick={() => openConversation(c.id)}>
                    <span className="block truncate">
                      {c.mode === "persona" ? `🎭 ${c.persona}: ` : c.mode === "compare" ? "⚖️ " : ""}
                      {c.title}
                    </span>
                    <span className="block text-xs text-stone-400">{new Date(c.updated_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}</span>
                  </button>
                )}
                <button onClick={() => setRenaming({ id: c.id, title: c.title })} className="rounded p-1 text-stone-400 hover:text-stone-700 sm:opacity-0 sm:group-hover:opacity-100 dark:hover:text-stone-200" aria-label="Rename chat" title="Rename">
                  <Pencil size={14} />
                </button>
                <button onClick={() => deleteConversation(c)} className="rounded p-1 text-stone-400 hover:text-red-600 sm:opacity-0 sm:group-hover:opacity-100" aria-label="Delete chat" title="Delete">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6" onClick={() => setShowHistory(false)}>
        <div className="mx-auto flex max-w-3xl flex-col gap-5">
          {messages.length === 0 && mode === "ask" && historyReady && (
            // Welcome, centred like a new chat: a large greeting for this book, starter questions as chips.
            <div className="flex min-h-[40vh] flex-col items-center justify-center text-center sm:min-h-[55vh]">
              <h2 className="flex max-w-2xl items-start justify-center gap-2.5 font-serif text-2xl leading-snug font-normal text-stone-800 sm:gap-3 sm:text-3xl md:text-4xl dark:text-stone-100">
                <BookOpen className="mt-1 size-6 shrink-0 text-brand-500 sm:size-7 md:size-9" aria-hidden />
                <span>
                  {greeting[0]}
                  <em>{book.title}</em>
                  {greeting[1]}
                </span>
              </h2>
              {maxChapter !== null && (
                <p className="mt-3 text-sm text-stone-500">Spoiler guard is on: I'll only use chapters 1–{maxChapter}.</p>
              )}
              <div className="mt-8 flex w-full max-w-3xl flex-wrap justify-center gap-2">
                {starterQuestions(book.suggested_questions).map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    title={q}
                    className="max-w-[min(18rem,100%)] truncate rounded-full border border-stone-200 bg-white px-3.5 py-1.5 text-sm text-stone-600 transition hover:border-brand-400 hover:text-stone-900 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300 dark:hover:text-stone-100 sm:max-w-[min(22rem,100%)]"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.length === 0 && mode !== "ask" && (
            <div className="mt-8 text-center">
              <h2 className="text-xl font-semibold">
                {mode === "persona" ? (persona ? `Talk to ${persona}` : "Talk to a character") : mode === "compare" ? "Compare books" : `Ask anything about “${book.title}”`}
              </h2>
              <p className="mt-1 text-sm text-stone-500">
                {mode === "persona"
                  ? "They answer in their own voice, but only from what the book says."
                  : mode === "compare"
                    ? "Answers draw on passages from each selected book, with citations from each."
                    : "Answers come only from the book, with clickable sources."}
                {maxChapter !== null && ` Spoiler guard: chapters 1–${maxChapter} only.`}
              </p>
            </div>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              editing?.index === i ? (
                <form
                  key={i}
                  onSubmit={(e) => {
                    e.preventDefault();
                    send(editing.text, i);
                  }}
                  className="w-full max-w-[85%] self-end rounded-2xl border border-brand-400 bg-white p-2 dark:bg-stone-900"
                >
                  <textarea
                    autoFocus
                    value={editing.text}
                    onChange={(e) => setEditing({ index: i, text: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        send(editing.text, i);
                      }
                      if (e.key === "Escape") setEditing(null);
                    }}
                    rows={2}
                    aria-label="Edit your question"
                    className="w-full resize-y bg-transparent px-1 text-[15px] outline-none"
                  />
                  <div className="flex justify-end gap-2">
                    <button type="button" onClick={() => setEditing(null)} className="rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800">
                      Cancel
                    </button>
                    <button type="submit" disabled={!editing.text.trim() || busy} className="rounded-md bg-brand-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-40">
                      Send again
                    </button>
                  </div>
                </form>
              ) : (
                <div key={i} className="group flex max-w-[85%] flex-col items-end self-end">
                  <div className="rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-[15px] whitespace-pre-wrap text-white">{m.content}</div>
                  <div className="mt-1 flex gap-1 opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-70">
                    <button disabled={busy} onClick={() => setEditing({ index: i, text: m.content })} className="flex items-center gap-1 rounded-md px-2 py-0.5 text-xs text-stone-500 hover:bg-stone-100 disabled:opacity-40 dark:hover:bg-stone-800" title="Edit and send again">
                      <Pencil size={12} /> Edit
                    </button>
                    <button disabled={busy} onClick={() => send(m.content, i)} className="flex items-center gap-1 rounded-md px-2 py-0.5 text-xs text-stone-500 hover:bg-stone-100 disabled:opacity-40 dark:hover:bg-stone-800" title="Send this question again">
                      <RotateCcw size={12} /> Resend
                    </button>
                  </div>
                </div>
              )
            ) : (
              <div key={i} className="group max-w-full">
                {m.content && (
                  <AnswerMarkdown
                    // A short "the book doesn't say" answer cites nothing, even if the model added a [n].
                    // Citation markers stay hidden until the reader asks to see the sources.
                    text={
                      (m.content.length < 160 && NOT_FOUND.test(m.content)) || !citesShown.has(i)
                        ? stripCitations(m.content)
                        : m.content
                    }
                    sources={m.sources}
                    onCite={onCite}
                  />
                )}
                {m.pending && (!m.content || m.stage === "searching_more") && (
                  <div className={`flex items-center gap-2 text-sm text-stone-500 ${m.content ? "mt-2" : ""}`} aria-live="polite">
                    <span className="flex gap-1">
                      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
                      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
                      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
                    </span>
                    {m.stage === "searching_more"
                      ? "Not found yet. Looking further in the book with other wordings…"
                      : m.stage === "answering"
                        ? `Reading ${m.sources.length} passages…`
                        : "Searching the book…"}
                  </div>
                )}
                {m.error && (
                  <div className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300">
                    {m.error}
                  </div>
                )}
                {!m.pending && m.content && citesShown.has(i) && <SourceList sources={m.sources} cited={m.cited} answer={m.content} onCite={onCite} />}
                {!m.pending && (m.content || m.error) && (
                  <div className="mt-2 flex flex-wrap gap-1 opacity-70 transition group-hover:opacity-100">
                    {m.content && sourceCount(m) > 0 && (
                      <button
                        onClick={() => toggleCites(i)}
                        aria-expanded={citesShown.has(i)}
                        className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800"
                        title={citesShown.has(i) ? "Hide sources" : "Show where this answer comes from"}
                      >
                        <Quote size={14} /> {citesShown.has(i) ? "Hide sources" : `Sources (${sourceCount(m)})`}
                      </button>
                    )}
                    {messages[i - 1]?.role === "user" && (
                      <button disabled={busy} onClick={() => send(messages[i - 1].content, i - 1)} className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100 disabled:opacity-40 dark:hover:bg-stone-800" title="Answer this question again">
                        <RotateCcw size={14} /> Retry
                      </button>
                    )}
                    {m.content && (
                      <>
                    <button onClick={() => saveAnswer(i, m)} className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800" title="Save to notes">
                      <BookmarkPlus size={14} /> Save
                    </button>
                    <button onClick={() => navigator.clipboard.writeText(plainText(m.content)).then(() => notify("Answer copied."))} className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800" title="Copy">
                      <Copy size={14} /> Copy
                    </button>
                    <ReplyAudio
                      playback={playback?.message === i ? playback : null}
                      onListen={() => listen(i, m.content)}
                      onStop={stopListening}
                    />
                      </>
                    )}
                  </div>
                )}
              </div>
            ),
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="border-t border-stone-200 px-4 py-3 dark:border-stone-800"
      >
        <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-stone-300 bg-white px-3 py-2 focus-within:border-brand-500 dark:border-stone-700 dark:bg-stone-900">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            rows={1}
            placeholder={placeholder}
            aria-label="Message"
            className="max-h-40 min-h-[28px] flex-1 resize-none bg-transparent py-1 text-[15px] outline-none placeholder:text-stone-400"
          />
          {SpeechRecognitionImpl && (
            <button
              type="button"
              onClick={toggleMic}
              className={`rounded-xl p-2 transition ${listening ? "animate-pulse bg-red-100 text-red-600 dark:bg-red-950" : "text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800"}`}
              title={listening ? "Stop dictation" : "Dictate your question"}
              aria-pressed={listening}
            >
              {listening ? <MicOff size={16} /> : <Mic size={16} />}
            </button>
          )}
          {busy ? (
            <button type="button" onClick={stop} className="rounded-xl bg-stone-200 p-2 text-stone-700 dark:bg-stone-700 dark:text-stone-200" title="Stop">
              <Square size={16} />
            </button>
          ) : (
            <button type="submit" disabled={!input.trim()} className="rounded-xl bg-brand-600 p-2 text-white transition hover:bg-brand-700 disabled:opacity-40" title="Send">
              <SendHorizonal size={16} />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
