"""Notes & highlights export (Markdown, PDF)."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from app.db.models import Book, Note

# Unicode TrueType fonts commonly present per OS; PDF falls back to a Latin-1 core font.
_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\ariali.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
     "/System/Library/Fonts/Supplemental/Arial Italic.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/dejavu/DejaVuSans-Oblique.ttf"),
]


def _count(notes: list[Note]) -> str:
    return f"{len(notes)} note{'' if len(notes) == 1 else 's'}"


def location_label(note: Note) -> str:
    loc = note.location or {}
    parts = [loc.get("chapter_title"), f"p. {loc['page']}" if loc.get("page") else None]
    return " · ".join(p for p in parts if p)


def _strip_citations(text: str) -> str:
    return re.sub(r"\s?\[\d+(?:\s*[,–-]\s*\d+)*\]", "", text)


def to_markdown(book: Book, notes: list[Note]) -> str:
    lines = [f"# Notes — {book.title}", ""]
    if book.author:
        lines += [f"*{book.author}*", ""]
    lines += [f"Exported {datetime.now().strftime('%Y-%m-%d %H:%M')} · {_count(notes)}", ""]
    for n in notes:
        title = n.title or {"quote": "Quote", "passage": "Highlight", "answer": "Answer"}.get(n.kind, "Note")
        lines += [f"## {title}", ""]
        meta = [location_label(n), ", ".join(f"#{t}" for t in n.tags or [])]
        meta = [m for m in meta if m]
        if meta:
            lines += [f"_{' · '.join(meta)}_", ""]
        body = _strip_citations(n.content).strip()
        if n.kind in ("quote", "passage"):
            body = "\n".join(f"> {line}" if line else ">" for line in body.split("\n"))
        lines += [body, ""]
        if n.comment:
            lines += [n.comment, ""]
    return "\n".join(lines)


def to_pdf(book: Book, notes: list[Note]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)
    family, unicode_ok = "helvetica", False
    for regular, bold, italic in _FONT_CANDIDATES:
        if Path(regular).exists():
            pdf.add_font("body", "", regular)
            pdf.add_font("body", "B", bold if Path(bold).exists() else regular)
            pdf.add_font("body", "I", italic if Path(italic).exists() else regular)
            family, unicode_ok = "body", True
            break

    def txt(s: str) -> str:
        if unicode_ok:
            return s
        s = (s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
              .replace("—", "-").replace("–", "-").replace("…", "..."))
        return s.encode("latin-1", "replace").decode("latin-1")

    width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.add_page()
    pdf.set_font(family, "B", 20)
    pdf.multi_cell(width, 10, txt(book.title))
    pdf.set_font(family, "I", 11)
    sub = " · ".join(x for x in [book.author, _count(notes), datetime.now().strftime("%Y-%m-%d")] if x)
    pdf.multi_cell(width, 6, txt(sub))
    pdf.ln(4)

    for n in notes:
        title = n.title or {"quote": "Quote", "passage": "Highlight", "answer": "Answer"}.get(n.kind, "Note")
        pdf.set_font(family, "B", 13)
        pdf.multi_cell(width, 7, txt(title))
        meta = " · ".join(m for m in [location_label(n), ", ".join(f"#{t}" for t in n.tags or [])] if m)
        if meta:
            pdf.set_font(family, "I", 9)
            pdf.set_text_color(110, 110, 110)
            pdf.multi_cell(width, 5, txt(meta))
            pdf.set_text_color(0, 0, 0)
        body = re.sub(r"[*_#>`]", "", _strip_citations(n.content)).strip()
        pdf.set_font(family, "I" if n.kind in ("quote", "passage") else "", 11)
        pdf.ln(1)
        pdf.multi_cell(width, 6, txt(body))
        if n.comment:
            pdf.set_font(family, "", 11)
            pdf.ln(1)
            pdf.multi_cell(width, 6, txt(n.comment))
        pdf.ln(3)
        pdf.set_draw_color(220, 220, 220)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(4)
    return bytes(pdf.output())
