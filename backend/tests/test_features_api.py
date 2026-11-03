"""End-to-end feature endpoints with a scripted fake LLM (no API key or cost needed).

Covers: analysis job -> explorer + timeline (spoiler-filtered), quote finder verbatim
verification, quizzes (+ grading), flashcards (+ review), summaries (chapter, whole book,
spoiler), notes CRUD + export, and chat with the spoiler guard.
"""
from __future__ import annotations

import asyncio
import json
import re

import httpx
import pytest

from tests.test_retrieval_api import BOOK, C1, C2, C3, _wait_ready

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def fake_complete_json(system, user, schema, **kw):
    from app.llm.prompts import analysis, book, quotes, study

    if schema is analysis.ChapterAnalysis:
        ch = re.search(r"Chapter: (.+)", user).group(1)
        E, R, V = analysis.EntityOut, analysis.RelationOut, analysis.EventOut
        if "Storm" in ch:
            return analysis.ChapterAnalysis(
                entities=[E(name="Mara", kind="character", aliases=["the keeper"], description="Keeps the lighthouse.",
                            importance=5),
                          E(name="The Lighthouse", kind="place", aliases=[], description="On the northern cliff.",
                            importance=4)],
                relations=[R(source="Mara", target="The Lighthouse", relation="keeps", description="")],
                events=[V(title="The storm arrives", description="A violent storm hits.", when="One autumn evening",
                          importance=4, evidence="a violent storm rolled in from the sea")])
        if "Key" in ch:
            return analysis.ChapterAnalysis(
                entities=[E(name="Mara", kind="character", aliases=["Mara"], description="Finds a key.", importance=5),
                          E(name="Brass key", kind="term", aliases=[], description="Old and green.", importance=3)],
                relations=[R(source="Mara", target="Brass key", relation="finds", description="")],
                events=[V(title="Mara finds a key", description="In the sand.", when=None, importance=3,
                          evidence="THIS PHRASE IS NOT IN THE TEXT")])
        return analysis.ChapterAnalysis(
            entities=[E(name="Smugglers", kind="organization", aliases=[], description="Used the lighthouse.",
                        importance=4),
                      E(name="Mara", kind="character", aliases=[], description="Learns the secret.", importance=5)],
            relations=[R(source="Smugglers", target="The Lighthouse", relation="used", description="")],
            events=[V(title="The secret is revealed", description="Smugglers!", when=None, importance=5,
                      evidence="used by smugglers carrying French brandy")])
    if schema is quotes.QuotesOut:
        first = re.search(r"PASSAGES:\n\n\[1\]\n(.+?)\n\n", user, re.S).group(1)
        real = first.split("\n\n")[0].split(". ")[0] + "."
        return quotes.QuotesOut(quotes=[
            quotes.QuoteOut(passage=1, quote=real, note="real"),
            quotes.QuoteOut(passage=1, quote="Mara secretly loved the smugglers' captain.", note="invented"),
        ])
    if schema is study.QuizOut:
        Q = study.QuestionOut
        return study.QuizOut(title="Lighthouse quiz", questions=[
            Q(type="multiple_choice", question="Where is the lighthouse?",
              options=["South beach", "Northern cliff", "Harbour", "Island"], answer="B",
              explanation="Chapter 1 says so.", passage=1),
            Q(type="true_false", question="The key was made of brass.", options=[], answer="True",
              explanation="A small brass key.", passage=1),
            Q(type="short_answer", question="Who used the lighthouse?", options=[], answer="Smugglers.",
              explanation="The diaries say so.", passage=1),
        ])
    if schema is study.GradesOut:
        items = re.findall(r"\[(\d+)\].*?Student answer: (.*?)(?:\n\n|$)", user, re.S)
        return study.GradesOut(grades=[study.GradeOut(index=int(i), correct="smuggl" in a.lower(), feedback="ok")
                                       for i, a in items])
    if schema is study.CardsOut:
        return study.CardsOut(cards=[study.CardOut(front=f"Card {i}", back="Back", passage=1) for i in range(3)])
    if schema is book.BookProfile:
        return book.BookProfile(is_fiction=True, questions=["What is in the cellar?"])
    from app.llm.prompts import essay, translate

    if schema is essay.EssayOut:
        first = re.search(r"\[1\]\n([^.]+\.)", user).group(1)  # a real sentence from passage 1
        Ev = essay.EvidenceOut
        return essay.EssayOut(
            title="Secrets", thesis="The lighthouse hides secrets.", introduction="Open with the storm.",
            sections=[essay.SectionOut(heading="The key", point="Objects reveal the past.", evidence=[
                Ev(passage=1, quote=first, explanation="Shows it."),
                Ev(passage=1, quote="Mara flew to the moon on a dragon.", explanation="Invented."),  # must be dropped
            ])],
            counterargument="Maybe it is just a lighthouse.", conclusion="Close on the diaries.")
    if schema is translate.TranslationOut:
        items = re.findall(r"\[(\d+)\]\n(.+?)(?=\n\n\[\d+\]\n|\n\nTranslate each)", user, re.S)
        return translate.TranslationOut(paragraphs=[translate.ParagraphOut(n=int(n), text=f"FR: {t}") for n, t in items])
    raise AssertionError(f"unexpected schema {schema}")


