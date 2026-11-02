"""Study mode endpoints: quizzes and flashcards."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.features import effective_max_chapter, require_llm
from app.db.models import Chunk, Flashcard, Quiz
from app.db.session import get_db
from app.features import study
from app.features.common import get_chapter, ready_book

router = APIRouter(prefix="/api", tags=["study"])


class QuizRequest(BaseModel):
    chapter_id: int | None = None
    max_chapter: int | None = None
    num_questions: int = Field(default=8, ge=3, le=20)
    types: list[Literal["multiple_choice", "true_false", "short_answer"]] = Field(
        default_factory=lambda: list(study.QUESTION_TYPES), min_length=1)
    difficulty: Literal["easy", "medium", "hard"] = "medium"


def _quiz_summary(q: Quiz) -> dict:
    return {"id": q.id, "title": q.title, "chapter_id": q.chapter_id, "num_questions": len(q.questions),
            "best_score": q.best_score, "attempts": len(q.attempts or []),
            "created_at": q.created_at.isoformat() if q.created_at else None}


@router.post("/books/{book_id}/quizzes", status_code=201)
async def create_quiz(book_id: int, req: QuizRequest, db: AsyncSession = Depends(get_db)):
    book = await ready_book(db, book_id)
    require_llm()
    max_ch = await effective_max_chapter(db, book_id, req.max_chapter)
    if req.chapter_id is not None:
        await get_chapter(db, book_id, req.chapter_id, max_ch)
    quiz = await study.generate_quiz(db, book, req.chapter_id, max_ch, req.num_questions, list(req.types),
                                     req.difficulty)
    return {**_quiz_summary(quiz), "questions": [study.public_question(q, i) for i, q in enumerate(quiz.questions)]}


async def _furthest_chapters(db: AsyncSession, quizzes: list[Quiz]) -> dict[int, int]:
    """Quiz id -> furthest chapter position its questions draw on (for the spoiler guard)."""
    ids = {q.get("chunk_id") for quiz in quizzes for q in quiz.questions if q.get("chunk_id")}
    pos = dict((await db.execute(select(Chunk.id, Chunk.chapter_position).where(Chunk.id.in_(ids)))).all()) if ids else {}
    return {quiz.id: max((pos.get(q.get("chunk_id"), 0) for q in quiz.questions), default=0) for quiz in quizzes}


@router.get("/books/{book_id}/quizzes")
async def list_quizzes(book_id: int, max_chapter: int | None = None, db: AsyncSession = Depends(get_db)):
    """Quizzes, hiding those that draw on chapters beyond the spoiler limit."""
    rows = list((await db.execute(select(Quiz).where(Quiz.book_id == book_id).order_by(Quiz.id.desc()))).scalars())
    furthest = await _furthest_chapters(db, rows)
    return [_quiz_summary(q) for q in rows if max_chapter is None or furthest[q.id] <= max_chapter]


@router.get("/quizzes/{quiz_id}")
async def get_quiz(quiz_id: int, max_chapter: int | None = None, db: AsyncSession = Depends(get_db)):
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(404, "Quiz not found.")
    if max_chapter is not None and (await _furthest_chapters(db, [quiz]))[quiz.id] > max_chapter:
        raise HTTPException(403, "Spoiler guard: this quiz covers chapters you haven't reached yet.")
    return {**_quiz_summary(quiz), "questions": [study.public_question(q, i) for i, q in enumerate(quiz.questions)]}


class QuizSubmission(BaseModel):
    answers: list[str | None]


@router.post("/quizzes/{quiz_id}/submit")
async def submit_quiz(quiz_id: int, sub: QuizSubmission, db: AsyncSession = Depends(get_db)):
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(404, "Quiz not found.")
    if any(q["type"] == "short_answer" for q in quiz.questions):
        require_llm()
    result = await study.grade_quiz(db, quiz, sub.answers)
    # Attach source locations so each explanation links to its passage.
    ids = [r["chunk_id"] for r in result["results"] if r["chunk_id"]]
    chunks = {c.id: c for c in (await db.execute(select(Chunk).where(Chunk.id.in_(ids)))).scalars()} if ids else {}
    for r in result["results"]:
        c = chunks.get(r["chunk_id"])
        r["source"] = ({"chunk_id": c.id, "chapter_id": c.chapter_id, "chapter_position": c.chapter_position,
                        "page": c.page_start, "char_start": c.char_start, "char_end": c.char_end} if c else None)
    return result


@router.delete("/quizzes/{quiz_id}", status_code=204)
async def delete_quiz(quiz_id: int, db: AsyncSession = Depends(get_db)):
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(404, "Quiz not found.")
    await db.delete(quiz)
    await db.commit()


# ---------------------------------------------------------------- flashcards

class CardsRequest(BaseModel):
    chapter_id: int | None = None
    max_chapter: int | None = None
    count: int = Field(default=10, ge=3, le=30)


def _card(c: Flashcard, chunk: Chunk | None = None) -> dict:
    return {"id": c.id, "front": c.front, "back": c.back, "chapter_id": c.chapter_id, "chunk_id": c.chunk_id,
            "ease": round(c.ease, 2), "interval_days": c.interval_days, "repetitions": c.repetitions,
            "due_at": c.due_at.isoformat() if c.due_at else None,
            "source": ({"chapter_id": chunk.chapter_id, "chapter_position": chunk.chapter_position,
                        "page": chunk.page_start, "char_start": chunk.char_start, "char_end": chunk.char_end}
                       if chunk else None)}


@router.post("/books/{book_id}/flashcards", status_code=201)
async def create_cards(book_id: int, req: CardsRequest, db: AsyncSession = Depends(get_db)):
    book = await ready_book(db, book_id)
    require_llm()
    max_ch = await effective_max_chapter(db, book_id, req.max_chapter)
    if req.chapter_id is not None:
        await get_chapter(db, book_id, req.chapter_id, max_ch)
    cards = await study.generate_cards(db, book, req.chapter_id, max_ch, req.count)
    return [_card(c) for c in cards]


@router.get("/books/{book_id}/flashcards")
async def list_cards(book_id: int, due_only: bool = False, db: AsyncSession = Depends(get_db)):
    stmt = (select(Flashcard, Chunk).outerjoin(Chunk, Chunk.id == Flashcard.chunk_id)
            .where(Flashcard.book_id == book_id).order_by(Flashcard.due_at, Flashcard.id))
    if due_only:
        stmt = stmt.where(Flashcard.due_at <= datetime.now(timezone.utc))
    rows = (await db.execute(stmt)).all()
    total = await db.scalar(select(func.count()).select_from(Flashcard).where(Flashcard.book_id == book_id))
    due = await db.scalar(select(func.count()).select_from(Flashcard).where(
        Flashcard.book_id == book_id, Flashcard.due_at <= datetime.now(timezone.utc)))
    return {"total": total, "due": due, "cards": [_card(c, ch) for c, ch in rows]}


class ReviewRequest(BaseModel):
    grade: Literal["again", "hard", "good", "easy"]


@router.post("/flashcards/{card_id}/review")
async def review_card(card_id: int, req: ReviewRequest, db: AsyncSession = Depends(get_db)):
    card = await db.get(Flashcard, card_id)
    if card is None:
        raise HTTPException(404, "Flashcard not found.")
    study.review(card, req.grade)
    await db.commit()
    return _card(card)


@router.delete("/flashcards/{card_id}", status_code=204)
async def delete_card(card_id: int, db: AsyncSession = Depends(get_db)):
    card = await db.get(Flashcard, card_id)
    if card is None:
        raise HTTPException(404, "Flashcard not found.")
    await db.delete(card)
    await db.commit()
