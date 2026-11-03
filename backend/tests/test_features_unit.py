from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

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
                location={"chapter_title": "Chapter II", "page": 12}, color=None, comment=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_exports():
    book = SimpleNamespace(title="Alice’s Adventures", author="Lewis Carroll")
    md = to_markdown(book, [_note(), _note(kind="answer", content="She grows. [2]", title="Why?")])
    assert "# Notes — Alice’s Adventures" in md and "> “Curiouser and curiouser!”" in md
    assert "[1]" not in md and "#fav" in md and "Chapter II · p. 12" in md
    md = to_markdown(book, [_note(kind="passage", comment="Alice is changing.")])
    assert "> “Curiouser and curiouser!”\n\nAlice is changing." in md
    pdf = to_pdf(book, [_note(), _note(kind="passage", comment="Alice is changing.")])
    assert pdf.startswith(b"%PDF") and len(pdf) > 500


def test_anki_export():
    from app.features.study import to_anki

    book = SimpleNamespace(title="Alice: Wonderland")
    ch = SimpleNamespace(title="Down the Rabbit-Hole", position=1)
    cards = [(SimpleNamespace(front="Who is late?", back="The White\tRabbit\n<watch>"), ch),
             (SimpleNamespace(front="Loose card", back="No chapter"), None)]
    out = to_anki(book, cards)
    lines = out.splitlines()
    assert lines[:5] == ["#separator:tab", "#html:true", "#notetype:Basic", "#deck:BookMind::Alice Wonderland",
                         "#tags column:3"]
    front, back, tags = lines[5].split("\t")
    assert front == "Who is late?" and "The White Rabbit<br>&lt;watch&gt;" in back and "Down the Rabbit-Hole" in back
    assert tags == "bookmind alice_wonderland ch01"
    assert lines[6].split("\t")[2] == "bookmind alice_wonderland" and len(lines) == 7


CLIPPINGS = """﻿The Lighthouse Keeper: A Novel (Test Author)
- Your Highlight on page 3 | Location 40-42 | Added on Monday, 1 January 2024 10:00:00

In the morning Mara found a small brass key lying in the sand
==========
The Lighthouse Keeper: A Novel (Test Author)
- Your Note on page 3 | Location 42 | Added on Monday, 1 January 2024 10:01:00

Where does the key come from?
==========
The Lighthouse Keeper: A Novel (Test Author)
- Your Bookmark on page 5 | Location 60 | Added on Monday, 1 January 2024 10:02:00


==========
﻿L'Art de la guerre (Sun Tzu)
- Votre surlignement sur la page 12 | emplacement 180-182 | Ajouté le lundi 1 janvier 2024

Tout l'art de la guerre est fondé sur la duperie.
==========
"""


def test_parse_kindle_clippings():
    from app.features.kindle import parse_clippings, summarize, title_score

    clips = parse_clippings(CLIPPINGS.replace("\n", "\r\n"))  # Kindles write Windows line endings
    assert [(c.kind, c.loc_start, c.loc_end) for c in clips] == [("highlight", 40, 42), ("note", 42, 42), ("highlight", 180, 182)]
    assert clips[0].title == "The Lighthouse Keeper: A Novel" and clips[0].author == "Test Author" and clips[0].page == 3
    assert clips[2].title == "L'Art de la guerre" and clips[2].text.startswith("Tout l'art")
    rows = summarize(clips, "The Lighthouse Keeper")
    assert rows[0]["title"] == "The Lighthouse Keeper: A Novel" and rows[0]["highlights"] == 1 and rows[0]["notes"] == 1
    assert rows[0]["match"] >= 0.9 > title_score("The Lighthouse Keeper", "L'Art de la guerre")


def test_text_index_find_span():
    from app.features.common import TextIndex

    text = "Intro.\n\nIt was the best of times, it was the worst of times, it was the age of wisdom, it was the age of foolishness, it was the epoch of belief."
    idx = TextIndex(text)
    exact = idx.find_span(TextIndex.prepare("IT WAS the best  of times"))
    assert text[exact[0]:exact[1]] == "It was the best of times"
    # A different edition: same opening and closing words, one word changed in the middle.
    variant = "It was the best of times, it was the worst of times, it was the era of wisdom, it was the age of foolishness, it was the epoch of belief."
    span = idx.find_span(TextIndex.prepare(variant))
    assert span and text[span[0]:span[1]].endswith("epoch of belief.") and text[span[0]:].startswith("It was the best")
    assert idx.find_span(TextIndex.prepare("nothing like this text at all, not one word of it matches here ok")) is None