async def fake_complete_text(system, user, **kw):
    scope = re.search(r"Scope: (.+)", user)
    return f"SUMMARY ({scope.group(1) if scope else 'chapter'}): " + ("SPOILER-SAFE" if "only read up" in user else "full")


async def fake_stream_text(system, messages, **kw):
    for word in ["The", " storm", " came", " [1]."]:
        yield word


@pytest.fixture
def fake_llm(monkeypatch):
    from app.api import chat, features
    from app.llm import client

    monkeypatch.setattr(client, "complete_json", fake_complete_json)
    monkeypatch.setattr(client, "complete_text", fake_complete_text)
    monkeypatch.setattr(client, "stream_text", fake_stream_text)
    monkeypatch.setattr(client, "llm_configured", lambda: True)
    monkeypatch.setattr(features, "llm_configured", lambda: True)


async def _wait_job(client, book_id, kind, timeout=60):
    for _ in range(int(timeout / 0.25)):
        job = (await client.get(f"/api/books/{book_id}/jobs/{kind}")).json()["job"]
        if job and job["status"] != "running":
            return job
        await asyncio.sleep(0.25)
    raise TimeoutError(kind)


async def test_features_end_to_end(test_db, fake_llm):
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60) as c:
        r = await c.post("/api/books", files={"file": ("lh.txt", BOOK.format(c1=C1, c2=C2, c3=C3).encode(), "text/plain")})
        book_id = r.json()["id"]
        assert (await _wait_ready(c, book_id))["status"] == "ready"
        chapters = (await c.get(f"/api/books/{book_id}/chapters")).json()
        ch1, ch3 = chapters[0]["id"], chapters[2]["id"]

        # --- analysis -> explorer & timeline
        assert (await c.post(f"/api/books/{book_id}/analysis")).status_code == 202
        job = await _wait_job(c, book_id, "analysis")
        assert job["status"] == "done", job
        ex = (await c.get(f"/api/books/{book_id}/entities")).json()
        names = {e["name"] for e in ex["entities"]}
        assert names == {"Mara", "The Lighthouse", "Brass key", "Smugglers"}
        mara = next(e for e in ex["entities"] if e["name"] == "Mara")
        assert [d["chapter"] for d in mara["details"]] == [1, 2, 3] and mara["first_chapter"] == 1
        assert len(ex["relations"]) == 3

        guarded = (await c.get(f"/api/books/{book_id}/entities", params={"max_chapter": 1})).json()
        assert {e["name"] for e in guarded["entities"]} == {"Mara", "The Lighthouse"}
        assert [d["chapter"] for d in guarded["entities"][0]["details"]] == [1]  # later details hidden
        assert len(guarded["relations"]) == 1

        mentions = (await c.get(f"/api/entities/{mara['id']}/mentions", params={"max_chapter": 2})).json()
        assert mentions and all(m["chapter_position"] <= 2 for m in mentions)

        tl = (await c.get(f"/api/books/{book_id}/timeline")).json()["events"]
        assert [e["title"] for e in tl] == ["The storm arrives", "Mara finds a key", "The secret is revealed"]
        ev3 = tl[2]
        ch3_text = (await c.get(f"/api/chapters/{ev3['chapter_id']}")).json()["text"]
        assert "smugglers" in ch3_text[ev3["char_start"]:ev3["char_end"]]  # evidence located the right passage
        assert len((await c.get(f"/api/books/{book_id}/timeline", params={"max_chapter": 2})).json()["events"]) == 2

        # --- quote finder: real quote kept (with exact book text), invented one dropped
        q = (await c.post(f"/api/books/{book_id}/quotes", json={"topic": "smugglers and brandy"})).json()
        assert len(q["quotes"]) == 1 and q["quotes"][0]["note"] == "real"
        qq = q["quotes"][0]
        text = (await c.get(f"/api/chapters/{qq['chapter_id']}")).json()["text"]
        assert text[qq["char_start"]:qq["char_end"]] == qq["quote"]

        # --- quiz
        quiz = (await c.post(f"/api/books/{book_id}/quizzes", json={"num_questions": 3})).json()
        assert len(quiz["questions"]) == 3 and "answer" not in quiz["questions"][0]
        res = (await c.post(f"/api/quizzes/{quiz['id']}/submit",
                            json={"answers": ["Northern cliff", "False", "Some smugglers"]})).json()
        assert [r["correct"] for r in res["results"]] == [True, False, True]
        assert res["score"] == 2 and res["results"][0]["source"]["chapter_position"] >= 1
        assert (await c.get(f"/api/books/{book_id}/quizzes")).json()[0]["attempts"] == 1

        # Spoiler guard on saved quizzes: a chapter-3 quiz is hidden from a reader at chapter 2.
        q3 = (await c.post(f"/api/books/{book_id}/quizzes", json={"num_questions": 3, "chapter_id": ch3})).json()
        visible = {q["id"] for q in (await c.get(f"/api/books/{book_id}/quizzes", params={"max_chapter": 2})).json()}
        assert q3["id"] not in visible
        assert q3["id"] in {q["id"] for q in (await c.get(f"/api/books/{book_id}/quizzes", params={"max_chapter": 3})).json()}
        assert (await c.get(f"/api/quizzes/{q3['id']}", params={"max_chapter": 2})).status_code == 403

        # --- flashcards
        cards = (await c.post(f"/api/books/{book_id}/flashcards", json={"count": 3})).json()
        assert len(cards) == 3
        deck = (await c.get(f"/api/books/{book_id}/flashcards", params={"due_only": True})).json()
        assert deck["due"] == 3
        reviewed = (await c.post(f"/api/flashcards/{cards[0]['id']}/review", json={"grade": "good"})).json()
        assert reviewed["interval_days"] == 1 and reviewed["repetitions"] == 1
        assert (await c.get(f"/api/books/{book_id}/flashcards", params={"due_only": True})).json()["due"] == 2

        # --- summaries: chapter (cached), spoiler-blocked chapter, whole book with spoiler guard
        s1 = (await c.post(f"/api/books/{book_id}/summaries", json={"chapter_id": ch1, "length": "short"})).json()
        assert s1["status"] == "done" and s1["summary"]["content"].startswith("SUMMARY")
        again = (await c.post(f"/api/books/{book_id}/summaries", json={"chapter_id": ch1, "length": "short"})).json()
        assert again["summary"]["id"] == s1["summary"]["id"]  # served from cache
        blocked = await c.post(f"/api/books/{book_id}/summaries",
                               json={"chapter_id": ch3, "length": "short", "max_chapter": 1})
        assert blocked.status_code == 403
        sb = (await c.post(f"/api/books/{book_id}/summaries", json={"length": "medium", "max_chapter": 2})).json()
        assert sb["status"] == "running"
        assert (await _wait_job(c, book_id, sb["job"]["kind"]))["status"] == "done"
        got = (await c.get(f"/api/books/{book_id}/summaries", params={"length": "medium", "max_chapter": 2})).json()
        assert "chapter 2" in got["summary"]["content"] and "SPOILER-SAFE" in got["summary"]["content"]
        full = (await c.get(f"/api/books/{book_id}/summaries", params={"length": "medium", "max_chapter": 3})).json()
        assert full["status"] == "missing"  # max_chapter=3 == whole book: different cache entry

        # --- notes
        n1 = (await c.post(f"/api/books/{book_id}/notes", json={
            "kind": "quote", "content": qq["quote"], "tags": ["#Theme", "theme", "secret"],
            "location": {"chapter_title": qq["chapter_title"], "page": qq["page"]}})).json()
        assert n1["tags"] == ["theme", "secret"]
        await c.post(f"/api/books/{book_id}/notes", json={"kind": "note", "content": "My own thought"})
        listing = (await c.get(f"/api/books/{book_id}/notes", params={"tag": "secret"})).json()
        assert len(listing["notes"]) == 1 and listing["tags"] == ["secret", "theme"]
        upd = (await c.patch(f"/api/notes/{n1['id']}", json={"tags": ["final"]})).json()
        assert upd["tags"] == ["final"]
        md = await c.get(f"/api/books/{book_id}/notes/export", params={"format": "md"})
        assert md.status_code == 200 and "My own thought" in md.text and "attachment" in md.headers["content-disposition"]
        pdf = await c.get(f"/api/books/{book_id}/notes/export", params={"format": "pdf"})
        assert pdf.content.startswith(b"%PDF")

        # --- chat with spoiler guard: retrieved sources never exceed the limit
        resp = await c.post(f"/api/books/{book_id}/chat",
                            json={"message": "What did the diaries reveal about smugglers?", "spoiler_chapter": 1})
        events = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
        sources = next(e["sources"] for e in events if "sources" in e)
        assert sources and all(s["chapter_position"] <= 1 for s in sources)
        assert any("message_id" in e for e in events)

        # --- resend: replaces the question and everything after it instead of appending
        conv = next(e for e in events if "user_message_id" in e)
        await c.post(f"/api/books/{book_id}/chat", json={"message": "A follow-up", "conversation_id": conv["id"]})
        before = (await c.get(f"/api/conversations/{conv['id']}")).json()["messages"]
        assert [m["role"] for m in before] == ["user", "assistant", "user", "assistant"]
        await c.post(f"/api/books/{book_id}/chat", json={
            "message": "Edited question", "conversation_id": conv["id"], "resend_from": conv["user_message_id"]})
        after = (await c.get(f"/api/conversations/{conv['id']}")).json()["messages"]
        assert [(m["role"], m["content"]) for m in after][0] == ("user", "Edited question") and len(after) == 2
        bad = await c.post(f"/api/books/{book_id}/chat", json={
            "message": "x", "conversation_id": conv["id"], "resend_from": after[1]["id"]})  # an answer, not a question
        assert bad.status_code == 404

        # --- cascade: deleting the book removes all feature data
        assert (await c.delete(f"/api/books/{book_id}")).status_code == 204
        assert (await c.get(f"/api/notes/{n1['id']}")).status_code in (404, 405)
        assert (await c.get(f"/api/quizzes/{quiz['id']}")).status_code == 404
