"""Start the API server:  python run.py  [--reload]

On Windows, psycopg's async driver cannot use the default ProactorEventLoop, so we run
uvicorn on a SelectorEventLoop explicitly (a plain `uvicorn app.main:app` can fail there).
"""
from __future__ import annotations

import asyncio
import sys

import uvicorn

from app.config import get_settings


def main() -> None:
    s = get_settings()
    config = uvicorn.Config("app.main:app", host=s.host, port=s.port, log_level="info")
    server = uvicorn.Server(config)
    if sys.platform == "win32":
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()
