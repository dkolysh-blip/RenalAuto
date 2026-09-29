"""Фоновый опрос площадок: новые объявления и изменения цены -> БД -> поток событий -> Telegram."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .events import EventHub
from .models import Listing, ListingEvent
from .notify import TelegramNotifier
from .sources import Source
from .storage import Storage

log = logging.getLogger(__name__)

MAX_BACKOFF = 15 * 60


class Poller:
    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        sources: dict[str, Source],
        hub: EventHub,
        notifier: TelegramNotifier | None = None,
    ):
        self.settings = settings
        self.storage = storage
        self.sources = sources
        self.hub = hub
        self.notifier = notifier
        self._tasks: list[asyncio.Task[None]] = []
        self._detail_sem = asyncio.Semaphore(max(1, settings.enrich_concurrency))
        self.status: dict[str, dict[str, Any]] = {
            name: {"last_ok": None, "last_error": None, "last_fetched": 0, "new_total": 0, "errors": 0}
            for name in sources
        }

    def start(self) -> None:
        for source in self.sources.values():
            self._tasks.append(asyncio.create_task(self._run(source), name=f"poll-{source.name}"))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _run(self, source: Source) -> None:
        failures = 0
        while True:
            try:
                await self.poll_once(source)
                failures = 0
                delay = self.settings.poll_interval
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — одна площадка не должна валить остальные
                failures += 1
                st = self.status[source.name]
                st["last_error"] = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}: {exc}"
                st["errors"] += 1
                delay = min(MAX_BACKOFF, self.settings.poll_interval * 2**failures)
                log.warning("%s poll failed (%d in a row), retry in %ss: %s", source.name, failures, delay, exc)
            # Джиттер, чтобы не долбить площадку строго по таймеру
            await asyncio.sleep(delay * random.uniform(0.85, 1.15))

    def _supports_detail(self, source: Source) -> bool:
        return type(source).fetch_detail is not Source.fetch_detail

    async def _enrich(self, source: Source, listing: Listing) -> Listing:
        async with self._detail_sem:
            try:
                return await source.fetch_detail(listing)
            except Exception as exc:  # noqa: BLE001
                log.info("%s detail %s failed: %s", source.name, listing.external_id, exc)
                return listing

    async def poll_once(self, source: Source) -> list[ListingEvent]:
        # Первый запуск по площадке — только наполняем базу, без уведомлений о «новых» старых объявлениях
        warmup = self.storage.count(source.name) == 0
        fetched = await source.fetch_latest(limit=self.settings.poll_limit)
        st = self.status[source.name]
        st["last_ok"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        st["last_fetched"] = len(fetched)

        pending: list[tuple[str, Listing, float | None]] = []
        for listing in fetched:
            status, merged, old_price = self.storage.upsert(listing)
            if status in ("new", "price_changed"):
                pending.append((status, merged, old_price))

        if self.settings.enrich_details and self._supports_detail(source):
            to_enrich = [item for item in pending if item[0] == "new" and not item[1].vin]
            enriched = await asyncio.gather(*(self._enrich(source, l) for _, l, _ in to_enrich))
            by_key = {}
            for listing in enriched:
                _, merged, _ = self.storage.upsert(listing)
                by_key[merged.key] = merged
            pending = [(s, by_key.get(l.key, l), p) for s, l, p in pending]

        if warmup:
            log.info("%s: warm-up, stored %d listings without notifications", source.name, len(fetched))
            return []

        filters = self.storage.list_filters()
        events = []
        for status, listing, old_price in pending:
            matched = [f for f in filters if f.matches(listing)]
            event = ListingEvent(
                type=status,  # type: ignore[arg-type]
                listing=listing,
                old_price=old_price,
                matched_filters=[f.id for f in matched if f.id is not None],
            )
            events.append(event)
            self.hub.publish(event)
            if self.notifier and self.notifier.enabled:
                for flt in matched:
                    await self.notifier.send(event, flt)
        st["new_total"] += sum(1 for e in events if e.type == "new")
        return events
