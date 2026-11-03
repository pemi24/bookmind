"""Reading stats: time read per day, streaks, progress per book, quiz and flashcard results.

Days are the machine's local calendar days (BookMind runs on the reader's own computer).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActivityDay, Book, Chapter, Flashcard, Note, Quiz

ACTIVE_DAY_SECONDS = 60  # a day counts toward the streak after a minute of reading (or any card review)


async def add_activity(db: AsyncSession, book_id: int, *, seconds: int = 0, cards: int = 0,
                       day: date | None = None) -> None:
    stmt = insert(ActivityDay).values(book_id=book_id, day=day or date.today(), read_seconds=seconds,
                                      cards_reviewed=cards)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_activity_book_day",
        set_={"read_seconds": ActivityDay.read_seconds + stmt.excluded.read_seconds,
              "cards_reviewed": ActivityDay.cards_reviewed + stmt.excluded.cards_reviewed},
    )
    await db.execute(stmt)


def streak(active: set[date], today: date) -> int:
    """Consecutive active days ending today (or yesterday, so the streak survives until you read today)."""
    day = today if today in active else today - timedelta(days=1)
    n = 0
    while day in active:
        n += 1
        day -= timedelta(days=1)
    return n


async def compute(db: AsyncSession, days: int = 30, today: date | None = None) -> dict:
    today = today or date.today()
    rows = (await db.execute(
        select(ActivityDay.day, func.sum(ActivityDay.read_seconds), func.sum(ActivityDay.cards_reviewed))
        .group_by(ActivityDay.day))).all()
    per_day = {d: (int(s or 0), int(c or 0)) for d, s, c in rows}
    active = {d for d, (s, c) in per_day.items() if s >= ACTIVE_DAY_SECONDS or c > 0}
    daily = [{"day": (d := today - timedelta(days=i)).isoformat(), "seconds": per_day.get(d, (0, 0))[0],
              "cards": per_day.get(d, (0, 0))[1]} for i in range(days - 1, -1, -1)]

    seconds_by_book = dict((await db.execute(
        select(ActivityDay.book_id, func.sum(ActivityDay.read_seconds)).group_by(ActivityDay.book_id))).all())
    chapter_counts = dict((await db.execute(
        select(Chapter.book_id, func.count()).group_by(Chapter.book_id))).all())
    highlight_counts = dict((await db.execute(
        select(Note.book_id, func.count()).where(Note.kind == "passage").group_by(Note.book_id))).all())
    books = []
    for b in (await db.execute(select(Book).where(Book.status == "ready"))).scalars():
        total = chapter_counts.get(b.id, 0)
        books.append({
            "id": b.id, "title": b.title, "author": b.author, "seconds": int(seconds_by_book.get(b.id) or 0),
            "chapters": total, "furthest": b.furthest_position or 0,
            "finished": bool(total and (b.furthest_position or 0) >= total),
            "highlights": highlight_counts.get(b.id, 0),
            "last_read": b.reading_updated_at.isoformat() if b.reading_updated_at else None,
        })
    books.sort(key=lambda x: (x["last_read"] or "", x["seconds"]), reverse=True)

    attempts = [a for q in (await db.execute(select(Quiz.attempts))).scalars() for a in (q or [])]
    scores = [a["score"] / a["total"] for a in attempts if a.get("total")]
    now = datetime.now(timezone.utc)
    cards_total, cards_due, mastered = (await db.execute(select(
        func.count(Flashcard.id),
        func.count(Flashcard.id).filter(Flashcard.due_at <= now),
        func.count(Flashcard.id).filter(Flashcard.interval_days >= 21),
    ))).one()

    return {
        "today_seconds": per_day.get(today, (0, 0))[0],
        "week_seconds": sum(per_day.get(today - timedelta(days=i), (0, 0))[0] for i in range(7)),
        "total_seconds": sum(s for s, _ in per_day.values()),
        "streak_days": streak(active, today),
        "best_streak_days": _best_streak(active),
        "active_days": len(active),
        "daily": daily,
        "books": books,
        "books_finished": sum(b["finished"] for b in books),
        "quizzes": {"attempts": len(attempts), "average": round(sum(scores) / len(scores), 3) if scores else None},
        "flashcards": {"total": cards_total, "due": cards_due, "mastered": mastered,
                       "reviews": sum(c for _, c in per_day.values())},
    }


def _best_streak(active: set[date]) -> int:
    best = 0
    for d in active:
        if d - timedelta(days=1) not in active:  # start of a run
            n = 0
            while d + timedelta(days=n) in active:
                n += 1
            best = max(best, n)
    return best
