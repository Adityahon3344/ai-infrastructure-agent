from __future__ import annotations

import asyncio

from app.core.loop_registry import get_main_loop


def get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Returns the main FastAPI/uvicorn event loop so background execution
    threads can publish stream events that WebSocket clients (subscribed on
    that same loop) will actually receive."""
    return get_main_loop()
