"""HTTP API + сайт (страницы рендерятся на сервере — их индексируют поисковики)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import date
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlencode

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import __version__, i18n
from .config import Settings
from .customs import TurnkeyCalc, turnkey
from .eligibility import RULES_AS_OF, engine_kind
from .events import EventHub
from .models import LEAD_KIND_LABELS, Lead, LeadIn, LeadStatus, Listing, ListingEvent, SavedFilter
from .notify import TelegramNotifier
from .poller import Poller
from .rates import Rates
from .sources import REGISTRY, Source, build_sources
from .storage import Storage
from .describe import describe
from .view import car_view, fmt_int, scene_car
from .vin.decoder import VinDecoded, decode
from .vin.report import VinReport, build_report, build_report_for_plate, looks_like_plate

log = logging.getLogger(__name__)
HERE = Path(__file__).parent
SSE_KEEPALIVE = 15
PAGE_SIZE = 24
POLICY_DATE = "20 октября 2026 г."  # дата редакции /privacy — менять вместе с текстом
PORT_PER_ZONE = 20  # мест в зоне терминала (Корея / Китай)
PORT_SCAN = 600  # сколько свежих объявлений перебирает пульт подбора
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


class IngestBody(BaseModel):
    collector: str | None = None
    fetched: int = 0
    listings: list[Listing] = Field(default_factory=list, max_length=3000)


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
        page=max(1, _int(q.get("page")) or 1),
    )


def _asset_version() -> str:
    """Версия статики по содержимому файлов: после обновления браузер сразу берёт новые css/js."""
    digest = hashlib.sha1(__version__.encode())
    for path in sorted((HERE / "static").glob("*")):
        if path.is_file():  # media/ (видео) версионируется по имени файла
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


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

    @app.middleware("http")
    async def no_stale_pages(request: Request, call_next):
        # Страницы всегда перепроверяются у сервера: после обновления сайта браузер не покажет старую версию.
        # Статика (css/js) версионируется через ?v=, её можно кэшировать.
        response = await call_next(request)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals.update(
        lead_kinds=LEAD_KIND_LABELS,
        company=settings.company_name,
        company_phone=settings.company_phone,
        company_telegram=settings.company_telegram,
        company_email=settings.company_email,
        company_legal_name=settings.company_legal_name,
        company_requisites=settings.company_requisites,
        company_address=settings.company_address,
        company_vk=settings.company_vk,
        ym_id=settings.ym_id,
        company_avito=settings.company_avito,
        deal=dict(fee=settings.deal_fee_rub, deposit=settings.deal_deposit_rub, pick_days=settings.deal_pick_days,
                  invoice_days=settings.deal_invoice_days, delivery_weeks=settings.deal_delivery_weeks),
        site_url=settings.site_url,
        rules_as_of=RULES_AS_OF,
        fmt=fmt_int,
        asset_version=_asset_version(),
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
        """Объявления для витрины. Непроходные в РФ (объём > 2 л из Кореи, > $50k, гибриды…) не показываем."""
        storage: Storage = app.state.storage
        rows = storage.search(
            country=f.country,
            make=f.make,
            model=f.model,
            year_from=f.year_from,
            mileage_max=f.mileage_max,
            price_usd_max=(f.price_max / rates.get("USD")) if f.price_max and rates.get("USD") else None,
            fuels=FUELS[f.fuel][1] if f.fuel else None,
            sort=f.sort,
            passable_only=True,
            limit=limit + 1,
            offset=offset,
        )
        return [car_view(l, rates) for l in rows[:limit]], len(rows) > limit

    def quote_car(v) -> dict[str, Any]:
        """Машина для сцены + ориентировочная цена под ключ (мощность не известна — считаем по льготе до 160 л.с.)."""
        car = scene_car(v)
        l, cc, eur = v.listing, v.eligibility.displacement_cc, rates.get("EUR")
        engine = engine_kind(l)
        if v.price_rub and l.year and eur and (cc or engine == "ev"):
            years = date.today().year - l.year
            age = "new" if years < 3 else "mid" if years <= 5 else "old"
            q = turnkey(price_rub=v.price_rub, cc=cc or 0, hp=150, age=age, engine=engine, eur_rub=eur,
                        fee_rub=settings.deal_fee_rub, papers_rub=settings.deal_papers_rub,
                        logistics_rub=settings.deal_logistics_kr_rub if l.country == "KR" else settings.deal_logistics_cn_rub)
            car["turnkey"] = q.total_rub
            car["turnkey_from"] = q.total_is_from
            car["calc"] = {"country": l.country, "engine": engine, "age": age, "cc": cc or 0, "price": round(v.price_rub)}
        return car

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
        if v.eligibility.verdict == "bad":
            return Response(status_code=204)
        macros = templates.env.get_template("_macros.html").module
        return HTMLResponse(str(macros.card(v, fresh=True)))

    @app.get("/port", response_class=HTMLResponse, include_in_schema=False)
    async def port_page(request: Request) -> HTMLResponse:
        """Рекламный лендинг «Порт»: терминал, куда заезжают машины из живой ленты."""
        q = request.query_params
        # message match: ?model=k5 / ?make=kia из ссылки рекламы (или utm_term)
        model, make = _clean(q.get("model") or q.get("utm_term")), _clean(q.get("make"))
        storage = storage_of(request)
        cars, seen = [], set()
        for country in ("KR", "CN"):
            rows = []
            if model or make:
                rows = storage.search(country=country, make=make, model=model, passable_only=True, limit=PORT_PER_ZONE)
            rows += storage.search(country=country, passable_only=True, limit=PORT_PER_ZONE)
            for l in rows:
                if l.key not in seen and len([c for c in cars if c.listing.country == country]) < PORT_PER_ZONE:
                    seen.add(l.key)
                    cars.append(car_view(l, rates))
        matched = None
        if model or make:
            hit = next((c for c in cars if (not model or model.lower() in f"{c.model} {c.title}".lower())
                        and (not make or make.lower() in f"{c.make} {c.title}".lower())), None)
            matched = (f"{hit.make} {hit.model}" if hit and hit.make and hit.model
                       else " ".join(x[:1].upper() + x[1:] for x in (make, model) if x))
        scene = {"cars": [quote_car(c) for c in cars], "demo": q.get("demo") == "1", "match": matched}
        return render(
            request, "port.html", cars=cars, matched=matched,
            scene=json.dumps(scene, ensure_ascii=False).replace("</", "<\\/"),
        )

    @app.get("/api/calc", response_model=TurnkeyCalc)
    async def calc(
        price: float = Query(gt=0, le=1_000_000_000),
        currency: Literal["RUB", "KRW", "CNY", "USD", "EUR"] = "RUB",
        cc: int = Query(1600, ge=0, le=10_000),
        hp: int = Query(150, ge=0, le=2000),
        age: Literal["new", "mid", "old"] = "mid",
        engine: Literal["ice", "hybrid", "ev"] = "ice",
        country: Literal["KR", "CN"] = "KR",
    ) -> TurnkeyCalc:
        """Ориентировочная цена под ключ для физлица: пошлина, утильсбор, сборы, доставка, вознаграждение."""
        price_rub = rates.rub(price, currency)
        eur = rates.get("EUR")
        if not price_rub or not eur:
            raise HTTPException(503, "Нет курса валют — попробуйте позже")
        return turnkey(
            price_rub=price_rub, cc=cc, hp=hp, age=age, engine=engine, eur_rub=eur, fee_rub=settings.deal_fee_rub,
            logistics_rub=settings.deal_logistics_kr_rub if country == "KR" else settings.deal_logistics_cn_rub,
            papers_rub=settings.deal_papers_rub,
        )

    @app.get("/api/port/cars", include_in_schema=False)
    async def port_cars(
        request: Request,
        budget: int | None = Query(None, ge=0),
        country: Literal["KR", "CN"] | None = None,
        body: Literal["sedan", "suv", "hatch", "van"] | None = None,
        q: str | None = Query(None, max_length=60),
    ) -> dict[str, Any]:
        """Пульт терминала: машины под бюджет под ключ, страну, кузов, марку/модель (до 20 в зоне)."""
        rows = storage_of(request).search(country=country, passable_only=True, limit=PORT_SCAN)
        # «Kia K5»: каждое слово ищем в исходном названии (기아, 起亚…) и в русском
        words = [[a.lower() for a in i18n.search_aliases(w)] for w in (_clean(q) or "").split()]
        found = []
        for l in rows:
            v = car_view(l, rates)
            text = f"{l.title} {l.make or ''} {l.model or ''} {v.title}".lower()
            if not all(any(a in text for a in aliases) for aliases in words):
                continue
            car = quote_car(v)
            if body and car["body"] != body:
                continue
            if budget and not (car.get("turnkey") and car["turnkey"] <= budget):
                continue
            found.append(car)
        shown = [c for c in found if c["country"] == "KR"][:PORT_PER_ZONE] + [c for c in found if c["country"] == "CN"][:PORT_PER_ZONE]
        return {"cars": shown, "total": len(found)}

    @app.get("/api/port/{source}/{external_id}", include_in_schema=False)
    async def port_car(request: Request, source: str, external_id: str) -> Response:
        """Машина для сцены терминала (по событию из /api/stream). 204 — не показываем."""
        listing = storage_of(request).get(source, external_id)
        if listing is None:
            return Response(status_code=204)
        v = car_view(listing, rates)
        if v.eligibility.verdict == "bad":
            return Response(status_code=204)
        return Response(json.dumps(quote_car(v), ensure_ascii=False), media_type="application/json")

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
            for l in storage.search(make=listing.make, model=listing.model, passable_only=True, limit=5)
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
            request, "car.html", v=v, similar=similar, desc=describe(v, settings.company_name), history=storage.history(source, external_id),
            jsonld=json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/"),
        )

    async def check_any(request: Request, query: str) -> VinReport:
        query = query.strip()
        kwargs = dict(storage=storage_of(request), settings=settings, sources=request.app.state.sources)
        if looks_like_plate(query):
            return await build_report_for_plate(query, **kwargs)
        return await build_report(query, **kwargs)

    @app.get("/vin", response_class=HTMLResponse, include_in_schema=False)
    async def vin_page(request: Request, vin: str | None = None) -> Response:
        if vin and vin.strip():
            return RedirectResponse(f"/vin/{quote(vin.strip())}", status_code=303)
        return render(request, "vin.html", vin=None)

    @app.get("/vin/{query}", response_class=HTMLResponse, include_in_schema=False)
    async def vin_report_page(request: Request, query: str) -> HTMLResponse:
        report = await check_any(request, query)
        cars = [car_view(l, rates) for l in report.listings[:8]]
        return render(request, "vin_report.html", report=report, cars=cars, car=cars[0] if cars else None)

    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_page(request: Request, status: str | None = None) -> HTMLResponse:
        require_admin(request)
        storage = storage_of(request)
        return render(request, "admin.html", leads=storage.list_leads(status), stats=storage.lead_stats())

    @app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
    async def privacy(request: Request) -> HTMLResponse:
        return render(request, "privacy.html", policy_date=POLICY_DATE)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🚗</text></svg>"
        return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=604800"})

    @app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
    async def robots() -> str:
        return f"User-agent: *\nDisallow: /admin\nDisallow: /api/\nDisallow: /partials/\nSitemap: {settings.site_url}/sitemap.xml\n"

    @app.get("/sitemap.xml", include_in_schema=False)
    async def sitemap(request: Request) -> Response:
        urls = [f"<url><loc>{settings.site_url}/</loc><changefreq>hourly</changefreq></url>",
                f"<url><loc>{settings.site_url}/vin</loc></url>",
                f"<url><loc>{settings.site_url}/port</loc></url>",
                f"<url><loc>{settings.site_url}/privacy</loc></url>"]
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

    @app.get("/api/check/{query}", response_model=VinReport)
    async def check_api(request: Request, query: str) -> VinReport:
        """Проверка по VIN или корейскому госномеру (например, 12가3456)."""
        return await check_any(request, query)

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
        if lead.kind is None:
            lead = lead.model_copy(update={"kind": "calc" if listing else "pick"})
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

    # --- API: удалённые сборщики ----------------------------------------------------

    @app.post("/api/ingest/{source}")
    async def ingest(request: Request, source: str, body: IngestBody) -> dict[str, Any]:
        """Приём объявлений от сборщика (python -m renalauto.collector)."""
        if not settings.ingest_token:
            raise HTTPException(403, "INGEST_TOKEN не задан в .env — приём данных выключен")
        if request.headers.get("X-Ingest-Token") != settings.ingest_token:
            raise HTTPException(403, "Неверный токен сборщика")
        if source not in REGISTRY:
            raise HTTPException(404, f"Неизвестная площадка {source!r}")
        wrong = [l.external_id for l in body.listings if l.source != source]
        if wrong:
            raise HTTPException(422, f"Объявления другой площадки: {wrong[:5]}")
        counts = await request.app.state.poller.ingest(source, body.listings, body.collector)
        return {"ok": True, "counts": counts}

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
