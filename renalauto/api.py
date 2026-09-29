"""HTTP API + веб-интерфейс."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from .config import Settings
from .events import EventHub
from .models import Listing, ListingEvent, SavedFilter
from .notify import TelegramNotifier
from .poller import Poller
from .sources import Source, build_sources
from .storage import Storage
from .vin.decoder import VinDecoded, decode
from .vin.report import VinReport, build_report

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
SSE_KEEPALIVE = 15


def create_app(settings: Settings | None = None, sources: dict[str, Source] | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        storage = Storage(settings.db_path)
        srcs = sources if sources is not None else build_sources(settings)
        hub = EventHub()
        notifier = TelegramNotifier(settings)
        poller = Poller(settings, storage, srcs, hub, notifier)
        app.state.storage, app.state.sources, app.state.hub, app.state.poller = storage, srcs, hub, poller
        if settings.poller_enabled:
            poller.start()
        try:
            yield
        finally:
            await poller.stop()
            await notifier.aclose()
            for source in srcs.values():
                await source.aclose()
            storage.close()

    app = FastAPI(
        title="RenalAuto",
        description="Объявления с вторичного рынка Кореи и Китая в реальном времени + проверка по VIN",
        version="0.1.0",
        lifespan=lifespan,
    )

    def storage_of(request: Request) -> Storage:
        return request.app.state.storage

    def source_of(request: Request, name: str) -> Source:
        source = request.app.state.sources.get(name)
        if source is None:
            raise HTTPException(404, f"Площадка {name!r} не подключена")
        return source

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        return {
            "ok": True,
            "listings": storage_of(request).count(),
            "stream_clients": request.app.state.hub.subscribers,
            "sources": request.app.state.poller.status,
        }

    @app.get("/api/listings", response_model=list[Listing])
    async def list_listings(
        request: Request,
        source: str | None = None,
        country: Literal["KR", "CN"] | None = None,
        make: str | None = None,
        model: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        mileage_max: int | None = None,
        price_usd_max: float | None = None,
        vin: str | None = None,
        limit: int = Query(50, le=500),
        offset: int = 0,
    ) -> list[Listing]:
        return storage_of(request).search(
            source=source,
            country=country,
            make=make,
            model=model,
            year_from=year_from,
            year_to=year_to,
            mileage_max=mileage_max,
            price_usd_max=price_usd_max,
            vin=vin.upper() if vin else None,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/listings/{source}/{external_id}")
    async def get_listing(request: Request, source: str, external_id: str, refresh: bool = False) -> dict[str, Any]:
        storage = storage_of(request)
        listing = storage.get(source, external_id)
        if listing is None:
            raise HTTPException(404, "Объявление не найдено")
        if refresh:
            listing = await source_of(request, source).fetch_detail(listing)
            _, listing, _ = storage.upsert(listing)
        return {"listing": listing, "history": storage.history(source, external_id)}

    @app.get("/api/listings/{source}/{external_id}/vin-report", response_model=VinReport)
    async def listing_vin_report(request: Request, source: str, external_id: str) -> VinReport:
        storage = storage_of(request)
        listing = storage.get(source, external_id)
        if listing is None:
            raise HTTPException(404, "Объявление не найдено")
        src = source_of(request, source)
        if not listing.vin:
            listing = await src.fetch_detail(listing)
            _, listing, _ = storage.upsert(listing)
        if not listing.vin:
            raise HTTPException(
                404,
                "Площадка не публикует VIN этого авто. Запросите VIN у продавца и проверьте через /api/vin/{vin}",
            )
        return await build_report(
            listing.vin, storage=storage, settings=settings, sources=request.app.state.sources, listing=listing
        )

    @app.get("/api/vin/{vin}", response_model=VinReport)
    async def vin_report(request: Request, vin: str) -> VinReport:
        return await build_report(vin, storage=storage_of(request), settings=settings, sources=request.app.state.sources)

    @app.get("/api/vin/{vin}/decode", response_model=VinDecoded)
    async def vin_decode(vin: str, year: int | None = None) -> VinDecoded:
        return decode(vin, year_hint=year)

    @app.get("/api/filters", response_model=list[SavedFilter])
    async def list_filters(request: Request) -> list[SavedFilter]:
        return storage_of(request).list_filters()

    @app.post("/api/filters", response_model=SavedFilter, status_code=201)
    async def add_filter(request: Request, flt: SavedFilter) -> SavedFilter:
        return storage_of(request).add_filter(flt)

    @app.delete("/api/filters/{filter_id}", status_code=204)
    async def delete_filter(request: Request, filter_id: int) -> None:
        if not storage_of(request).delete_filter(filter_id):
            raise HTTPException(404, "Фильтр не найден")

    @app.post("/api/poll/{source}")
    async def poll_now(request: Request, source: str) -> dict[str, Any]:
        """Внеочередной опрос площадки."""
        events = await request.app.state.poller.poll_once(source_of(request, source))
        return {"events": len(events), "status": request.app.state.poller.status[source]}

    @app.get("/api/stream")
    async def stream(
        request: Request,
        source: str | None = None,
        country: Literal["KR", "CN"] | None = None,
        make: str | None = None,
        model: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        mileage_max: int | None = None,
        price_usd_max: float | None = None,
        q: str | None = None,
        filter_id: int | None = None,
    ) -> StreamingResponse:
        """Server-Sent Events: новые объявления и изменения цены в реальном времени."""
        if filter_id is not None:
            saved = {f.id: f for f in storage_of(request).list_filters()}
            if filter_id not in saved:
                raise HTTPException(404, "Фильтр не найден")
            flt = saved[filter_id]
        else:
            flt = SavedFilter(
                name="stream",
                source=source,
                country=country,
                make=make,
                model=model,
                year_from=year_from,
                year_to=year_to,
                mileage_max=mileage_max,
                price_usd_max=price_usd_max,
                query=q,
            )
        hub: EventHub = request.app.state.hub

        async def events() -> AsyncIterator[str]:
            async with hub.subscribe() as queue:
                yield ": connected\n\n"
                while not await request.is_disconnected():
                    try:
                        event: ListingEvent = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    if flt.matches(event.listing):
                        yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app
