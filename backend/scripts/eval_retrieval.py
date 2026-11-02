"""Sanity-check retrieval quality on the sample book (no LLM calls, no cost).

    python scripts/eval_retrieval.py                 # uses the indexed "Alice" book
    python scripts/eval_retrieval.py --book-id 3 --cases my_cases.json -k 8

A case passes when one of the top-k passages comes from the expected chapter AND
contains every expected keyword (case-insensitive). Reports hit@1, hit@k and MRR,
so you can compare chunking/retrieval settings before and after a change.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.models import Book  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.retrieval.hybrid import search_book  # noqa: E402

# Expected chapter = chapter position in the Gutenberg text (12 chapters).
ALICE_CASES = [
    {"q": "What does Alice see that makes her follow the White Rabbit?",
     "chapter": 1, "keywords": ["waistcoat-pocket"]},
    {"q": "What was written on the little bottle Alice found?", "chapter": 1, "keywords": ["drink me"]},
    {"q": "How does Alice end up swimming in a pool?", "chapter": 2, "keywords": ["tears"]},
    {"q": "What is a Caucus-race and who wins it?", "chapter": 3, "keywords": ["everybody has won"]},
    {"q": "What advice does the Caterpillar give Alice about the mushroom?",
     "chapter": 5, "keywords": ["mushroom", "one side"]},
    {"q": "What happens to the Duchess's baby?", "chapter": 6, "keywords": ["pig"]},
    {"q": "Why is it always six o'clock at the tea-party?", "chapter": 7, "keywords": ["six o’clock"]},
    {"q": "Why are the gardeners painting the roses red?", "chapter": 8, "keywords": ["red rose-tree"]},
    {"q": "What does the Queen of Hearts shout whenever she is angry?",
     "chapter": 8, "keywords": ["off with"]},
    {"q": "Why did the Mock Turtle's schoolmaster get called Tortoise?",
     "chapter": 9, "keywords": ["taught us"]},
    {"q": "Who is accused of stealing the tarts?", "chapter": 11, "keywords": ["knave"]},
    {"q": "How does Alice's adventure end?", "chapter": 12, "keywords": ["sister"]},
]


def matches(p, case) -> bool:
    text = p.text.lower()
    return p.chapter_position == case["chapter"] and all(k.lower() in text for k in case["keywords"])


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-id", type=int)
    ap.add_argument("--cases", type=Path, help="JSON list of {q, chapter, keywords}")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--no-rerank", action="store_true")
    args = ap.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8")) if args.cases else ALICE_CASES
    async with SessionLocal() as db:
        if args.book_id:
            book = await db.get(Book, args.book_id)
        else:
            book = (await db.execute(
                select(Book).where(Book.title.ilike("%alice%"), Book.status == "ready").order_by(Book.id.desc())
            )).scalars().first()
        if book is None:
            sys.exit("No indexed book found. Upload samples/alice-in-wonderland.txt first (or pass --book-id).")
        book_id = book.id  # rollback() below expires ORM objects; keep the plain id
        print(f"Evaluating on '{book.title}' (id {book_id}), k={args.k}, rerank={not args.no_rerank}\n")

        hit1 = hitk = 0
        rr = 0.0
        for case in cases:
            passages = await search_book(db, case["q"], book_id, top_k=args.k, use_rerank=not args.no_rerank)
            rank = next((i for i, p in enumerate(passages, 1) if matches(p, case)), None)
            hit1 += rank == 1
            hitk += rank is not None
            rr += 1 / rank if rank else 0
            top = passages[0] if passages else None
            mark = "OK " if rank else "MISS"
            where = f"ch{top.chapter_position} p{top.page_start}" if top else "-"
            print(f"[{mark}] rank={rank or '-':>2}  top={where:<10} {case['q']}")
            await db.rollback()  # end the SET LOCAL transaction between queries

    n = len(cases)
    print(f"\nhit@1 = {hit1 / n:.0%}   hit@{args.k} = {hitk / n:.0%}   MRR = {rr / n:.3f}   ({n} cases)")
    await engine.dispose()


if __name__ == "__main__":
    # psycopg async needs a selector loop on Windows.
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
