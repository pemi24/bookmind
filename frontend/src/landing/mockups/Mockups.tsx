/** Product mockups drawn in HTML/CSS (no screenshots): they follow the theme and stay crisp. */
import { BookOpen, Check, ChevronLeft, ChevronRight, Clock, Headphones, Pause, Quote, SkipBack, SkipForward } from "lucide-react";
import type { ReactNode } from "react";
import type { DemoChat, DemoResult, MockupName } from "../content";
import { useInView } from "../ui/motion";
import { Caret, useTyping, WithCitations } from "../ui/typing";

/** A rounded "app window" with three dots and a title. */
export function Window({ title, children, className = "" }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`overflow-hidden rounded-[var(--radius-card)] border border-line bg-paper-raised shadow-float ${className}`}>
      <div className="flex items-center gap-2 border-b border-line bg-paper-sunk/60 px-4 py-2.5">
        <span className="flex gap-1.5" aria-hidden="true">
          <i className="h-2.5 w-2.5 rounded-full bg-line" />
          <i className="h-2.5 w-2.5 rounded-full bg-line" />
          <i className="h-2.5 w-2.5 rounded-full bg-line" />
        </span>
        {title && <span className="ml-2 truncate text-xs font-medium text-ink-muted">{title}</span>}
      </div>
      {children}
    </div>
  );
}

function BookHeader({ book }: { book: { title: string; author: string } }) {
  return (
    <div className="flex items-center gap-3 border-b border-line px-4 py-3">
      <span className="flex h-9 w-7 shrink-0 items-center justify-center rounded-sm bg-accent text-on-accent shadow-card">
        <BookOpen size={14} aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="truncate font-display text-sm font-semibold text-ink">{book.title}</p>
        <p className="truncate text-xs text-ink-muted">{book.author}</p>
      </div>
    </div>
  );
}

function UserBubble({ children }: { children: ReactNode }) {
  return <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm leading-relaxed text-on-accent">{children}</div>;
}

/* ---------- hero chat ---------- */

