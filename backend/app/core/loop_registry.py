"""Holds a reference to the main asyncio event loop (the one uvicorn runs the
FastAPI app on), set once at startup. Background threads (job execution,
scheduled automations) use this to safely schedule coroutines back onto the
loop that WebSocket subscribers are listening on via
asyncio.run_coroutine_threadsafe.
"""
from __future__ import annotations

import asyncio

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def get_main_loop() -> asyncio.AbstractEventLoop:
    if _main_loop is None:
        raise RuntimeError("Main event loop has not been set yet — app startup has not completed.")
    return _main_loop
