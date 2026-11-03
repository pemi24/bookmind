"""Start the API server:  python run.py  [--reload]

On Windows, psycopg's async driver cannot use the default ProactorEventLoop, so we run
uvicorn on a SelectorEventLoop explicitly (a plain `uvicorn app.main:app` can fail there).
"""
from __future__ import annotations

import asyncio
import queue
import sys
import threading

import uvicorn

from app.config import get_settings


class BackgroundConsole:
    """Writes to the console from a background thread, so the server never waits on the console.

    A Windows console pauses any program writing to it while text is selected in it ("QuickEdit":
    one stray click in the window). Writing logs directly would then freeze every request until
    someone presses Esc; with this, only the log output waits.
    """

    def __init__(self, stream) -> None:
        self._stream = stream
        self._queue: queue.SimpleQueue[str | None] = queue.SimpleQueue()
        threading.Thread(target=self._pump, name=f"console-{id(stream)}", daemon=True).start()

    def _pump(self) -> None:
        while (text := self._queue.get()) is not None:
            try:
                self._stream.write(text)
                if self._queue.empty():
                    self._stream.flush()
            except (OSError, ValueError):
                pass  # console closed

    def write(self, text: str) -> int:
        self._queue.put(text)
        return len(text)

    def flush(self) -> None:
        pass  # the pump flushes once it has caught up

    def __getattr__(self, name: str):  # isatty, encoding, fileno... behave like the real console
        return getattr(self._stream, name)


def main() -> None:
    # Before uvicorn and the app set up logging, so every log handler writes through these.
    sys.stdout, sys.stderr = BackgroundConsole(sys.stdout), BackgroundConsole(sys.stderr)
    s = get_settings()
    config = uvicorn.Config("app.main:app", host=s.host, port=s.port, log_level="info")
    server = uvicorn.Server(config)
    if sys.platform == "win32":
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()
