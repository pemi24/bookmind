import { Check, Download, GraduationCap, Layers, RotateCcw, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { Flashcard, QuestionType, Quiz, QuizResult, QuizSummary } from "../../types";
import { useWorkspace } from "../../workspace";
import { Button, buttonClasses, ChapterSelect, EmptyState, ErrorBox, LocationChip, PanelShell, Segmented } from "../ui";

const TYPE_LABELS: Record<QuestionType, string> = {
  multiple_choice: "Multiple choice",
  true_false: "True / false",
  short_answer: "Short answer",
};

/* ------------------------------------------------------------------ quizzes */

function QuizTaker({ quiz, onExit }: { quiz: Quiz; onExit: () => void }) {
  const { chapters, openPassage, notify } = useWorkspace();
  const [answers, setAnswers] = useState<(string | null)[]>(() => quiz.questions.map(() => null));
  const [result, setResult] = useState<QuizResult | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      setResult(await api.submitQuiz(quiz.id, answers));
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const retake = () => {
    setAnswers(quiz.questions.map(() => null));
    setResult(null);
  };

  const answered = answers.filter((a) => a && a.trim()).length;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button variant="ghost" onClick={onExit}>← All quizzes</Button>
        <h3 className="font-semibold">{quiz.title}</h3>
      </div>

      {result && (
        <div className={`mb-5 rounded-xl p-4 text-center ${result.score / result.total >= 0.7 ? "bg-emerald-50 dark:bg-emerald-950/40" : "bg-amber-50 dark:bg-amber-950/40"}`}>
          <p className="text-3xl font-bold">
            {result.score} / {result.total}
          </p>
          <p className="text-sm text-stone-600 dark:text-stone-300">
            {result.score === result.total ? "Perfect score!" : result.score / result.total >= 0.7 ? "Nicely done." : "Review the explanations below and try again."}
          </p>
          <Button className="mt-3" onClick={retake}>
            <RotateCcw size={14} /> Retake
          </Button>
        </div>
      )}

      <ol className="space-y-4">
        {quiz.questions.map((q, i) => {
          const r = result?.results[i];
          return (
            <li key={i} className={`rounded-xl border bg-white p-4 dark:bg-stone-900 ${r ? (r.correct ? "border-emerald-300 dark:border-emerald-800" : "border-red-300 dark:border-red-900") : "border-stone-200 dark:border-stone-800"}`}>
              <p className="text-xs text-stone-400">
                {i + 1}. {TYPE_LABELS[q.type]}
              </p>
              <p className="mt-1 font-medium">{q.question}</p>
              {q.type === "short_answer" ? (
                <textarea
                  value={answers[i] ?? ""}
                  disabled={!!result}
                  onChange={(e) => setAnswers((a) => a.map((x, j) => (j === i ? e.target.value : x)))}
                  rows={2}
                  className="mt-2 w-full rounded-lg border border-stone-300 bg-transparent p-2 text-sm dark:border-stone-700"
                  placeholder="Your answer…"
                />
              ) : (
                <div className="mt-2 grid gap-1.5">
                  {q.options.map((opt) => {
                    const chosen = answers[i] === opt;
                    const isAnswer = r && r.answer === opt;
                    return (
                      <label
                        key={opt}
                        className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
                          isAnswer
                            ? "border-emerald-400 bg-emerald-50 dark:bg-emerald-950/40"
                            : r && chosen
                              ? "border-red-400 bg-red-50 dark:bg-red-950/40"
                              : chosen
                                ? "border-brand-500 bg-brand-50 dark:bg-brand-900/30"
                                : "border-stone-200 hover:bg-stone-50 dark:border-stone-700 dark:hover:bg-stone-800"
                        }`}
                      >
                        <input
                          type="radio"
                          name={`q${i}`}
                          checked={chosen}
                          disabled={!!result}
                          onChange={() => setAnswers((a) => a.map((x, j) => (j === i ? opt : x)))}
                          className="accent-brand-600"
                        />
                        {opt}
                      </label>
                    );
                  })}
                </div>
              )}
              {r && (
                <div className="mt-3 space-y-1 border-t border-stone-100 pt-2 text-sm dark:border-stone-800">
                  <p className="flex items-center gap-1 font-medium">
                    {r.correct ? <Check size={16} className="text-emerald-600" /> : <X size={16} className="text-red-600" />}
                    {r.correct ? "Correct" : q.type === "short_answer" ? "Not quite" : `Answer: ${r.answer}`}
                  </p>
                  {q.type === "short_answer" && <p className="text-stone-600 dark:text-stone-300">Model answer: {r.answer}</p>}
                  {r.feedback && <p className="text-stone-600 dark:text-stone-300">{r.feedback}</p>}
                  <p className="text-stone-600 dark:text-stone-300">{r.explanation}</p>
                  {r.source && (
                    <LocationChip
                      chapter={chapters.find((c) => c.id === r.source!.chapter_id)?.title ?? `Chapter ${r.source.chapter_position}`}
                      page={r.source.page}
                      onClick={() => openPassage(r.source!)}
                    />
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {!result && (
        <div className="mt-5 flex items-center gap-3">
          <Button variant="primary" onClick={submit} loading={busy} disabled={answered === 0}>
            Submit answers
          </Button>
          <span className="text-sm text-stone-500">
            {answered} / {quiz.questions.length} answered
          </span>
        </div>
      )}
    </div>
  );
}

function Quizzes() {
  const { book, chapters, maxChapter, notify } = useWorkspace();
  const [list, setList] = useState<QuizSummary[]>([]);
  const [active, setActive] = useState<Quiz | null>(null);
  const [chapterId, setChapterId] = useState<number | null>(null);
  const [num, setNum] = useState(8);
  const [types, setTypes] = useState<QuestionType[]>(["multiple_choice", "true_false", "short_answer"]);
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => api.quizzes(book.id, maxChapter).then(setList).catch(() => {}), [book.id, maxChapter]);
  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const q = await api.createQuiz(book.id, { chapter_id: chapterId, max_chapter: maxChapter, num_questions: num, types, difficulty });
      setActive(q);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (active) return <QuizTaker quiz={active} onExit={() => { setActive(null); refresh(); }} />;

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
        <h3 className="font-medium">New quiz</h3>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
          <ChapterSelect chapters={chapters} value={chapterId} onChange={setChapterId} maxChapter={maxChapter} />
          <label className="flex items-center gap-1.5">
            Questions
            <input type="number" min={3} max={20} value={num} onChange={(e) => setNum(Math.min(20, Math.max(3, Number(e.target.value))))} className="w-16 rounded-lg border border-stone-300 bg-transparent px-2 py-1 dark:border-stone-700" />
          </label>
          <Segmented value={difficulty} onChange={setDifficulty} label="Difficulty" options={[{ value: "easy", label: "Easy" }, { value: "medium", label: "Medium" }, { value: "hard", label: "Hard" }]} />
        </div>
        <div className="mt-3 flex flex-wrap gap-3 text-sm">
          {(Object.keys(TYPE_LABELS) as QuestionType[]).map((t) => (
            <label key={t} className="flex items-center gap-1.5">
              <input
                type="checkbox"
                className="accent-brand-600"
                checked={types.includes(t)}
                onChange={(e) => setTypes((ts) => (e.target.checked ? [...ts, t] : ts.length > 1 ? ts.filter((x) => x !== t) : ts))}
              />
              {TYPE_LABELS[t]}
            </label>
          ))}
        </div>
        <Button variant="primary" className="mt-4" onClick={create} loading={busy}>
          {busy ? "Writing questions…" : "Generate quiz"}
        </Button>
        {error && <div className="mt-3"><ErrorBox>{error}</ErrorBox></div>}
      </section>

      {list.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-medium text-stone-500">Your quizzes</h3>
          <ul className="divide-y divide-stone-100 rounded-xl border border-stone-200 bg-white dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900">
            {list.map((q) => (
              <li key={q.id} className="flex items-center gap-3 px-4 py-3">
                <button className="min-w-0 flex-1 text-left" onClick={() => api.quiz(q.id, maxChapter).then(setActive).catch((e) => notify(e.message))}>
                  <p className="truncate text-sm font-medium">{q.title}</p>
                  <p className="text-xs text-stone-500">
                    {q.num_questions} questions · {q.attempts ? `best ${Math.round((q.best_score ?? 0) * 100)}% · ${q.attempts} attempt${q.attempts > 1 ? "s" : ""}` : "not taken yet"}
                  </p>
                </button>
                <button
                  onClick={async () => {
                    await api.deleteQuiz(q.id);
                    refresh();
                  }}
                  className="rounded p-1 text-stone-400 hover:text-red-600"
                  title="Delete quiz"
                >
                  <Trash2 size={15} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ flashcards */

function Flashcards() {
  const { book, chapters, maxChapter, openPassage, notify } = useWorkspace();
  const [deck, setDeck] = useState<{ total: number; due: number; cards: Flashcard[] } | null>(null);
  const [queue, setQueue] = useState<Flashcard[]>([]);
  const [flipped, setFlipped] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [chapterId, setChapterId] = useState<number | null>(null);
  const [count, setCount] = useState(10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Spoiler guard: hide cards from chapters beyond the reader's limit.
  const allowed = useCallback(
    (c: Flashcard) => {
      if (maxChapter === null || c.chapter_id === null) return true;
      const pos = chapters.find((ch) => ch.id === c.chapter_id)?.position;
      return pos === undefined || pos <= maxChapter;
    },
    [maxChapter, chapters],
  );
  const refresh = useCallback(
    () =>
      api
        .cards(book.id)
        .then((d) => {
          const cards = d.cards.filter(allowed);
          setDeck({ total: cards.length, due: cards.filter((c) => c.due_at && new Date(c.due_at) <= new Date()).length, cards });
        })
        .catch((e) => setError(e.message)),
    [book.id, allowed],
  );
  useEffect(() => {
    refresh();
  }, [refresh]);

  const startReview = async () => {
    const due = await api.cards(book.id, true);
    setQueue(due.cards.filter(allowed));
    setFlipped(false);
    setReviewing(true);
  };

  const grade = async (g: "again" | "hard" | "good" | "easy") => {
    const card = queue[0];
    try {
      await api.reviewCard(card.id, g);
    } catch (e) {
      notify((e as Error).message);
      return;
    }
    // "Again" goes back to the end of this session's queue.
    setQueue((q) => (g === "again" ? [...q.slice(1), card] : q.slice(1)));
    setFlipped(false);
  };

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.createCards(book.id, { chapter_id: chapterId, max_chapter: maxChapter, count });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (reviewing) {
    const card = queue[0];
    return (
      <div>
        <div className="mb-4 flex items-center gap-2">
          <Button variant="ghost" onClick={() => { setReviewing(false); refresh(); }}>← Done</Button>
          <span className="text-sm text-stone-500">{queue.length} left in this session</span>
        </div>
        {!card ? (
          <EmptyState icon={<Check size={22} />} title="All caught up!">
            No more cards are due right now. Come back later; spaced repetition schedules each card for when you're about to forget it.
          </EmptyState>
        ) : (
          <div className="mx-auto max-w-xl">
            <button
              onClick={() => setFlipped((f) => !f)}
              className="flex min-h-56 w-full flex-col items-center justify-center rounded-2xl border border-stone-200 bg-white p-6 text-center shadow-sm transition hover:shadow-md dark:border-stone-800 dark:bg-stone-900"
              aria-label={flipped ? "Show question" : "Show answer"}
            >
              <p className="text-xs tracking-wide text-stone-400 uppercase">{flipped ? "Answer" : "Question"}</p>
              <p className="mt-3 text-lg font-medium">{flipped ? card.back : card.front}</p>
              {!flipped && <p className="mt-6 text-xs text-stone-400">Click or press Space to reveal</p>}
            </button>
            {flipped && (
              <>
                <div className="mt-4 grid grid-cols-4 gap-2">
                  {([["again", "Again", "bg-red-600"], ["hard", "Hard", "bg-amber-600"], ["good", "Good", "bg-emerald-600"], ["easy", "Easy", "bg-sky-600"]] as const).map(([g, label, color]) => (
                    <button key={g} onClick={() => grade(g)} className={`rounded-lg py-2 text-sm font-medium text-white ${color} hover:opacity-90`}>
                      {label}
                    </button>
                  ))}
                </div>
                {card.source && (
                  <div className="mt-3 text-center">
                    <LocationChip
                      chapter={chapters.find((c) => c.id === card.source!.chapter_id)?.title ?? `Chapter ${card.source.chapter_position}`}
                      page={card.source.page}
                      onClick={() => openPassage(card.source!)}
                    />
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="flex flex-wrap items-center gap-4 rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
        <div className="flex-1">
          <p className="text-2xl font-bold">{deck?.due ?? 0} <span className="text-sm font-normal text-stone-500">due now</span></p>
          <p className="text-xs text-stone-500">{deck?.total ?? 0} cards in this book's deck</p>
        </div>
        <a
          href={api.exportCardsUrl(book.id, maxChapter)}
          download
          aria-disabled={!deck?.total}
          className={`${buttonClasses("secondary")} ${deck?.total ? "" : "pointer-events-none opacity-40"}`}
          title="Download a file to import into Anki (File → Import). Cards keep their chapter as a tag."
        >
          <Download size={14} /> Export to Anki
        </a>
        <Button variant="primary" onClick={startReview} disabled={!deck?.due}>
          Review due cards
        </Button>
      </section>

      <section className="rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
        <h3 className="font-medium">Add cards</h3>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
          <ChapterSelect chapters={chapters} value={chapterId} onChange={setChapterId} maxChapter={maxChapter} />
          <label className="flex items-center gap-1.5">
            Cards
            <input type="number" min={3} max={30} value={count} onChange={(e) => setCount(Math.min(30, Math.max(3, Number(e.target.value))))} className="w-16 rounded-lg border border-stone-300 bg-transparent px-2 py-1 dark:border-stone-700" />
          </label>
          <Button variant="primary" onClick={generate} loading={busy}>
            {busy ? "Creating cards…" : "Generate flashcards"}
          </Button>
        </div>
        {error && <div className="mt-3"><ErrorBox>{error}</ErrorBox></div>}
      </section>

      {deck && deck.cards.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-medium text-stone-500">All cards</h3>
          <ul className="divide-y divide-stone-100 rounded-xl border border-stone-200 bg-white text-sm dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900">
            {deck.cards.map((c) => (
              <li key={c.id} className="flex items-start gap-3 px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{c.front}</p>
                  <p className="text-stone-500">{c.back}</p>
                </div>
                <span className="shrink-0 text-xs text-stone-400" title="Next review">
                  {c.due_at && new Date(c.due_at) <= new Date() ? "due" : c.due_at ? new Date(c.due_at).toLocaleDateString() : ""}
                </span>
                <button onClick={async () => { await api.deleteCard(c.id); refresh(); }} className="text-stone-400 hover:text-red-600" title="Delete card">
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export default function StudyPanel() {
  const [tab, setTab] = useState<"quizzes" | "cards">("quizzes");

  // Space flips the current flashcard.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Space" && (e.target as HTMLElement)?.tagName !== "TEXTAREA" && (e.target as HTMLElement)?.tagName !== "INPUT") {
        const btn = document.querySelector<HTMLButtonElement>("button[aria-label='Show answer'],button[aria-label='Show question']");
        if (btn) {
          e.preventDefault();
          btn.click();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <PanelShell
      title="Study"
      actions={
        <Segmented
          value={tab}
          onChange={setTab}
          label="Study mode"
          options={[{ value: "quizzes", label: "Quizzes" }, { value: "cards", label: "Flashcards" }]}
        />
      }
    >
      {tab === "quizzes" ? <Quizzes /> : <Flashcards />}
      <p className="mt-6 flex items-center gap-1.5 text-xs text-stone-400">
        {tab === "quizzes" ? <GraduationCap size={14} /> : <Layers size={14} />}
        Questions and cards are generated only from passages within your spoiler limit.
      </p>
    </PanelShell>
  );
}
