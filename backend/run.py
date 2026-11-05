"""Start the API server:  python run.py  [--reload]

On Windows, psycopg's async driver cannot use the default ProactorEventLoop, so we run
uvicorn on a SelectorEventLoop explicitly (a plain `uvicorn app.main:app` can fail there).
With HTTPS=true it also serves the app over HTTPS on HTTPS_PORT (see app/certs.py).
"""
from __future__ import annotations

import asyncio
import contextlib
import queue
import signal
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


class _Server(uvicorn.Server):
    """A uvicorn server that leaves Ctrl+C to serve_all(), which stops every listener together."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


async def serve_all(servers: list[uvicorn.Server]) -> None:
    def stop(sig, frame) -> None:
        for server in servers:
            if server.should_exit and sig == signal.SIGINT:
                server.force_exit = True  # second Ctrl+C: don't wait for open connections
            server.should_exit = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    tasks = [asyncio.create_task(server.serve()) for server in servers]
    try:
        # If one listener stops (e.g. its port is taken), stop the others too.
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for server in servers:
            server.should_exit = True
        await asyncio.gather(*tasks, return_exceptions=True)
        for task in done:
            task.result()  # re-raise a startup failure (SystemExit) after the others shut down
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main() -> None:
    # Before uvicorn and the app set up logging, so every log handler writes through these.
    sys.stdout, sys.stderr = BackgroundConsole(sys.stdout), BackgroundConsole(sys.stderr)
    s = get_settings()
    servers = [_Server(uvicorn.Config("app.main:app", host=s.host, port=s.port, log_level="info"))]
    if s.https:
        # Same app on a second, encrypted port; the plain http address keeps working.
        from app import certs

        paths = certs.resolve(s)
        servers.append(_Server(uvicorn.Config(
            "app.main:app", host=s.host, port=s.https_port, log_level="info", lifespan="off",
            ssl_certfile=str(paths.certfile), ssl_keyfile=str(paths.keyfile))))
    if sys.platform == "win32":
        asyncio.run(serve_all(servers), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(serve_all(servers))


if __name__ == "__main__":
    main()