OPDS_SEARCH = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<link rel="next" href="/ebooks/search.opds/?query=war&amp;start_index=26"/>
<entry><id>https://www.gutenberg.org/ebooks/authors/search.opds/?query=war</id><title>Authors</title></entry>
<entry><id>https://www.gutenberg.org/ebooks/132.opds</id><title>The Art of War</title>
<content type="text">active 6th century B.C. Sunzi</content></entry>
<entry><id>https://www.gutenberg.org/ebooks/1946.opds</id><title>On War</title>
<content type="text">Carl von Clausewitz</content></entry>
</feed>"""

OPDS_BOOK = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>ignored</title>
<entry><title>Alice's Adventures in Wonderland</title><author><name>Carroll, Lewis, 1832-1898</name></author></entry>
</feed>"""


def test_gutenberg_catalog_parsing():
    from app.features.catalog import CatalogError, parse_book, parse_search

    res = parse_search(OPDS_SEARCH)
    assert res["has_more"] is True
    assert [(r["source"], r["id"], r["title"], r["author"]) for r in res["results"]] == [
        ("gutenberg", "132", "The Art of War", "Sunzi"), ("gutenberg", "1946", "On War", "Carl von Clausewitz")]
    assert res["results"][0]["cover"].endswith("/cache/epub/132/pg132.cover.medium.jpg")
    assert parse_book(OPDS_BOOK) == {"title": "Alice's Adventures in Wonderland", "author": "Lewis Carroll"}
    with pytest.raises(CatalogError):
        parse_search("<html>Service unavailable</html")


