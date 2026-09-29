"""Удалённый сборщик: забирает объявления с площадки и отправляет их на основной сервер.

Нужен для площадок, которые не пускают сервер из дата-центра (Encar). Запускается на машине
с корейским домашним/офисным интернетом (мини-ПК, Raspberry Pi, ноутбук) или с PROXY_KR.
Входящие порты не нужны — сборщик сам ходит на сервер.

    COLLECTOR_SERVER=https://renal-auto.asia:8443 INGEST_TOKEN=... python -m renalauto.collector

Работает бережно: по каждому НОВОМУ объявлению — карточка и страховая история, с паузой между
запросами; уже известные объявления повторно не открываются.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import socket
from typing import Any

import httpx

from .config import Settings
from .models import Listing
from .poller import DETAIL_MARK
from .sources import REGISTRY, Source
from .storage import Storage

log = logging.getLogger("renalauto.collector")

MAX_OUTBOX = 2000
MAX_BACKOFF = 30 * 60


class Collector:
    def __init__(
        self,
        settings: Settings,
        server: str,
        token: str,
        source_names: list[str],
        state_path: str,
        name: str,
        detail_delay: float = 2.0,
        with_history: bool = True,
        http: httpx.AsyncClient | None = None,
        sources: dict[str, Source] | None = None,
    ):
        self.settings = settings
        self.server = server.rstrip("/")
        self.token = token
        self.name = name
        self.detail_delay = detail_delay
        self.with_history = with_history
        self.state = Storage(state_path)
        self.sources = sources or {n: REGISTRY[n](settings) for n in source_names}
        self.http = http or httpx.AsyncClient(timeout=60)
        self.outbox: dict[str, dict[tuple[str, str], Listing]] = {n: {} for n in self.sources}

    async def _collect_one(self, source: Source, listing: Listing) -> Listing:
        try:
            if hasattr(source, "collect"):
                detailed = await source.collect(listing, with_history=self.with_history)  # type: ignore[attr-defined]
            else:
                detailed = await source.fetch_detail(listing)
        except Exception as exc:  # noqa: BLE001 — карточку догрузим в следующий раз
            log.warning("%s detail %s failed: %s", source.name, listing.external_id, exc)
            return listing
        return detailed.model_copy(update={"extra": {**detailed.extra, DETAIL_MARK: True}})

    async def run_once(self, source: Source) -> dict[str, Any]:
        fetched = await source.fetch_latest(limit=self.settings.poll_limit)
        outbox = self.outbox[source.name]
        for listing in fetched:
            status, merged, _ = self.state.upsert(listing)
            needs_detail = not merged.extra.get(DETAIL_MARK)
            if needs_detail:
                merged = await self._collect_one(source, merged)
                _, merged, _ = self.state.upsert(merged)
                await asyncio.sleep(self.detail_delay * random.uniform(0.7, 1.3))
            if status != "unchanged" or needs_detail:
                outbox[merged.key] = merged
        # Ограничиваем очередь, если сервер долго недоступен
        while len(outbox) > MAX_OUTBOX:
            outbox.pop(next(iter(outbox)))
        return await self.push(source.name, fetched_count=len(fetched))

    async def push(self, source_name: str, fetched_count: int = 0) -> dict[str, Any]:
        outbox = self.outbox[source_name]
        batch = list(outbox.values())
        response = await self.http.post(
            f"{self.server}/api/ingest/{source_name}",
            headers={"X-Ingest-Token": self.token},
            json={
                "collector": self.name,
                "fetched": fetched_count,
                "listings": [l.model_dump(mode="json") for l in batch],
            },
        )
        response.raise_for_status()
        for listing in batch:
            outbox.pop(listing.key, None)
        result = response.json()
        log.info("%s: fetched %d, pushed %d -> %s", source_name, fetched_count, len(batch), result.get("counts"))
        return result

    async def run_source(self, source: Source) -> None:
        failures = 0
        while True:
            try:
                await self.run_once(source)
                failures = 0
                delay = self.settings.poll_interval
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                failures += 1
                delay = min(MAX_BACKOFF, self.settings.poll_interval * 2**failures)
                log.warning("%s cycle failed (%d in a row), retry in %ss: %s", source.name, failures, delay, exc)
            await asyncio.sleep(delay * random.uniform(0.85, 1.15))

    async def run_forever(self) -> None:
        await asyncio.gather(*(self.run_source(s) for s in self.sources.values()))

    async def aclose(self) -> None:
        for source in self.sources.values():
            await source.aclose()
        await self.http.aclose()
        self.state.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    server = os.getenv("COLLECTOR_SERVER")
    token = os.getenv("INGEST_TOKEN")
    if not server or not token:
        raise SystemExit("Нужны переменные COLLECTOR_SERVER и INGEST_TOKEN")
    settings = Settings()
    if not os.getenv("POLL_INTERVAL"):
        settings.poll_interval = 120
    collector = Collector(
        settings,
        server=server,
        token=token,
        source_names=[s.strip() for s in os.getenv("COLLECTOR_SOURCES", "encar").split(",") if s.strip()],
        state_path=os.getenv("COLLECTOR_STATE", "collector.db"),
        name=os.getenv("COLLECTOR_NAME", socket.gethostname()),
        detail_delay=float(os.getenv("COLLECTOR_DETAIL_DELAY", "2")),
        with_history=os.getenv("COLLECTOR_HISTORY", "true").lower() in ("1", "true", "yes", "on"),
    )

    async def run() -> None:
        try:
            await collector.run_forever()
        finally:
            await collector.aclose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
