from datetime import datetime, timezone
from types import SimpleNamespace

from app.features.analysis import EntityMerger
from app.features.common import find_verbatim, normalize_name, split_text
from app.features.notes import to_markdown, to_pdf
from app.features.study import _clean_question, review, sm2
from app.llm.prompts.analysis import EntityOut
from app.llm.prompts.study import QuestionOut

TEXT = "“Off with her head!” the Queen shouted at the top of her voice.\n\nNobody moved."


def test_find_verbatim_tolerates_quotes_case_and_whitespace():
    s, e = find_verbatim(TEXT, '"off with her head!"  the queen shouted')
    assert TEXT[s:e] == "Off with her head!” the Queen shouted"
    assert find_verbatim(TEXT, "Off with his head") is None  # not really there
    assert find_verbatim(TEXT, "ab") is None
    s, e = find_verbatim(TEXT, "her voice. Nobody moved.")  # across a paragraph break
    assert TEXT[s:e] == "her voice.\n\nNobody moved."


def test_split_text_respects_paragraphs():
    text = "\n\n".join(["x" * 100] * 10)
    parts = split_text(text, max_chars=250)
    assert all(len(p) <= 250 for p in parts)
    assert "\n\n".join(parts) == text


def test_sm2_schedule():
    ease, interval, reps = 2.5, 0, 0
    ease, interval, reps = sm2(ease, interval, reps, 4)
    assert (interval, reps) == (1, 1)
    ease, interval, reps = sm2(ease, interval, reps, 4)
    assert (interval, reps) == (6, 2)
    ease, interval, reps = sm2(ease, interval, reps, 5)
    assert interval > 6 and ease > 2.5
    ease2, interval2, reps2 = sm2(ease, interval, reps, 1)  # forgot it
    assert (interval2, reps2) == (1, 0) and ease2 < ease
    assert sm2(1.3, 1, 0, 1)[0] == 1.3  # ease floor


def test_review_again_is_due_soon():
    card = SimpleNamespace(ease=2.5, interval_days=6, repetitions=2, due_at=None)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    review(card, "again", now)
    assert (card.due_at - now).total_seconds() == 600
    review(card, "good", now)
    assert card.interval_days == 1 and (card.due_at - now).days == 1


def test_entity_merger_aliases_and_first_chapter():
    m = EntityMerger()
    m.add(EntityOut(name="The White Rabbit", kind="character", aliases=["Rabbit"], description="Late.",
                    importance=3), chapter=1)
    hit = m.add(EntityOut(name="Rabbit", kind="character", aliases=["Mr. Rabbit"], description="Has gloves.",
                          importance=4), chapter=4)
    assert len(m.entities) == 1
    assert hit.name == "The White Rabbit" and hit.first_chapter == 1 and hit.importance == 4
    assert [d["chapter"] for d in hit.details] == [1, 4]
    assert m.find("mr. rabbit") is hit
    assert normalize_name("The Queen’s") == "queen's"


def _q(**kw):
    base = dict(type="multiple_choice", question="Q?", options=["A1", "B1", "C1", "D1"], answer="B",
                explanation="because", passage=1)
    base.update(kw)
    return QuestionOut(**base)


def test_clean_question_recovers_answers():
    assert _clean_question(_q(), None)["answer"] == "B1"  # letter -> option
    assert _clean_question(_q(answer="c1"), None)["answer"] == "C1"  # case-insensitive
    assert _clean_question(_q(answer="nonsense"), None) is None  # unusable
    tf = _clean_question(_q(type="true_false", options=[], answer="true"), None)
    assert tf["options"] == ["True", "False"] and tf["answer"] == "True"


def _note(**kw):
    base = dict(kind="quote", title=None, content="“Curiouser and curiouser!” [1]", tags=["fav"],
                location={"chapter_title": "Chapter II", "page": 12})
    base.update(kw)
    return SimpleNamespace(**base)


def test_exports():
    book = SimpleNamespace(title="Alice’s Adventures", author="Lewis Carroll")
    md = to_markdown(book, [_note(), _note(kind="answer", content="She grows. [2]", title="Why?")])
    assert "# Notes — Alice’s Adventures" in md and "> “Curiouser and curiouser!”" in md
    assert "[1]" not in md and "#fav" in md and "Chapter II · p. 12" in md
    pdf = to_pdf(book, [_note()])
    assert pdf.startswith(b"%PDF") and len(pdf) > 500
