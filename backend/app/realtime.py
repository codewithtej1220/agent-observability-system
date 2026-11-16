"""Server-sent events: push new calls, alerts and agent runs to open dashboards.

In-process pub/sub keyed by workspace. Publishing is safe from any thread
(sync route handlers run in a thread pool). Slow consumers drop events
rather than block publishers; the dashboard re-fetches on reconnect, so a
dropped event only delays an update.

Scale-out note: with several API processes, replace the broker with a
shared bus (e.g. Redis pub/sub); the endpoint and event shapes stay the same.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, AsyncIterator, Dict, Optional, Set

log = logging.getLogger(__name__)
HEARTBEAT_S = 20
QUEUE_SIZE = 200


class Broker:
    def __init__(self) -> None:
        self._subs: Dict[int, Set[asyncio.Queue]] = defaultdict(set)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribers(self, ws_id: int) -> int:
        return len(self._subs.get(ws_id, ()))

    def publish(self, ws_id: int, event: str, data: Dict[str, Any]) -> None:
        """Fire-and-forget; callable from the event loop or any worker thread."""
        if not self._subs.get(ws_id) or self._loop is None:
            return
        msg = (event, data)

        def deliver() -> None:
            for q in list(self._subs.get(ws_id, ())):
                try:
                    q.put_nowait(msg)
                except asyncio.QueueFull:
                    pass  # slow client: it re-syncs when it reconnects

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            deliver()
        else:
            try:
                self._loop.call_soon_threadsafe(deliver)
            except RuntimeError:  # loop closed (shutdown)
                pass

    async def stream(self, ws_id: int) -> AsyncIterator[bytes]:
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subs[ws_id].add(q)
        try:
            yield b": connected\nretry: 3000\n\n"
            while True:
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_S)
                    yield f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()
                except asyncio.TimeoutError:
                    yield b": heartbeat\n\n"
        finally:
            self._subs[ws_id].discard(q)


broker = Broker()
