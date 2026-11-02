import { BookmarkPlus, Copy, History, Mic, MicOff, Plus, SendHorizonal, Square, Trash2, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamChat } from "../api";
import type { ChatMessage, ConversationSummary, Source, Style } from "../types";
import { useWorkspace } from "../workspace";
import AnswerMarkdown from "./AnswerMarkdown";
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
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const SpeechRecognitionImpl: any =
  typeof window !== "undefined" ? (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition : undefined;
const canSpeak = typeof window !== "undefined" && "speechSynthesis" in window;

function plainText(markdown: string): string {
  return markdown.replace(/\[\d+(?:\s*[,–-]\s*\d+)*\]/g, "").replace(/[*_#>`]/g, "").replace(/\s+/g, " ").trim();
}

const NOT_FOUND = /couldn.?t find|could not find|doesn.?t (?:say|mention)|does not (?:say|mention)|not (?:mentioned|covered|in the (?:book|passages))/i;

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
  const { book, books, maxChapter, saveNote, notify } = useWorkspace();
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
  const [speaking, setSpeaking] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const recRef = useRef<{ stop: () => void } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const others = books.filter((b) => b.id !== book.id && b.status === "ready");

  const loadConversations = useCallback(() => {
    api.conversations(book.id).then(setConversations).catch(() => {});
  }, [book.id]);

  useEffect(() => {
    abortRef.current?.abort();
    setConversationId(null);
    setMessages([]);
    setMode("ask");
    setCompareIds([]);
    setPersona("");
    loadConversations();
  }, [book.id, loadConversations]);

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
    if (canSpeak) window.speechSynthesis.cancel();
    recRef.current?.stop();
  }, []);

  const openConversation = async (id: number) => {
    setShowHistory(false);
    abortRef.current?.abort();
    const c = await api.conversation(id);
    setConversationId(id);
    setMessages(c.messages);
    setMode(c.mode === "persona" ? "persona" : c.mode === "compare" ? "compare" : "ask");
    setPersona(c.persona ?? "");
    setCompareIds(c.book_ids.filter((b) => b !== book.id));
  };

  const newConversation = () => {
    abortRef.current?.abort();
    setConversationId(null);
    setMessages([]);
  };

  const changeMode = (m: Mode) => {
    setMode(m);
    newConversation(); // modes are per conversation
  };

  const updateLast = (fn: (m: ChatMessage) => ChatMessage) => setMessages((ms) => [...ms.slice(0, -1), fn(ms[ms.length - 1])]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    if (mode === "persona" && !persona.trim()) {
      notify("Choose a character to talk to first.");
      return;
    }
    if (mode === "compare" && compareIds.length === 0) {
      notify("Pick at least one other book to compare with.");
      return;
    }
    setInput("");
    setBusy(true);
    setMessages((ms) => [
      ...ms,
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
      },
      {
        onConversation: (id) => setConversationId(id),
        onStage: (stage) => updateLast((m) => ({ ...m, stage })),
        onSources: (sources) => updateLast((m) => ({ ...m, sources })),
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
    updateLast((m) => ({ ...m, pending: false, error: m.content ? undefined : "Stopped." }));
    setBusy(false);
  };

  const deleteConversation = async (id: number) => {
    await api.deleteConversation(id);
    if (id === conversationId) newConversation();
    loadConversations();
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

  const speak = (i: number, text: string) => {
    window.speechSynthesis.cancel();
    if (speaking === i) {
      setSpeaking(null);
      return;
    }
    const u = new SpeechSynthesisUtterance(plainText(text));
    u.onend = () => setSpeaking((s) => (s === i ? null : s));
    setSpeaking(i);
    window.speechSynthesis.speak(u);
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
            ...(book.is_fiction !== false ? [{ value: "persona" as Mode, label: "Talk to a character" }] : []),
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
              <div key={c.id} className={`group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-stone-100 dark:hover:bg-stone-800 ${c.id === conversationId ? "bg-stone-100 dark:bg-stone-800" : ""}`}>
                <button className="min-w-0 flex-1 truncate text-left" onClick={() => openConversation(c.id)}>
                  {c.mode === "persona" ? `🎭 ${c.persona}: ` : c.mode === "compare" ? "⚖️ " : ""}
                  {c.title}
                </button>
                <button onClick={() => deleteConversation(c.id)} className="text-stone-400 opacity-0 group-hover:opacity-100 hover:text-red-600" aria-label="Delete conversation">
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
          {messages.length === 0 && (
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
              {mode === "ask" && book.suggested_questions.length > 0 && (
                <div className="mx-auto mt-6 grid max-w-2xl gap-2 sm:grid-cols-2">
                  {book.suggested_questions.map((q) => (
                    <button
                      key={q}
                      onClick={() => send(q)}
                      className="rounded-xl border border-stone-200 bg-white px-3 py-2.5 text-left text-sm text-stone-700 transition hover:border-brand-400 hover:shadow-sm dark:border-stone-800 dark:bg-stone-900 dark:text-stone-300"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="max-w-[85%] self-end rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-[15px] text-white">
                {m.content}
              </div>
            ) : (
              <div key={i} className="group max-w-full">
                {m.content && (
                  <AnswerMarkdown
                    // A short "the book doesn't say" answer cites nothing, even if the model added a [n].
                    text={m.content.length < 160 && NOT_FOUND.test(m.content) ? m.content.replace(/\s*\[[^\]]*\d[^\]]*\]/g, "") : m.content}
                    sources={m.sources}
                    onCite={onCite}
                  />
                )}
                {m.pending && !m.content && (
                  <div className="flex items-center gap-2 text-sm text-stone-500" aria-live="polite">
                    <span className="flex gap-1">
                      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
                      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
                      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
                    </span>
                    {m.stage === "answering" ? `Reading ${m.sources.length} passages…` : "Searching the book…"}
                  </div>
                )}
                {m.error && (
                  <div className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300">
                    {m.error}
                  </div>
                )}
                {!m.pending && m.content && <SourceList sources={m.sources} cited={m.cited} answer={m.content} onCite={onCite} />}
                {!m.pending && m.content && (
                  <div className="mt-2 flex gap-1 opacity-70 transition group-hover:opacity-100">
                    <button onClick={() => saveAnswer(i, m)} className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800" title="Save to notes">
                      <BookmarkPlus size={14} /> Save
                    </button>
                    <button onClick={() => navigator.clipboard.writeText(plainText(m.content)).then(() => notify("Answer copied."))} className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800" title="Copy">
                      <Copy size={14} /> Copy
                    </button>
                    {canSpeak && (
                      <button onClick={() => speak(i, m.content)} className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800" title={speaking === i ? "Stop reading" : "Read aloud"}>
                        {speaking === i ? <VolumeX size={14} /> : <Volume2 size={14} />} {speaking === i ? "Stop" : "Listen"}
                      </button>
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