SE_SEARCH = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>https://standardebooks.org/ebooks/bram-stoker/dracula</id><title>Dracula</title>
<author><name>Bram Stoker</name></author>
<link href="https://standardebooks.org/ebooks/bram-stoker/dracula/downloads/cover-thumbnail.jpg" rel="http://opds-spec.org/image/thumbnail"/>
</entry>
<entry><id>https://example.com/not-a-book</id><title>Spam</title></entry>
</feed>"""


def test_more_free_book_sources():
    from app.features.catalog import (CatalogError, archive_files, catalog_name, download_prefix,
                                      parse_archive_search, parse_standard_search, standard_epub_url)

    se = parse_standard_search(SE_SEARCH)["results"]
    assert [(r["source"], r["id"], r["title"], r["author"]) for r in se] == [
        ("standard", "bram-stoker/dracula", "Dracula", "Bram Stoker")]
    assert standard_epub_url("bram-stoker/dracula").startswith(
        "https://standardebooks.org/ebooks/bram-stoker/dracula/downloads/bram-stoker_dracula.epub")

    ia = parse_archive_search({"response": {"numFound": 3, "docs": [
        {"identifier": "dracula00stok", "title": "Dracula", "creator": "Stoker, Bram, 1847-1912", "year": "1899"},
        {"identifier": "dracu00stok", "title": "Dracula", "creator": ["Stoker, Bram, 1847-1912"]},  # another scan
        {"identifier": "bad id!", "title": "x"},
    ]}})
    assert [(r["id"], r["title"], r["author"]) for r in ia["results"]] == [("dracula00stok", "Dracula (1899)", "Bram Stoker")]

    free = {"metadata": {"possible-copyright-status": "NOT_IN_COPYRIGHT", "collection": ["americana"]},
            "files": [{"name": "x_djvu.txt", "format": "DjVuTXT"}, {"name": "x.epub", "format": "EPUB"},
                      {"name": "y.epub", "format": "EPUB", "private": "true"}]}
    assert archive_files("x", free) == [("https://archive.org/download/x/x.epub", ".epub"),
                                        ("https://archive.org/download/x/x_djvu.txt", ".txt")]
    for blocked in ({"possible-copyright-status": "NOT_IN_COPYRIGHT", "collection": ["inlibrary"]},  # loan-only
                    {"possible-copyright-status": "", "collection": "opensource"},  # uploader's own claim only
                    {"possible-copyright-status": "NOT_IN_COPYRIGHT", "access-restricted-item": "true"}):
        with pytest.raises(CatalogError) as e:
            archive_files("x", {"metadata": blocked, "files": free["files"]})
        assert e.value.status == 403

    assert catalog_name("Marcus Aurelius, Emperor of Rome, 121-180") == "Marcus Aurelius"
    assert download_prefix("gutenberg", "132") == "gutenberg-132."  # same names as books imported before
    assert download_prefix("standard", "bram-stoker/dracula") == "standard-bram-stoker_dracula."


async def test_catalog_search_survives_a_failing_source(monkeypatch):
    from app.features import catalog

    async def ok(query, page):
        return {"results": [{"source": "gutenberg", "id": "1", "title": "T", "author": None, "cover": "", "url": ""}],
                "has_more": False}

    async def down(query, page):
        raise catalog.CatalogError("Standard Ebooks is busy or down (503). Try again in a minute.", 503)

    async def slow(query, page):
        import asyncio
        await asyncio.sleep(5)

    monkeypatch.setattr(catalog, "SOURCE_TIMEOUT", 0.2)
    monkeypatch.setattr(catalog, "SOURCES", [catalog.Source("gutenberg", "Project Gutenberg", ok, None),
                                             catalog.Source("standard", "Standard Ebooks", down, None),
                                             catalog.Source("archive", "Internet Archive", slow, None)])
    monkeypatch.setattr(catalog, "BY_KEY", {s.key: s for s in catalog.SOURCES})
    res = await catalog.search("t", 1)
    assert [r["id"] for r in res["results"]] == ["1"]
    status = {s["key"]: s for s in res["sources"]}
    assert status["gutenberg"]["count"] == 1 and status["gutenberg"]["error"] is None
    assert "busy" in status["standard"]["error"] and "too long" in status["archive"]["error"]


def test_streaks_and_translation_batches():
    from datetime import date, timedelta

    from app.features.stats import _best_streak, streak
    from app.features.translate import batches, needs_translation

    today = date(2026, 11, 3)
    days = {today - timedelta(days=i) for i in (1, 2, 3, 6, 7)}
    assert streak(days, today) == 3  # not read today yet: yesterday's streak still counts
    assert streak(days | {today}, today) == 4 and streak({today - timedelta(days=2)}, today) == 0
    assert _best_streak(days) == 3

    paras = ["* * *", "A" * 50, "B" * 50, "C" * 200, "12", "D" * 10]
    assert not needs_translation("* * *") and not needs_translation("12") and needs_translation("Hi there")
    assert batches(paras, budget=120) == [[1, 2], [3], [5]]


def test_refusal_detection():
    from app.llm.prompts.chat import admits_gap, is_not_found

    refusals = ["The book doesn't say.", "The book doesn't say. [1]", "I couldn't find that in the book.",
                "The provided passages do not state who the father of Abraham was.",
                "The provided passages do not state who the mother of Samuel was [1, 2, 3].",
                "The passages don’t mention his father.", "There is no information about this in the passages."]
    answers = ["The passages state that the woman who bore Samson was the wife of Manoah [1].",
               "Terah was the father of Abram [1].",
               "Hannah is the mother of Samuel; the passages do not state her age, but she prayed at Shiloh [1].",
               "Alice follows the White Rabbit down a rabbit-hole [2]. The book doesn't say why.",
               "The book doesn't say who his father was, but it names his mother Hannah [3]."]
    assert all(is_not_found(r) for r in refusals)
    assert not any(is_not_found(a) for a in answers)
    # Partial answers that admit a gap still get a second search; complete answers don't.
    assert admits_gap("Elkanah had two wives, Hannah and Peninnah [2]. However, the passages do not show who "
                      "the mother of Samuel was.")
    assert not admits_gap("Terah was the father of Abram [1].")


def test_book_overview_prompt():
    from app.llm.prompts.chat import build_overview, build_system

    chapters = [("Down the Rabbit-Hole", "Alice follows a White Rabbit. She falls down a deep hole."),
                ("The Pool of Tears", None)]
    ov = build_overview("Alice", "Lewis Carroll", chapters, "A girl falls into Wonderland.")
    assert '"Alice" by Lewis Carroll' in ov and "Book summary: A girl falls into Wonderland." in ov
    assert "1. Down the Rabbit-Hole: Alice follows a White Rabbit. She falls down a deep hole." in ov
    assert "2. The Pool of Tears" in ov and ov in build_system(overview=ov)
    # Too long for the budget: first sentences only, then titles only.
    many = [(f"Chapter {i}", "First sentence here. " + "More detail. " * 40) for i in range(1, 60)]
    short = build_overview("Big", None, many, max_chars=3000)
    assert "1. Chapter 1: First sentence here." in short and "More detail" not in short
    tiny = build_overview("Big", None, many, max_chars=600)
    assert "1. Chapter 1\n" in tiny and "First sentence" not in tiny


def test_pdf_outline_depth():
    from app.ingestion.parsers.pdf import outline_chapters

    bible = (
        [[1, "Cover", 1], [1, "Old Testament", 3], [2, "Genesis", 4]]
        + [[3, f"Genesis {i}", 4 + i] for i in range(1, 51)] + [[2, "Exodus", 60]]
        + [[3, f"Exodus {i}", 60 + i] for i in range(1, 41)] + [[1, "New Testament", 200], [2, "Matthew", 201]]
        + [[3, f"Matthew {i}", 201 + i] for i in range(1, 129)]
    )
    # Level 3 would give 220 chapters: too many, so the books (level 2) are used, with "Cover" kept.
    assert [t for t, _ in outline_chapters(bible)] == ["Cover", "Genesis", "Exodus", "Matthew"]
    assert outline_chapters([[1, "Book", 1], [2, "Ch 1", 2], [2, "Ch 2", 5]]) == [("Ch 1", 2), ("Ch 2", 5)]
    assert outline_chapters([[1, "A", 1], [1, "B", 3]]) == [("A", 1), ("B", 3)] and outline_chapters([]) == []