"""Шина событий в памяти: поллер публикует, SSE-клиенты подписываются."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from .models import ListingEvent


class EventHub:
    def __init__(self, queue_size: int = 1000):
        self._subscribers: set[asyncio.Queue[ListingEvent]] = set()
        self._queue_size = queue_size

    @property
    def subscribers(self) -> int:
        return len(self._subscribers)

    def publish(self, event: ListingEvent) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                # Медленный клиент не должен тормозить остальных — выбрасываем самое старое.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[ListingEvent]]:
        queue: asyncio.Queue[ListingEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)
