"""线程安全的进程内事件总线（WebSocket 广播）。"""
from __future__ import annotations

import asyncio
import itertools
import threading
from collections import deque
from typing import Any

from .utils import iso_ms


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[int, asyncio.Queue] = {}
        self._ids = itertools.count(1)
        self._seq = itertools.count(1)
        self._loop: asyncio.AbstractEventLoop | None = None
        self.recent: deque[dict[str, Any]] = deque(maxlen=60)

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def register(self) -> tuple[int, asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            sub_id = next(self._ids)
            self._subscribers[sub_id] = queue
        return sub_id, queue

    def unregister(self, sub_id: int) -> None:
        with self._lock:
            self._subscribers.pop(sub_id, None)

    def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload.setdefault("ts", iso_ms())
        payload["seq"] = next(self._seq)
        with self._lock:
            self.recent.append(payload)
            loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._dispatch, payload)
            except RuntimeError:
                pass
        return payload

    def _dispatch(self, payload: dict[str, Any]) -> None:
        with self._lock:
            queues = list(self._subscribers.values())
        for queue in queues:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    continue

    def snapshot(self, limit: int = 6, types: set[str] | None = None) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self.recent)
        if types:
            items = [item for item in items if item.get("type") in types]
        return items[-limit:]
