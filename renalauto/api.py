"""HTTP API + сайт (страницы рендерятся на сервере — их индексируют поисковики)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import date
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import __version__
from .config import Settings
from .eligibility import RULES_AS_OF
from .events import EventHub
from .models import Lead, LeadIn, LeadStatus, Listing, ListingEvent, SavedFilter
from .notify import TelegramNotifier
from .poller import Poller
from .rates import Rates
from .sources import Source, build_sources
from .storage import Storage
from .view import car_view, fmt_int
from .vin.decoder import VinDecoded, decode
from .vin.report import VinReport, build_report

log = logging.getLogger(__name__)
HERE = Path(__file__).parent
SSE_KEEPALIVE = 15
PAGE_SIZE = 24
RATES_REFRESH = 6 * 3600

# Значение фильтра «топливо» -> как оно пишется на площадках
FUELS: dict[str, tuple[str, list[str]]] = {
    "petrol": ("Бензин", ["가솔린", "汽油"]),
    "diesel": ("Дизель", ["디젤", "柴油"]),
    "hybrid": ("Гибрид", ["하이브리드", "混", "增程"]),
    "electric": ("Электро", ["전기", "纯电", "电动"]),
    "lpg": ("Газ", ["LPG"]),
}
SORTS = [
    ("new", "Сначала новые"),
    ("price_asc", "Сначала дешёвые"),
    ("price_desc", "Сначала дорогие"),
    ("year_desc", "Сначала свежие по году"),
    ("mileage_asc", "С меньшим пробегом"),
]
POPULAR_MAKES = [
    "Hyundai", "Kia", "Genesis", "Chevrolet", "Renault Korea", "KG Mobility", "BMW", "Mercedes-Benz", "Audi",
    "Volkswagen", "Toyota", "Lexus", "Honda", "Nissan", "BYD", "Geely", "Changan", "Chery", "Haval", "Li Auto",
    "Zeekr", "Lynk & Co", "Tesla", "Volvo", "Porsche",
]

LEADS_PER_WINDOW = 5
LEADS_WINDOW = 600


class LeadUpdate(BaseModel):
    status: LeadStatus | None = None
    manager_note: str | None = None


class PageFilters(BaseModel):
    country: Literal["KR", "CN"] | None = None
    make: str | None = None
    model: str | None = None
    year_from: int | None = None
    mileage_max: int | None = None
    price_max: int | None = None
    fuel: str | None = None
    sort: str = "new"
    passable: bool = False
    page: int = 1


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _int(value: str | None) -> int | None:
    try:
        return int(str(value).replace(" ", "")) if value not in (None, "") else None
    except ValueError:
        return None


def page_filters(request: Request) -> PageFilters:
    q = request.query_params
    return PageFilters(
        country=q.get("country") if q.get("country") in ("KR", "CN") else None,
        make=_clean(q.get("make")),
        model=_clean(q.get("model")),
        year_from=_int(q.get("year_from")),
        mileage_max=_int(q.get("mileage_max")),
        price_max=_int(q.get("price_max")),
        fuel=q.get("fuel") if q.get("fuel") in FUELS else None,
        sort=q.get("sort") if q.get("sort") in dict(SORTS) else "new",
        passable=q.get("passable") in ("1", "on", "true"),
        page=max(1, _int(q.get("page")) or 1),
    )


def create_app(settings: Settings | None = None, sources: dict[str, Source] | None = None) -> FastAPI:
    settings = settings or Settings()
    rates = Rates(
        {
            "KRW": settings.rate_krw_rub,
            "CNY": settings.rate_cny_rub,
            "USD": settings.rate_usd_rub,
            "EUR": settings.rate_eur_rub,
        }
    )
    lead_hits: dict[str, deque[float]] = defaultdict(deque)

    async def refresh_rates_forever() -> None:
        while True:
            await rates.refresh(force=True)
            await asyncio.sleep(RATES_REFRESH)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        storage = Storage(settings.db_path)
        srcs = sources if sources is not None else build_sources(settings)
        hub = EventHub()
        notifier = TelegramNotifier(settings)
        poller = Poller(settings, storage, srcs, hub, notifier)
        app.state.storage, app.state.sources, app.state.hub, app.state.poller = storage, srcs, hub, poller
        app.state.notifier = notifier
        if settings.poller_enabled:
            poller.start()
        rates_task = asyncio.create_task(refresh_rates_forever()) if settings.rates_live else None
        if not settings.admin_token:
            log.warning("ADMIN_TOKEN не задан: заявки и служебные функции недоступны")
        try:
            yield
        finally:
            if rates_task:
                rates_task.cancel()
                with suppress(asyncio.CancelledError):
                    await rates_task
            await poller.stop()
            await notifier.aclose()
            for source in srcs.values():
                await source.aclose()
            storage.close()

    app = FastAPI(
        title=settings.company_name,
        description="Объявления с вторичного рынка Кореи и Китая в реальном времени + проверка по VIN",
        version=__version__,
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals.update(
        company=settings.company_name,
        company_phone=settings.company_phone,
        company_telegram=settings.company_telegram,
        site_url=settings.site_url,
        rules_as_of=RULES_AS_OF,
        fmt=fmt_int,
        asset_version=__version__,
    )

    def render(request: Request, name: str, status_code: int = 200, **context: Any) -> HTMLResponse:
        context.update(year=date.today().year, rates_source=rates.source)
        return templates.TemplateResponse(request, name, context, status_code=status_code)

    def storage_of(request: Request) -> Storage:
        return request.app.state.storage

    def source_of(request: Request, name: str) -> Source:
        source = request.app.state.sources.get(name)
        if source is None:
            raise HTTPException(404, f"Площадка {name!r} не подключена")
        return source

    def require_admin(request: Request) -> None:
        if not settings.admin_token:
            raise HTTPException(403, "ADMIN_TOKEN не задан в .env — служебные функции отключены")
        token = request.headers.get("X-Admin-Token") or request.query_params.get("token")
        if token != settings.admin_token:
            raise HTTPException(403, "Нужен токен администратора")

    def client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "?"

    def query_cars(f: PageFilters, limit: int, offset: int) -> tuple[list, bool]:
        """Объявления для витрины. Фильтр «проходные» считается в Python, поэтому выбираем с запасом."""
        storage: Storage = app.state.storage
        kwargs = dict(
            country=f.country,
            make=f.make,
            model=f.model,
            year_from=f.year_from,
            mileage_max=f.mileage_max,
            price_usd_max=(f.price_max / rates.get("USD")) if f.price_max and rates.get("USD") else None,
            fuels=FUELS[f.fuel][1] if f.fuel else None,
            sort=f.sort,
        )
        if not f.passable:
            rows = storage.search(limit=limit + 1, offset=offset, **kwargs)
            return [car_view(l, rates) for l in rows[:limit]], len(rows) > limit
        views, skipped, scan_offset, batch = [], 0, 0, 200
        while len(views) <= limit and scan_offset < 5000:
            rows = storage.search(limit=batch, offset=scan_offset, **kwargs)
            for listing in rows:
                v = car_view(listing, rates)
                if v.eligibility.verdict == "bad":
                    continue
                if skipped < offset:
                    skipped += 1
                    continue
                views.append(v)
            if len(rows) < batch:
                break
            scan_offset += batch
        return views[:limit], len(views) > limit

    def stream_query(f: PageFilters) -> str:
        params = {"country": f.country, "make": f.make, "model": f.model, "year_from": f.year_from,
                  "mileage_max": f.mileage_max}
        return urlencode({k: v for k, v in params.items() if v})

    # --- страницы ------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(request: Request) -> HTMLResponse:
        f = page_filters(request)
        cars, has_more = query_cars(f, PAGE_SIZE, (f.page - 1) * PAGE_SIZE)
        next_url = None
        if has_more:
            params = dict(request.query_params)
            params["page"] = str(f.page + 1)
            next_url = "/?" + urlencode(params)
        return render(
            request, "index.html", f=f, cars=cars, next_url=next_url, makes=POPULAR_MAKES,
            fuels=[(k, v[0]) for k, v in FUELS.items()], sorts=SORTS, stream_query=stream_query(f),
        )

    @app.get("/partials/card/{source}/{external_id}", response_class=HTMLResponse, include_in_schema=False)
    async def card_partial(request: Request, source: str, external_id: str) -> Response:
        listing = storage_of(request).get(source, external_id)
        if listing is None:
            return Response(status_code=204)
        v = car_view(listing, rates)
        f = page_filters(request)
        if f.passable and v.eligibility.verdict == "bad":
            return Response(status_code=204)
        macros = templates.env.get_template("_macros.html").module
        return HTMLResponse(str(macros.card(v, fresh=True)))

    @app.get("/car/{source}/{external_id}", response_class=HTMLResponse, include_in_schema=False)
    async def car_page(request: Request, source: str, external_id: str) -> HTMLResponse:
        storage = storage_of(request)
        listing = storage.get(source, external_id)
        if listing is None:
            return render(request, "index.html", status_code=404, f=PageFilters(), cars=[], next_url=None,
                          makes=POPULAR_MAKES, fuels=[(k, v[0]) for k, v in FUELS.items()], sorts=SORTS,
                          stream_query="")
        v = car_view(listing, rates)
        similar = [
            car_view(l, rates)
            for l in storage.search(make=listing.make, model=listing.model, limit=5)
            if l.key != listing.key
        ][:4]
        jsonld = {
            "@context": "https://schema.org",
            "@type": "Car",
            "name": f"{v.title} {listing.year or ''}".strip(),
            "image": v.photos[:10],
            "brand": {"@type": "Brand", "name": v.make or ""},
            "vehicleModelDate": str(listing.year or ""),
            "fuelType": v.fuel or "",
            "url": settings.site_url + v.path,
        }
        if listing.mileage_km is not None:
            jsonld["mileageFromOdometer"] = {"@type": "QuantitativeValue", "value": listing.mileage_km, "unitCode": "KMT"}
        if v.price_rub:
            jsonld["offers"] = {"@type": "Offer", "price": v.price_rub, "priceCurrency": "RUB",
                                "availability": "https://schema.org/InStock", "url": settings.site_url + v.path}
        return render(
            request, "car.html", v=v, similar=similar, history=storage.history(source, external_id),
            jsonld=json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/"),
        )

    @app.get("/vin", response_class=HTMLResponse, include_in_schema=False)
    async def vin_page(request: Request, vin: str | None = None) -> HTMLResponse:
        return render(request, "vin.html", vin=vin)

    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_page(request: Request, status: str | None = None) -> HTMLResponse:
        require_admin(request)
        storage = storage_of(request)
        return render(request, "admin.html", leads=storage.list_leads(status), stats=storage.lead_stats())

    @app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
    async def robots() -> str:
        return f"User-agent: *\nDisallow: /admin\nDisallow: /api/\nDisallow: /partials/\nSitemap: {settings.site_url}/sitemap.xml\n"

    @app.get("/sitemap.xml", include_in_schema=False)
    async def sitemap(request: Request) -> Response:
        urls = [f"<url><loc>{settings.site_url}/</loc><changefreq>hourly</changefreq></url>",
                f"<url><loc>{settings.site_url}/vin</loc></url>"]
        for source, external_id, last_seen in storage_of(request).recent_listing_keys(5000):
            urls.append(f"<url><loc>{settings.site_url}/car/{source}/{external_id}</loc><lastmod>{last_seen[:10]}</lastmod></url>")
        body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(urls) + "</urlset>"
        return Response(body, media_type="application/xml")

    # --- API: объявления, VIN -------------------------------------------------

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        return {
            "ok": True,
            "listings": storage_of(request).count(),
            "stream_clients": request.app.state.hub.subscribers,
            "sources": request.app.state.poller.status,
            "rates": rates.as_dict(),
            "admin_token_set": bool(settings.admin_token),
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
        sort: str = "new",
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
            sort=sort,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/listings/{source}/{external_id}")
    async def get_listing(request: Request, source: str, external_id: str) -> dict[str, Any]:
        storage = storage_of(request)
        listing = storage.get(source, external_id)
        if listing is None:
            raise HTTPException(404, "Объявление не найдено")
        return {"listing": listing, "view": car_view(listing, rates).as_json(), "history": storage.history(source, external_id)}

    @app.get("/api/listings/{source}/{external_id}/vin-report", response_model=VinReport)
    async def listing_vin_report(request: Request, source: str, external_id: str) -> VinReport:
        storage = storage_of(request)
        listing = storage.get(source, external_id)
        if listing is None:
            raise HTTPException(404, "Объявление не найдено")
        if not listing.vin:
            src = request.app.state.sources.get(source)
            if src is not None:
                with suppress(Exception):
                    listing = await src.fetch_detail(listing)
                    _, listing, _ = storage.upsert(listing)
        if not listing.vin:
            raise HTTPException(
                404, "Продавец не опубликовал VIN. Оставьте заявку — менеджер запросит VIN и отчёт об истории."
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

    # --- API: заявки ----------------------------------------------------------

    @app.post("/api/leads", status_code=201)
    async def create_lead(request: Request, lead: LeadIn) -> dict[str, Any]:
        if lead.website:  # бот заполнил скрытое поле — делаем вид, что всё хорошо
            return {"ok": True}
        if not (lead.phone or lead.telegram):
            raise HTTPException(422, "Укажите телефон или Telegram")
        ip = client_ip(request)
        hits = lead_hits[ip]
        now = time.monotonic()
        while hits and now - hits[0] > LEADS_WINDOW:
            hits.popleft()
        if len(hits) >= LEADS_PER_WINDOW:
            raise HTTPException(429, "Слишком много заявок подряд — попробуйте через несколько минут")
        hits.append(now)
        storage = storage_of(request)
        listing = storage.get(lead.source, lead.external_id) if lead.source and lead.external_id else None
        saved = storage.add_lead(lead, listing)
        if listing:
            saved.listing_title = car_view(listing, rates).title + (f", {listing.year}" if listing.year else "")
        sent = await request.app.state.notifier.send_lead(saved, settings.site_url)
        if not sent:
            log.warning("lead #%s saved but not delivered to Telegram (check TELEGRAM_* settings)", saved.id)
        return {"ok": True, "id": saved.id}

    @app.get("/api/leads", response_model=list[Lead], dependencies=[Depends(require_admin)])
    async def list_leads(request: Request, status: LeadStatus | None = None) -> list[Lead]:
        return storage_of(request).list_leads(status)

    @app.get("/api/leads/stats", dependencies=[Depends(require_admin)])
    async def leads_stats(request: Request) -> dict[str, int]:
        return storage_of(request).lead_stats()

    @app.patch("/api/leads/{lead_id}", response_model=Lead, dependencies=[Depends(require_admin)])
    async def update_lead(request: Request, lead_id: int, patch: LeadUpdate) -> Lead:
        lead = storage_of(request).update_lead(lead_id, patch.status, patch.manager_note)
        if lead is None:
            raise HTTPException(404, "Заявка не найдена")
        return lead

    # --- API: служебное ----------------------------------------------------------

    @app.get("/api/filters", response_model=list[SavedFilter], dependencies=[Depends(require_admin)])
    async def list_filters(request: Request) -> list[SavedFilter]:
        return storage_of(request).list_filters()

    @app.post("/api/filters", response_model=SavedFilter, status_code=201, dependencies=[Depends(require_admin)])
    async def add_filter(request: Request, flt: SavedFilter) -> SavedFilter:
        return storage_of(request).add_filter(flt)

    @app.delete("/api/filters/{filter_id}", status_code=204, dependencies=[Depends(require_admin)])
    async def delete_filter(request: Request, filter_id: int) -> None:
        if not storage_of(request).delete_filter(filter_id):
            raise HTTPException(404, "Фильтр не найден")

    @app.post("/api/poll/{source}", dependencies=[Depends(require_admin)])
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
    ) -> StreamingResponse:
        """Server-Sent Events: новые объявления и изменения цены в реальном времени."""
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
