"""Study mode: quizzes (multiple choice, true/false, short answer) and SM-2 flashcards."""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Book, Chapter, Chunk, Flashcard, Quiz
from app.features.common import max_input_chars, sample_chunks
from app.llm import client as llm
from app.llm.prompts import study as P

QUESTION_TYPES = ("multiple_choice", "true_false", "short_answer")
GRADES = {"again": 1, "hard": 3, "good": 4, "easy": 5}  # SM-2 quality scores


def _passage_budget(n: int) -> int:
    """How many ~2,000-char passages to send: enough for n items, within the model's context."""
    return max(2, min(max(n, 4), 14, max_input_chars() // 2200))


# ---------------------------------------------------------------- quizzes

def _clean_question(q: P.QuestionOut, chunk: Chunk | None) -> dict | None:
    d = {"type": q.type, "question": q.question.strip(), "options": [o.strip() for o in q.options if o.strip()],
         "answer": q.answer.strip(), "explanation": q.explanation.strip(), "chunk_id": chunk.id if chunk else None}
    if q.type == "multiple_choice":
        if len(d["options"]) < 2:
            return None
        if d["answer"] not in d["options"]:  # model gave "B" or a paraphrase: try to recover
            letter = re.fullmatch(r"\(?([A-Da-d])\)?\.?", d["answer"])
            if letter and ord(letter.group(1).upper()) - 65 < len(d["options"]):
                d["answer"] = d["options"][ord(letter.group(1).upper()) - 65]
            else:
                match = [o for o in d["options"] if o.lower() == d["answer"].lower()]
                if not match:
                    return None
                d["answer"] = match[0]
    elif q.type == "true_false":
        d["options"] = ["True", "False"]
        d["answer"] = "True" if d["answer"].lower().startswith("t") else "False"
    else:
        d["options"] = []
    return d


async def generate_quiz(db: AsyncSession, book: Book, chapter_id: int | None, max_chapter: int | None,
                        n: int, types: list[str], difficulty: str) -> Quiz:
    chunks = await sample_chunks(db, book.id, chapter_id, max_chapter, _passage_budget(n))
    if not chunks:
        raise llm.LLMError("No passages available for a quiz in this range.", 400)
    out = await llm.complete_json(
        P.QUIZ_SYSTEM, P.quiz_user(book.title, [c.text for c in chunks], n, types, difficulty), P.QuizOut,
        model=get_settings().llm_fast_model, max_tokens=12000,
    )
    questions = []
    for q in out.questions:
        if q.type not in types:
            continue
        chunk = chunks[q.passage - 1] if 1 <= q.passage <= len(chunks) else None
        cleaned = _clean_question(q, chunk)
        if cleaned:
            questions.append(cleaned)
    if not questions:
        raise llm.LLMError("The AI didn't produce usable questions. Try again.", 502)
    quiz = Quiz(book_id=book.id, chapter_id=chapter_id, title=out.title.strip()[:300] or "Quiz",
                questions=questions[:n], attempts=[])
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz)
    return quiz


def public_question(q: dict, i: int) -> dict:
    """A question without its answer (sent before submission)."""
    return {"index": i, "type": q["type"], "question": q["question"], "options": q["options"]}


async def grade_quiz(db: AsyncSession, quiz: Quiz, answers: list[str | None]) -> dict:
    results: list[dict] = []
    short: list[tuple[int, str, str, str]] = []
    for i, q in enumerate(quiz.questions):
        given = (answers[i] if i < len(answers) else None) or ""
        r = {"index": i, "given": given, "answer": q["answer"], "explanation": q["explanation"],
             "chunk_id": q.get("chunk_id"), "correct": False, "feedback": None}
        if q["type"] == "short_answer":
            if given.strip():
                short.append((i, q["question"], q["answer"], given.strip()))
            else:
                r["feedback"] = "No answer given."
        else:
            r["correct"] = given.strip().lower() == q["answer"].strip().lower()
        results.append(r)

    if short:
        graded = await llm.complete_json(P.GRADE_SYSTEM, P.grade_user(short), P.GradesOut,
                                         model=get_settings().llm_fast_model, max_tokens=4000)
        by_index = {g.index: g for g in graded.grades}
        for i, *_ in short:
            g = by_index.get(i)
            if g:
                results[i]["correct"] = bool(g.correct)
                results[i]["feedback"] = g.feedback

    score = sum(r["correct"] for r in results)
    total = len(results)
    quiz.attempts = [*(quiz.attempts or []), {"score": score, "total": total,
                                              "at": datetime.now(timezone.utc).isoformat()}]
    pct = score / total if total else 0
    quiz.best_score = max(quiz.best_score or 0, pct)
    await db.commit()
    return {"score": score, "total": total, "results": results}


# ---------------------------------------------------------------- flashcards

def sm2(ease: float, interval: int, reps: int, quality: int) -> tuple[float, int, int]:
    """SuperMemo-2. Returns (ease, interval_days, repetitions)."""
    if quality < 3:
        return max(1.3, ease - 0.2), 1, 0
    reps += 1
    if reps == 1:
        interval = 1
    elif reps == 2:
        interval = 6 if quality >= 4 else 3
    else:
        interval = round(interval * ease * (1.3 if quality == 5 else 1.0))
    ease = max(1.3, ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    return ease, max(interval, 1), reps


def review(card: Flashcard, grade: str, now: datetime | None = None) -> Flashcard:
    now = now or datetime.now(timezone.utc)
    card.ease, card.interval_days, card.repetitions = sm2(card.ease, card.interval_days, card.repetitions,
                                                         GRADES[grade])
    # "Again" comes back in 10 minutes within the same session; others after N days.
    card.due_at = now + (timedelta(minutes=10) if grade == "again" else timedelta(days=card.interval_days))
    return card


async def generate_cards(db: AsyncSession, book: Book, chapter_id: int | None, max_chapter: int | None,
                         n: int) -> list[Flashcard]:
    chunks = await sample_chunks(db, book.id, chapter_id, max_chapter, _passage_budget(n))
    if not chunks:
        raise llm.LLMError("No passages available in this range.", 400)
    out = await llm.complete_json(P.CARDS_SYSTEM, P.cards_user(book.title, [c.text for c in chunks], n), P.CardsOut,
                                  model=get_settings().llm_fast_model, max_tokens=8000)
    cards = []
    for c in out.cards[:n]:
        chunk = chunks[c.passage - 1] if 1 <= c.passage <= len(chunks) else None
        card = Flashcard(book_id=book.id, chapter_id=chunk.chapter_id if chunk else chapter_id,
                         chunk_id=chunk.id if chunk else None, front=c.front.strip(), back=c.back.strip(),
                         ease=2.5, interval_days=0, repetitions=0, due_at=datetime.now(timezone.utc))
        db.add(card)
        cards.append(card)
    await db.commit()
    for c in cards:
        await db.refresh(c)
    return cards


# ---------------------------------------------------------------- Anki export

def _anki_field(text: str) -> str:
    # Tabs/newlines would break the tab-separated rows; the file declares #html:true.
    return html.escape(text.strip()).replace("\t", " ").replace("\r", "").replace("\n", "<br>")


def to_anki(book: Book, rows: list[tuple[Flashcard, Chapter | None]]) -> str:
    """Anki "Notes in plain text" import file: Basic note type, one deck per book, chapter tags."""
    deck = re.sub(r"[:\s]+", " ", book.title).strip() or "Book"  # "::" would nest decks in Anki
    book_tag = re.sub(r"[^\w]+", "_", book.title.lower()).strip("_")[:40] or "book"
    lines = ["#separator:tab", "#html:true", "#notetype:Basic", f"#deck:BookMind::{deck}", "#tags column:3"]
    for card, chapter in rows:
        back = _anki_field(card.back)
        tags = ["bookmind", book_tag]
        if chapter is not None:
            back += f'<br><br><small>{_anki_field(f"{book.title} — {chapter.title}")}</small>'
            tags.append(f"ch{chapter.position:02d}")
        lines.append("\t".join([_anki_field(card.front), back, " ".join(tags)]))
    return "\n".join(lines) + "\n"
