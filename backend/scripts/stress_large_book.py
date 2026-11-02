"""Large-book check: index a generated 1,000-page PDF and confirm the API stays responsive.

    python scripts/stress_large_book.py                 # against http://127.0.0.1:8000
    python scripts/stress_large_book.py --pages 1500 --keep

Builds a PDF from the public-domain sample texts (repeated, 60 chapters with an outline),
uploads it to the RUNNING backend, then polls an API endpoint every second while it
indexes. Reports total indexing time and the slowest API response seen meanwhile — the
UI uses these same endpoints, so a slow response here means a frozen UI. The test book is
deleted at the end unless --keep is given.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pymupdf

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
CHARS_PER_PAGE = 2200


def build_pdf(pages: int, chapters: int, path: Path) -> None:
    def body(name: str) -> str:
        # Only the book text: repeated Project Gutenberg license blocks would (correctly) be stripped
        # by the cleaner and leave most of the test book empty.
        raw = (SAMPLES / name).read_text(encoding="utf-8")
        start = raw.find("*** START OF")
        end = raw.find("*** END OF")
        return raw[raw.find("\n", start) + 1 if start != -1 else 0:end if end != -1 else None]

    text = "\n\n".join(body(n) for n in ("alice-in-wonderland.txt", "the-art-of-war.txt"))
    paras = []
    for p in text.split("\n\n"):
        words = p.split()
        # Split very long paragraphs so each page's text fits its box (an overflowing box stays empty).
        for k in range(0, len(words), 150):
            if len(words[k:k + 150]) > 8:
                paras.append(" ".join(words[k:k + 150]))
    doc = pymupdf.open()
    toc, per_chapter, i = [], max(1, pages // chapters), 0
    for page_no in range(1, pages + 1):
        page = doc.new_page()
        body, size = [], 0
        if (page_no - 1) % per_chapter == 0 and len(toc) < chapters:
            title = f"Chapter {len(toc) + 1}"
            toc.append([1, title, page_no])
            body.append(title)
        while size < CHARS_PER_PAGE:
            p = paras[i % len(paras)]
            i += 1
            body.append(p)
            size += len(p)
        box = pymupdf.Rect(50, 50, 545, 790)
        if page.insert_textbox(box, "\n\n".join(body), fontsize=8) < 0:  # still too long: smaller type
            page.insert_textbox(box, "\n\n".join(body), fontsize=6)
        page.insert_text((290, 815), str(page_no), fontsize=8)  # page number footer (should be cleaned)
    doc.set_toc(toc)
    doc.save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--pages", type=int, default=1000)
    ap.add_argument("--chapters", type=int, default=60)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--timeout", type=int, default=3600, help="seconds to wait for indexing")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / f"stress-{args.pages}-pages.pdf"
        t = time.time()
        build_pdf(args.pages, args.chapters, pdf)
        print(f"Built {pdf.name}: {args.pages} pages, {pdf.stat().st_size / 1e6:.1f} MB in {time.time() - t:.0f}s")

        api = httpx.Client(base_url=args.url, timeout=120)
        with pdf.open("rb") as f:
            r = api.post("/api/books", files={"file": (pdf.name, f, "application/pdf")})
        r.raise_for_status()
        book_id = r.json()["id"]

    print(f"Uploaded as book {book_id}; indexing… (polling the API every second)")
    ok = False
    try:
        ok = run_checks(api, book_id, args)
    finally:
        if not args.keep:
            api.delete(f"/api/books/{book_id}", timeout=300)
            print("  (test book deleted)")
    sys.exit(0 if ok else 1)


def run_checks(api: httpx.Client, book_id: int, args) -> bool:
    latencies, errors, start, last_msg = [], 0, time.time(), ""
    status = {}
    while time.time() - start < args.timeout:
        t = time.time()
        try:
            status = api.get(f"/api/books/{book_id}").json()
            api.get("/api/books")  # what the library page polls
        except httpx.TransportError as e:  # count it as an unresponsive moment and keep going
            errors += 1
            print(f"  [{time.time() - start:6.0f}s] API request failed: {e!r}")
            time.sleep(2)
            continue
        latencies.append(time.time() - t)
        msg = f"{status['progress'] * 100:5.1f}% {status['status_message']}"
        if msg != last_msg:
            print(f"  [{time.time() - start:6.0f}s] {msg}   (API {latencies[-1] * 1000:.0f} ms)")
            last_msg = msg
        if status["status"] in ("ready", "failed"):
            break
        time.sleep(1)
    elapsed = time.time() - start

    print("\nResult")
    print(f"  status:            {status.get('status')} {status.get('error') or ''}")
    print(f"  chapters / pages:  {status.get('chapter_count')} / {status.get('page_count')}")
    print(f"  indexing time:     {elapsed / 60:.1f} min")
    print(f"  API latency while indexing: median {statistics.median(latencies) * 1000:.0f} ms, "
          f"p95 {sorted(latencies)[int(len(latencies) * 0.95)] * 1000:.0f} ms, max {max(latencies) * 1000:.0f} ms "
          f"({len(latencies)} samples, {errors} failed requests)")
    if status.get("status") == "ready":
        t = time.time()
        hits = api.get(f"/api/books/{book_id}/retrieve", params={"q": "What did the Queen of Hearts shout?"}).json()
        print(f"  search after indexing: {len(hits)} passages in {(time.time() - t) * 1000:.0f} ms")
    return status.get("status") == "ready" and not errors


if __name__ == "__main__":
    main()
