"""
In-process pub/sub used to fan out live job events to WebSocket subscribers.
Every event is also persisted (JobEvent rows) so a client that connects after
the fact (or reconnects) can replay history via GET /api/jobs/{id}/events,
then continue receiving live events over the WebSocket.

Note for test authors: publish_threadsafe() schedules a coroutine onto the
event loop that was live when the app's `lifespan` started (see
app/core/loop_registry.py). In tests that call orchestrator/executor code
directly without going through a live `TestClient` request, or after that
loop has been torn down, the scheduled publish is silently dropped — this
only affects live WebSocket delivery of that one event, never correctness of
the job/DB state, which is always persisted first. It's a test-harness
artifact, not a production behavior (uvicorn's loop lives for the whole
process), so it's filtered in pytest.ini rather than treated as a failure.
"""
from __future__ import annotations

import asyncio
import itertools
from collections import defaultdict
from typing import AsyncIterator

_counter = itertools.count(1)


class StreamManager:
    def __init__(self):
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers[job_id].add(q)
        return q

    async def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers[job_id].discard(q)

    async def publish(self, job_id: str, event: dict) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(job_id, ()))
        for q in queues:
            await q.put(event)

    def publish_threadsafe(self, loop: asyncio.AbstractEventLoop, job_id: str, event: dict) -> None:
        asyncio.run_coroutine_threadsafe(self.publish(job_id, event), loop)


stream_manager = StreamManager()


def next_sequence() -> int:
    return next(_counter)