/** The hero's conversation: the answer types itself out, then its sources appear. */
export function ChatMockup({ chat }: { chat: DemoChat }) {
  const [ref, seen] = useInView<HTMLDivElement>("0px");
  const { typed, done } = useTyping(chat.answer, seen, { delay: 700 });
  return (
    <div ref={ref}>
      <Window title="BookMind · Chat">
        <BookHeader book={chat.book} />
        <div className="space-y-4 px-4 py-5 sm:px-5" aria-label="Example conversation">
          <UserBubble>{chat.question}</UserBubble>
          <div className="max-w-[95%] text-[0.95rem] leading-relaxed text-ink">
            {/* screen readers get the whole answer at once, not each word */}
            <p className="sr-only">{chat.answer.replace(/\s*\[\d+\]/g, "")}</p>
            <p aria-hidden="true" className="min-h-[7.5em] sm:min-h-[6em]">
              <WithCitations text={typed} />
              <Caret show={!done} />
            </p>
          </div>
          <ul className={`space-y-2 transition-opacity duration-500 ${done ? "opacity-100" : "opacity-0"}`} aria-label="Sources">
            {chat.citations.map((c) => (
              <li key={c.marker} className="flex gap-2.5 rounded-xl border border-line bg-paper px-3 py-2">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[0.7rem] font-semibold text-accent-ink">
                  {c.marker}
                </span>
                <span className="min-w-0 text-xs leading-snug">
                  <span className="block font-medium text-ink">{c.where}</span>
                  <span className="block font-display text-[0.8rem] text-ink-muted italic">{c.quote}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="border-t border-line px-4 py-3">
          <div className="flex items-center justify-between rounded-full border border-line bg-paper px-4 py-2 text-sm text-ink-muted">
            Ask about this book…
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-on-accent" aria-hidden="true">
              <ChevronRight size={15} />
            </span>
          </div>
        </div>
      </Window>
    </div>
  );
}

/* ---------- showcase result cards ---------- */

export function ResultCard({ result }: { result: DemoResult }) {
  const head = <p className="mb-3 text-xs font-semibold tracking-wide text-accent-ink uppercase">{result.title}</p>;
  switch (result.kind) {
    case "quiz":
      return (
        <div className="rounded-2xl border border-line bg-paper p-4">
          {head}
          <p className="font-display text-lg leading-snug text-ink">{result.question}</p>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {result.options.map((o, i) => (
              <li
                key={o}
                className={`flex items-center justify-between rounded-xl border px-3 py-2 text-sm ${
                  i === result.correct ? "border-accent bg-accent-soft font-medium text-accent-ink" : "border-line text-ink"
                }`}
              >
                {o}
                {i === result.correct && <Check size={16} aria-label="correct answer" />}
              </li>
            ))}
          </ul>
        </div>
      );
    case "quotes":
      return (
        <div className="rounded-2xl border border-line bg-paper p-4">
          {head}
          <ul className="space-y-3">
            {result.quotes.map((q) => (
              <li key={q.text} className="flex gap-3">
                <Quote size={16} className="mt-1 shrink-0 text-accent-ink" aria-hidden="true" />
                <span>
                  <span className="block font-display text-[1.05rem] leading-snug text-ink">“{q.text}”</span>
                  <span className="text-xs text-ink-muted">{q.where}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      );
    case "summary":
      return (
        <div className="rounded-2xl border border-line bg-paper p-4">
          {head}
          <ul className="space-y-2">
            {result.points.map((p) => (
              <li key={p} className="flex gap-2.5 text-sm leading-relaxed text-ink">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
                {p}
              </li>
            ))}
          </ul>
        </div>
      );
    case "characters":
      return (
        <div className="rounded-2xl border border-line bg-paper p-4">
          {head}
          <CharacterGraph people={result.people} links={result.links} />
        </div>
      );
  }
}

/** A small, fixed-layout relationship graph (SVG lines, HTML labels). */
function CharacterGraph({ people, links }: { people: { name: string; note: string }[]; links: [number, number, string][] }) {
  // positions in % of the box, laid out for up to five people
  const pos = [
    [26, 30],
    [74, 30],
    [20, 78],
    [78, 76],
    [50, 6],
  ];
  return (
    <div
      className="relative h-56 w-full"
      role="img"
      aria-label={`Character map: ${links.map(([a, b, l]) => `${people[a].name} and ${people[b].name}, ${l}`).join("; ")}`}
    >
      <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox="0 0 100 100" aria-hidden="true">
        {links.map(([a, b], i) => (
          <line
            key={i}
            x1={pos[a][0]}
            y1={pos[a][1] + 6}
            x2={pos[b][0]}
            y2={pos[b][1] + 6}
            className="stroke-line"
            strokeWidth="0.8"
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
      {links.map(([a, b, label], i) => (
        <span
          key={`l${i}`}
          aria-hidden="true"
          className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-paper px-1.5 text-[0.65rem] whitespace-nowrap text-ink-muted"
          style={{ left: `${(pos[a][0] + pos[b][0]) / 2}%`, top: `${(pos[a][1] + pos[b][1]) / 2 + 6}%` }}
        >
          {label}
        </span>
      ))}
      {people.map((p, i) => (
        <span
          key={p.name}
          aria-hidden="true"
          className={`absolute -translate-x-1/2 rounded-full border px-2 py-0.5 text-center text-[0.7rem] font-medium whitespace-nowrap shadow-card sm:px-3 sm:py-1 sm:text-xs ${
            i === 0 ? "border-accent bg-accent text-on-accent" : "border-line bg-paper-raised text-ink"
          }`}
          style={{ left: `${pos[i][0]}%`, top: `${pos[i][1]}%` }}
        >
          {p.name}
        </span>
      ))}
    </div>
  );
}

/* ---------- feature highlight mockups ---------- */

function SummaryMock() {
  return (
    <Window title="Summaries · Pride and Prejudice">
      <div className="space-y-4 p-5">
        <div className="flex gap-1.5" role="presentation">
          {["Short", "Medium", "Detailed"].map((l, i) => (
            <span
              key={l}
              className={`rounded-full px-3 py-1 text-xs font-medium ${i === 1 ? "bg-accent text-on-accent" : "border border-line text-ink-muted"}`}
            >
              {l}
            </span>
          ))}
        </div>
        <div>
          <p className="font-display text-lg font-semibold text-ink">Chapter 3</p>
          <p className="mt-2 text-sm leading-relaxed text-ink">
            At the Meryton assembly, Mr. Bingley dances twice with Jane and charms everyone. Mr. Darcy refuses to dance with Elizabeth, calling her
            only “tolerable”, and she turns the slight into a story she tells with great spirit.
          </p>
        </div>
        <p className="flex items-center gap-1.5 text-xs text-ink-muted">
          <Check size={14} className="text-accent-ink" aria-hidden="true" /> Saved · from 6 passages
        </p>
      </div>
    </Window>
  );
}

function FlashcardsMock() {
  return (
    <div className="relative mx-auto max-w-md pt-6 pb-10">
      <div
        className="absolute inset-x-8 top-0 h-full rotate-[-4deg] rounded-[var(--radius-card)] border border-line bg-paper-sunk"
        aria-hidden="true"
      />
      <div
        className="absolute inset-x-4 top-3 h-full rotate-[3deg] rounded-[var(--radius-card)] border border-line bg-paper-raised"
        aria-hidden="true"
      />
      <Window title="Flashcards · 12 due today" className="relative">
        <div className="p-6 text-center">
          <p className="text-xs font-semibold tracking-wide text-ink-muted uppercase">Question</p>
          <p className="mt-2 font-display text-xl leading-snug text-ink">
            Who writes the letters that open <em>Frankenstein</em>?
          </p>
          <div className="my-5 h-px bg-line" />
          <p className="text-xs font-semibold tracking-wide text-ink-muted uppercase">Answer</p>
          <p className="mt-2 text-base text-ink">Robert Walton, to his sister Margaret</p>
          <div className="mt-6 grid grid-cols-3 gap-2 text-xs font-medium">
            <span className="rounded-full border border-line py-2 text-ink-muted">Again</span>
            <span className="rounded-full border border-line py-2 text-ink">Good</span>
            <span className="rounded-full bg-accent py-2 text-on-accent">Easy · 6 days</span>
          </div>
        </div>
      </Window>
    </div>
  );
}

function ExplorerMock() {
  return (
    <Window title="Explorer · Pride and Prejudice">
      <div className="p-5">
        <CharacterGraph
          people={[
            { name: "Elizabeth", note: "" },
            { name: "Darcy", note: "" },
            { name: "Jane", note: "" },
            { name: "Bingley", note: "" },
            { name: "Lady Catherine", note: "" },
          ]}
          links={[
            [0, 1, "rivals"],
            [2, 3, "courtship"],
            [0, 2, "sisters"],
            [1, 3, "friends"],
            [4, 1, "aunt"],
          ]}
        />
        <div className="mt-3 rounded-xl border border-line bg-paper px-4 py-3 text-sm">
          <p className="font-medium text-ink">Elizabeth Bennet</p>
          <p className="text-ink-muted">Character · the second of the five Bennet sisters</p>
        </div>
      </div>
    </Window>
  );
}

function TimelineMock() {
  const events = [
    { ch: "Ch. 1", t: "Ishmael goes to sea" },
    { ch: "Ch. 16", t: "Signs on to the Pequod" },
    { ch: "Ch. 28", t: "Ahab appears on deck" },
    { ch: "Ch. 36", t: "The doubloon is nailed to the mast" },
  ];
  return (
    <Window title="Timeline · Moby-Dick">
      <ol className="relative space-y-4 p-6 pl-10">
        <span className="absolute top-8 bottom-8 left-[1.6rem] w-px bg-line" aria-hidden="true" />
        {events.map((e, i) => (
          <li key={e.t} className="relative">
            <span
              className={`absolute top-1.5 -left-[1.15rem] h-3 w-3 rounded-full border-2 ${i === 2 ? "border-accent bg-accent" : "border-ink-muted bg-paper-raised"}`}
              aria-hidden="true"
            />
            <p className="text-xs font-semibold text-accent-ink">{e.ch}</p>
            <p className="text-sm text-ink">{e.t}</p>
          </li>
        ))}
      </ol>
    </Window>
  );
}

function SpoilerMock() {
  return (
    <Window title="Spoiler guard">
      <div className="space-y-4 p-5">
        <div className="rounded-xl border border-line bg-paper p-4">
          <p className="text-sm font-medium text-ink">I've read up to</p>
          <div className="mt-3 flex items-center gap-3">
            <div className="relative h-2 flex-1 rounded-full bg-paper-sunk" aria-hidden="true">
              <div className="absolute inset-y-0 left-0 w-[38%] rounded-full bg-accent" />
              <div className="absolute top-1/2 left-[38%] h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-paper-raised bg-accent shadow-card" />
            </div>
            <span className="rounded-full bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent-ink">Ch. 23</span>
          </div>
        </div>
        <UserBubble>Does Elizabeth end up with Darcy?</UserBubble>
        <p className="text-sm leading-relaxed text-ink">
          That happens after chapter 23, so I'll keep it to myself. So far, she has turned down Mr. Collins and still thinks very little of Darcy.
        </p>
      </div>
    </Window>
  );
}

function NotesMock() {
  return (
    <Window title="Reader · Frankenstein, Chapter 4">
      <div className="space-y-3 p-6 font-display text-[1.05rem] leading-relaxed text-ink">
        <p>
          Learn from me, if not by my precepts, at least by my example, how dangerous is the acquirement of knowledge{" "}
          <mark className="rounded-sm bg-highlight px-0.5 text-ink">
            and how much happier that man is who believes his native town to be the world, than he who aspires to become greater than his nature will
            allow.
          </mark>
        </p>
        <div className="ml-auto max-w-xs rounded-xl border border-line bg-paper p-3 font-body text-sm text-ink shadow-card">
          <p className="text-xs font-semibold text-accent-ink">Your note</p>
          Victor warns Walton about the very ambition that drives them both.
          <p className="mt-2 flex gap-1.5">
            {["#theme", "#essay"].map((t) => (
              <span key={t} className="rounded-full bg-paper-sunk px-2 py-0.5 text-xs text-ink-muted">
                {t}
              </span>
            ))}
          </p>
        </div>
      </div>
    </Window>
  );
}

function ListenMock() {
  return (
    <Window title="Reader · Alice's Adventures in Wonderland">
      <div className="p-6 font-display text-[1.05rem] leading-relaxed text-ink">
        <p>
          Alice was beginning to get very tired of sitting by her sister on the bank, and of having nothing to do: once or twice she had peeped into
          the book her sister was reading,{" "}
          <span className="rounded-sm bg-accent-soft px-0.5 text-ink ring-1 ring-accent/30">but it had no pictures or conversations in it,</span> “and
          what is the use of a book,” thought Alice “without pictures or conversations?”
        </p>
      </div>
      <div className="border-t border-line bg-paper-sunk/60 px-4 py-3 font-body">
        <div className="mb-2 h-1 rounded-full bg-line" aria-hidden="true">
          <div className="h-full w-1/3 rounded-full bg-accent" />
        </div>
        <div className="flex items-center gap-1 text-ink-muted">
          <SkipBack size={16} aria-hidden="true" />
          <ChevronLeft size={18} aria-hidden="true" />
          <span className="mx-1 flex h-9 w-9 items-center justify-center rounded-full bg-accent text-on-accent" aria-hidden="true">
            <Pause size={16} />
          </span>
          <ChevronRight size={18} aria-hidden="true" />
          <SkipForward size={16} aria-hidden="true" />
          <span className="ml-3 min-w-0 flex-1 truncate text-xs">
            <span className="font-medium text-ink">Ch. 1</span> · Sentence 2 of 82
          </span>
          <Clock size={15} aria-hidden="true" />
        </div>
        <div className="mt-3 flex items-center gap-2 rounded-xl border border-line bg-paper-raised px-3 py-2 text-xs text-ink">
          <Headphones size={14} className="text-accent-ink" aria-hidden="true" />
          Voice: <span className="font-medium">Alba</span> · British (Scottish), female
          <span className="ml-auto rounded-full bg-paper-sunk px-2 py-0.5 text-ink-muted">1.25×</span>
        </div>
      </div>
    </Window>
  );
}

const MOCKUPS: Record<MockupName, () => JSX.Element> = {
  summary: SummaryMock,
  flashcards: FlashcardsMock,
  explorer: ExplorerMock,
  timeline: TimelineMock,
  spoiler: SpoilerMock,
  notes: NotesMock,
  listen: ListenMock,
};

export function FeatureMockup({ name }: { name: MockupName }) {
  const M = MOCKUPS[name];
  return <M />;
}
