"""Download Piper voices (local text-to-speech) into PIPER_VOICES_DIR (backend/data/voices).

    python scripts/download_voices.py                    # the voices in PIPER_VOICES (.env)
    python scripts/download_voices.py en_GB-cori-high    # these voices instead
    python scripts/download_voices.py --list             # every English and French voice, with sizes
    python scripts/download_voices.py --list de          # voices for another language

Voices come from https://huggingface.co/rhasspy/piper-voices. Each is a .onnx model (about 60 MB
for "medium", 110 MB for "high") plus a small .onnx.json config. Files already downloaded are
skipped. To offer a voice in BookMind, list it in PIPER_VOICES and restart.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
VOICE = re.compile(r"^(?P<lang>[a-z]{2,3})_(?P<region>[A-Z]{2})-(?P<name>[\w-]+)-(?P<quality>x_low|low|medium|high)$")


def _get(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "BookMind"}), timeout=60)


def _download(url: str, dest: Path) -> None:
    part = dest.with_name(dest.name + ".part")
    with _get(url) as r, open(part, "wb") as f:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {dest.name}: {done * 100 // total}% of {total // 2**20} MB", end="", flush=True)
    part.replace(dest)  # only a complete file gets the real name
    print()


def download(voice: str, folder: Path) -> bool:
    m = VOICE.match(voice)
    if not m:
        print(f"'{voice}' isn't a voice name like en_US-lessac-medium (see --list).")
        return False
    lang = f"{m['lang']}_{m['region']}"
    for ext in (".onnx.json", ".onnx"):
        dest = folder / f"{voice}{ext}"
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  {dest.name}: already downloaded")
            continue
        try:
            _download(f"{BASE}/{m['lang']}/{lang}/{m['name']}/{m['quality']}/{voice}{ext}?download=true", dest)
        except Exception as e:  # noqa: BLE001 - report and carry on with the other voices
            print(f"  Couldn't download {voice}{ext}: {e}")
            return False
    return True


def list_voices(langs: list[str]) -> None:
    with _get(f"{BASE}/voices.json?download=true") as r:
        catalog = json.load(r)
    for key, v in sorted(catalog.items()):
        if v["language"]["family"] not in langs:
            continue
        size = sum(f["size_bytes"] for name, f in v["files"].items() if name.endswith(".onnx")) // 2**20
        lang = v["language"]
        print(f"{key:45} {lang['name_english']} ({lang['country_english']}), {v['quality']}, {size} MB")


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["--list"]:
        list_voices(args[1:] or ["en", "fr"])
        return 0
    settings = get_settings()
    voices = args or [v.strip() for v in settings.piper_voices.split(",") if v.strip()]
    if not voices:
        print("No voices to download: list some in PIPER_VOICES in backend/.env, or name them here.")
        return 1
    folder = settings.piper_voices_dir
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {len(voices)} voice(s) into {folder}")
    failed = [v for v in voices if not download(v, folder)]
    if failed:
        print(f"Not downloaded: {', '.join(failed)}")
        return 1
    print("Done. Restart BookMind to use them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
