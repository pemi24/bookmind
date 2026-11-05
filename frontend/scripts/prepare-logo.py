"""Prepares BookMind's logo symbol (the brain rising from an open book) for the site, from the original
artwork: brand/bookmind-logo-original.webp (transparent background, "BOOK MIND" lettering underneath).

    python scripts/prepare-logo.py        (needs Pillow; the backend's virtualenv has it)

Writes public/brand/symbol-light.png (the symbol exactly as drawn: purple fading to navy) and
symbol-dark.png (the same shape, lightened to purple fading to lavender so it reads on dark
backgrounds and the green sign-in panel). The lettering is left out: the site sets "Book Mind" in its
own font beside the symbol. Run scripts/render-brand-images.mjs afterwards for the favicon, app
icons and sharing image.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "brand" / "bookmind-logo-original.webp"
OUT = ROOT / "public" / "brand"
WIDTH = 640  # output width (sharp at 2× for the largest size the site shows it)

# Dark mode: the gradient's top and bottom colours (the original runs from purple to navy, top to bottom).
DARK_TOP = (0xB9, 0xA3, 0xFF)
DARK_BOTTOM = (0xD6, 0xCF, 0xF2)


def symbol_box(img: Image.Image) -> tuple[int, int, int, int]:
    """The symbol: the first block of non-empty rows (the lettering is the block below it)."""
    alpha = img.getchannel("A").point(lambda a: 255 if a > 8 else 0)
    first = None
    for y in range(img.height):
        has_ink = alpha.crop((0, y, img.width, y + 1)).getbbox() is not None
        if has_ink and first is None:
            first = y
        elif not has_ink and first is not None:
            return alpha.crop((0, first, img.width, y)).getbbox()[0], first, alpha.crop((0, first, img.width, y)).getbbox()[2], y
    raise SystemExit("No symbol found in the artwork.")


def lighten(img: Image.Image) -> Image.Image:
    """Same shape and transparency, the vertical gradient repainted from DARK_TOP to DARK_BOTTOM."""
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        t = y / max(1, out.height - 1)
        colour = tuple(round(a + (b - a) * t) for a, b in zip(DARK_TOP, DARK_BOTTOM))
        for x in range(out.width):
            alpha = px[x, y][3]
            if alpha:
                px[x, y] = (*colour, alpha)
    return out


def main() -> None:
    art = Image.open(SOURCE).convert("RGBA")
    symbol = art.crop(symbol_box(art))
    symbol = symbol.resize((WIDTH, round(symbol.height * WIDTH / symbol.width)), Image.LANCZOS)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, img in (("light", symbol), ("dark", lighten(symbol))):
        img.save(OUT / f"symbol-{name}.png", optimize=True)
        print(f"  public/brand/symbol-{name}.png ({img.width}×{img.height})")


if __name__ == "__main__":
    main()
