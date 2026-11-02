from app.ingestion.chunking import chunk_text, estimate_tokens, page_at
from app.retrieval.hybrid import _keyword_tsquery, reciprocal_rank_fusion


def _book_text(paragraphs: int = 60) -> str:
    para = " ".join(f"Sentence number {i} tells part of the story about the river and the mill." for i in range(8))
    return "\n\n".join(f"Paragraph {p}. {para}" for p in range(paragraphs))


def test_chunks_are_exact_slices_and_sized():
    text = _book_text()
    chunks = chunk_text(text, target_tokens=300, max_tokens=420, overlap_tokens=50)
    assert len(chunks) > 3
    for c in chunks:
        assert text[c.char_start:c.char_end] == c.text
        assert c.token_count <= 420 * 1.25
    # Coverage: every character of the text is in some chunk.
    assert chunks[0].char_start == 0
    assert chunks[-1].char_end == len(text)
    for a, b in zip(chunks, chunks[1:]):
        assert b.char_start <= a.char_end  # overlap or adjacency, never a gap


def test_overlap_exists():
    chunks = chunk_text(_book_text(), target_tokens=300, max_tokens=420, overlap_tokens=60)
    overlaps = [a.char_end - b.char_start for a, b in zip(chunks, chunks[1:])]
    assert all(o > 0 for o in overlaps)


def test_prefers_paragraph_boundaries():
    chunks = chunk_text(_book_text(), target_tokens=300, max_tokens=600, overlap_tokens=0)
    ends_at_para = sum(c.text.rstrip().endswith("mill.") for c in chunks[:-1])
    assert ends_at_para >= len(chunks[:-1]) * 0.8


def test_long_unbroken_text_is_split():
    text = "word " * 5000
    chunks = chunk_text(text, target_tokens=200, max_tokens=300, overlap_tokens=20)
    assert len(chunks) > 5
    assert max(c.token_count for c in chunks) <= 300 * 1.25


def test_empty_text():
    assert chunk_text("   ") == []


def test_page_at():
    pm = [[0, 5], [100, 6], [250, 7]]
    assert page_at(pm, 0) == 5
    assert page_at(pm, 99) == 5
    assert page_at(pm, 100) == 6
    assert page_at(pm, 9999) == 7
    assert page_at([], 3) is None


def test_estimate_tokens():
    assert estimate_tokens("a" * 400) == 100


def test_rrf_prefers_items_ranked_by_both():
    fused = reciprocal_rank_fusion([[1, 2, 3], [3, 1, 4]], k=60)
    ranked = sorted(fused, key=fused.get, reverse=True)
    assert ranked[0] == 1 and ranked[1] == 3
    assert set(fused) == {1, 2, 3, 4}


def test_keyword_query_sanitized():
    assert _keyword_tsquery("Who's the Queen?! (a) & | !") == "who | the | queen"
    assert _keyword_tsquery("?!") is None
