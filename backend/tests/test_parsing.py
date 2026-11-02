from pathlib import Path

import pytest

from app.ingestion.chapters import detect_chapters, is_heading
from app.ingestion.cleaning import clean_document
from app.ingestion.parsers import ParseError, parse_file

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def _pipeline(path: Path):
    doc = clean_document(parse_file(path))
    return doc, detect_chapters(doc)


def test_gutenberg_txt_chapters_and_boilerplate():
    doc, chapters = _pipeline(SAMPLES / "alice-in-wonderland.txt")
    assert doc.title and "Alice" in doc.title
    assert doc.author == "Lewis Carroll"
    titles = [c.title for c in chapters]
    assert len(chapters) == 12, titles
    assert titles[0].startswith("CHAPTER I") and "Rabbit-Hole" in titles[0]
    assert "Alice’s Evidence" in titles[-1]
    full = "\n".join(c.text for c in chapters)
    assert "Project Gutenberg License" not in full  # license stripped
    assert "Down the Rabbit-Hole" in chapters[0].text
    # Hard-wrapped lines were unwrapped into paragraphs.
    assert "Alice was beginning to get very tired of sitting by her sister" in chapters[0].text


def test_epub_chapters():
    doc, chapters = _pipeline(SAMPLES / "alice-in-wonderland.epub")
    assert doc.pages_estimated
    assert sum("CHAPTER" in c.title.upper() for c in chapters) >= 12
    assert all(c.page_map for c in chapters)


def test_markdown_headings(tmp_path):
    body = "Some words here that make a long enough paragraph. " * 20
    p = tmp_path / "notes.md"
    p.write_text(f"# Intro\n\n{body}\n\n# Second part\n\n{body}\n\n# Third\n\n{body}\n", encoding="utf-8")
    _, chapters = _pipeline(p)
    assert [c.title for c in chapters] == ["Intro", "Second part", "Third"]


def test_docx_headings(tmp_path):
    import docx

    d = docx.Document()
    body = "A sentence of body text for this section. " * 15
    for t in ("Alpha", "Beta", "Gamma"):
        d.add_heading(t, level=1)
        d.add_paragraph(body)
    path = tmp_path / "doc.docx"
    d.save(path)
    _, chapters = _pipeline(path)
    assert [c.title for c in chapters] == ["Alpha", "Beta", "Gamma"]


def test_pdf_headers_footers_and_page_numbers(tmp_path):
    import pymupdf

    animals = ["whales", "otters", "herons", "seals", "crabs", "gulls", "eels", "terns"]
    pdf = pymupdf.open()
    for i, animal in enumerate(animals):
        page = pdf.new_page()
        page.insert_text((72, 40), "THE RUNNING HEADER")
        page.insert_text((72, 100), f"This page describes the {animal} seen from the deck of our ship.")
        page.insert_text((300, 800), str(i + 1))
    path = tmp_path / "book.pdf"
    pdf.save(path)
    doc, chapters = _pipeline(path)
    full = "\n".join(c.text for c in chapters)
    assert "RUNNING HEADER" not in full
    assert "whales" in full
    assert all(not line.strip().isdigit() for line in full.split("\n\n"))
    assert doc.pages[3].number == 4


def test_unsupported_and_binary(tmp_path):
    bad = tmp_path / "x.xyz"
    bad.write_text("hi")
    with pytest.raises(ParseError):
        parse_file(bad)
    binary = tmp_path / "y.txt"
    binary.write_bytes(b"\x00\x01\x02" * 2000)
    with pytest.raises(ParseError):
        parse_file(binary)


@pytest.mark.parametrize("text,expected", [
    ("CHAPTER I.", True), ("Chapter 12: The Return", True), ("BOOK TWO", True),
    ("I. LAYING PLANS", True), ("Prologue", True),
    ("Chapter and verse were quoted at length by the vicar during the long service.", False),
    ("It was a dark night.", False),
])
def test_heading_regex(text, expected):
    assert is_heading(text) is expected
