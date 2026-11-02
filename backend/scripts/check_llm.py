"""Check that the configured AI model is ready (e.g. Ollama running and the model pulled).

    python scripts/check_llm.py          # exit code 0 = ready, 1 = not ready

The start scripts run this as a warning only: books can still be uploaded and read
without a model; chat and AI features need it.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm.providers import get_provider  # noqa: E402


async def main() -> int:
    p = get_provider()
    status = await p.check()
    await p.aclose()
    if status.ok:
        print(f"AI model ready: {status.message}")
        return 0
    print(f"\n[WARNING] AI model not ready (LLM_PROVIDER={p.name}, LLM_MODEL={p.model}):")
    print(f"  -> {status.message}")
    print("  The app will start anyway; chat and AI features will work once this is fixed.\n")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
