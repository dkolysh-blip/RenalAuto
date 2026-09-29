"""Encar.com — крупнейшая площадка б/у авто в Южной Корее.

Используются публичные JSON-эндпоинты, которые дергает сам сайт fem.encar.com:
  * поиск:   https://api.encar.com/search/car/list/general
  * карточка: https://api.encar.com/v1/readside/vehicle/{id}           (VIN, госномер)
  * история: https://api.encar.com/v1/readside/record/vehicle/{id}/open (ДТП, владельцы — данные страховых)
Цена в выдаче — в 만원 (10 000 вон).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from typing import Any

import httpx

from ..models import Listing
from .base import Source, SourceError, to_float, to_int

API = "https://api.encar.com"
PHOTO_HOST = "https://ci.encar.com"
CARD_URL = "https://fem.encar.com/cars/detail/{id}"

# Отечественные (CarType.Y) и импортные (CarType.N) авто, скрытые объявления исключены.
DEFAULT_QUERIES = "(And.Hidden.N._.CarType.Y.);(And.Hidden.N._.CarType.N.)"

MAN_WON = 10_000

DEFAULT_SEARCH_PATHS = "general,premium,mobile"

# Режим «web»: api.encar.com закрыт для дата-центров, но страницы сайта отдают те же данные в HTML:
#   список  — car.encar.com/list/car (JSON в __NEXT_DATA__, формат как у поискового API)
#   карточка — fem.encar.com/cars/detail/{id} (встроенный JSON с VIN, госномером, характеристиками, фото)
WEB_LIST_URL = "https://car.encar.com/list/car"
WEB_CARD_URL = "https://fem.encar.com/cars/detail/{id}"
WEB_PAGE_SIZE = 20
DEFAULT_WEB_SEARCH = {
    "type": "car",
    "action": "(And.Hidden.N._.CarType.A.)",
    "title": "국산",
    "toggle": {},
    "layer": "",
    "sort": "ModifiedDate",
}
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_DETAIL_KEYS = ("category", "spec", "advertisement", "contact", "photos", "manage", "condition")


def find_search_items(node: Any) -> list[dict[str, Any]]:
    """Все объявления в формате поискового API (Id, Manufacturer, Price…) где угодно в JSON страницы."""
    found: dict[str, dict[str, Any]] = {}

    def walk(n: Any) -> None:
        if isinstance(n, list):
            if n and all(isinstance(i, dict) for i in n) and any("Id" in i and ("Manufacturer" in i or "Model" in i) for i in n):
                for i in n:
                    if i.get("Id"):
                        found.setdefault(str(i["Id"]), i)
                return
            for i in n:
                walk(i)
        elif isinstance(n, dict):
            for v in n.values():
                walk(v)

    walk(node)
    return list(found.values())


def extract_vehicle(html_text: str, car_id: str) -> dict[str, Any] | None:
    """Данные автомобиля из HTML карточки fem.encar.com (тот же формат, что /v1/readside/vehicle)."""
    anchor = html_text.find(f'"requestUrl":"/v1/readside/vehicle/{car_id}')
    if anchor < 0:
        anchor = html_text.find(f'"vehicleId":{car_id}')
    if anchor < 0:
        return None
    decoder = json.JSONDecoder()
    start = max(0, anchor - 300_000)
    data: dict[str, Any] = {"vehicleId": int(car_id) if car_id.isdigit() else car_id}
    for key in _DETAIL_KEYS:
        # последнее вхождение ключа перед якорем — поле именно этого автомобиля
        matches = list(re.compile(rf'"{key}"\s*:\s*').finditer(html_text, start, anchor))
        if not matches:
            continue
        try:
            data[key], _ = decoder.raw_decode(html_text, matches[-1].end())
        except ValueError:
            continue
    near = html_text[max(0, anchor - 1500): anchor + 300]
    vin = re.search(r'"vin"\s*:\s*"([A-HJ-NPR-Z0-9]{11,17})"', near)
    plate = re.search(r'"vehicleNo"\s*:\s*"([^"]{2,20})"', near)
    if vin:
        data["vin"] = vin.group(1)
    if plate:
        data["vehicleNo"] = plate.group(1)
    return data
# Без этих заголовков api.encar.com может отвечать 404/403
BROWSER_HEADERS = {
    "Referer": "https://www.encar.com/",
    "Origin": "https://www.encar.com",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def _photo_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http"):
        return path
    # В выдаче путь без номера кадра: "/carpicture07/pic3812/38123456_"
    if path.endswith("_"):
        path += "001.jpg"
    return PHOTO_HOST + path


def _item_photos(item: dict[str, Any]) -> list[str]:
    """Фото из элемента выдачи: поле Photo (префикс пути) или список Photos."""
    urls: list[str] = []
    for photo in item.get("Photos") or []:
        if isinstance(photo, dict):
            for value in photo.values():
                if isinstance(value, str) and "carpicture" in value and value.lower().endswith((".jpg", ".jpeg", ".png")):
                    urls.append(value)
                    break
    return [u for u in dict.fromkeys(_photo_url(u) for u in urls) if u][:30]


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f %z", "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            # "+09" -> "+0900"
            candidate = text + "00" if len(text) > 3 and text[-3] in "+-" else text
            return datetime.strptime(candidate, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class EncarSource(Source):
    name = "encar"
    country = "KR"
    currency = "KRW"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.queries = [q.strip() for q in os.getenv("ENCAR_QUERIES", DEFAULT_QUERIES).split(";") if q.strip()]
        # Сайт использует несколько вариантов поискового эндпоинта; перебираем, запоминаем рабочий.
        self.search_paths = [
            p.strip() for p in os.getenv("ENCAR_SEARCH_PATHS", DEFAULT_SEARCH_PATHS).split(",") if p.strip()
        ]
        # web — через страницы сайта (работает с сервера в дата-центре); api — api.encar.com (нужен корейский IP)
        self.mode = os.getenv("ENCAR_MODE", "web").strip().lower()
        self.web_search = json.loads(os.getenv("ENCAR_WEB_SEARCH") or json.dumps(DEFAULT_WEB_SEARCH))

    async def fetch_latest(self, limit: int = 50, query: str | None = None, **_: Any) -> list[Listing]:
        if self.mode == "web":
            return await self._web_latest(limit)
        queries = [query] if query else self.queries
        batches = await asyncio.gather(*(self._search(q, limit) for q in queries))
        listings = [item for batch in batches for item in batch]
        listings.sort(key=lambda l: l.listed_at or datetime.min.astimezone(), reverse=True)
        return listings

    async def _search(self, query: str, limit: int) -> list[Listing]:
        params = {"count": "true", "q": query, "sr": f"|ModifiedDate|0|{limit}"}
        last_error: SourceError | None = None
        for path in list(self.search_paths):
            response = await self.client.get(
                f"{API}/search/car/list/{path}", params=params, headers=BROWSER_HEADERS
            )
            self._raise_if_blocked(response)
            if response.status_code == 404 and len(self.search_paths) > 1:
                last_error = SourceError(f"encar: HTTP 404 for {response.request.url}")
                continue
            data = self._json(response)
            if path != self.search_paths[0]:
                self.search_paths.remove(path)
                self.search_paths.insert(0, path)
            break
        else:
            raise last_error or SourceError("encar: no search endpoint configured")
        results = data.get("SearchResults") if isinstance(data, dict) else None
        if results is None:
            raise SourceError("encar: unexpected search response shape")
        return [self.parse_search_item(item) for item in results if item.get("Id")]

    async def _get_html(self, url: str, **kwargs: Any) -> str:
        headers = {"Accept": "text/html,application/xhtml+xml", "Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://car.encar.com/"}
        response = await self.client.get(url, headers=headers, **kwargs)
        self._raise_if_blocked(response)
        if response.status_code >= 400:
            raise SourceError(f"encar: HTTP {response.status_code} for {response.request.url}")
        return response.text

    async def _web_latest(self, limit: int) -> list[Listing]:
        items: dict[str, dict[str, Any]] = {}
        pages = max(1, min(10, -(-limit // WEB_PAGE_SIZE)))
        search = json.dumps(self.web_search, ensure_ascii=False, separators=(",", ":"))
        for page in range(1, pages + 1):
            text = await self._get_html(WEB_LIST_URL, params={"page": page, "search": search})
            m = _NEXT_DATA_RE.search(text)
            if not m:
                raise SourceError("encar: на странице списка нет __NEXT_DATA__ (разметка сменилась?)")
            batch = find_search_items(json.loads(m.group(1)))
            if not batch:
                if page == 1:
                    raise SourceError("encar: в __NEXT_DATA__ не найдено объявлений")
                break
            for item in batch:
                items.setdefault(str(item["Id"]), item)
            if page < pages:
                await asyncio.sleep(0.5)
        return [self.parse_search_item(i) for i in list(items.values())[:limit]]

    @staticmethod
    def _raise_if_blocked(response: httpx.Response) -> None:
        if response.status_code >= 400 and "has_been_cr_blocked" in response.text:
            raise SourceError(
                "encar: IP сервера заблокирован Encar (запросы из облачных сетей/дата-центров не принимаются). "
                "Нужен IP вне дата-центра, см. PROXY_KR в README"
            )

    def _json(self, response: httpx.Response) -> Any:
        self._raise_if_blocked(response)
        return super()._json(response)

    def parse_search_item(self, item: dict[str, Any]) -> Listing:
        car_id = str(item["Id"])
        price_man = to_float(item.get("Price"))
        price = price_man * MAN_WON if price_man is not None else None
        year = to_int(item.get("FormYear")) or (to_int(item.get("Year")) // 100 if item.get("Year") else None)
        make, model = item.get("Manufacturer"), item.get("Model")
        trim = " ".join(filter(None, [item.get("Badge"), item.get("BadgeDetail")])) or None
        photos = _item_photos(item)
        extra = {k: item[k] for k in ("SellType", "Separation", "Trust", "ServiceMark") if item.get(k)}
        if len(photos) > 1:
            extra["photos"] = photos
        return Listing(
            source=self.name,
            external_id=car_id,
            country="KR",
            url=CARD_URL.format(id=car_id),
            title=" ".join(filter(None, [make, model, trim])) or car_id,
            make=make,
            model=model,
            trim=trim,
            year=year,
            mileage_km=to_int(item.get("Mileage")),
            price=price,
            currency=self.currency,
            price_usd=self.settings.to_usd(price, self.currency),
            fuel=item.get("FuelType"),
            transmission=item.get("Transmission"),
            location=item.get("OfficeCityState"),
            photo=_photo_url(item.get("Photo")) or (photos[0] if photos else None),
            listed_at=_parse_date(item.get("ModifiedDate")),
            extra=extra,
        )

    async def fetch_detail(self, listing: Listing) -> Listing:
        if self.mode == "web":
            text = await self._get_html(WEB_CARD_URL.format(id=listing.external_id))
            data = extract_vehicle(text, listing.external_id)
            if data is None:
                raise SourceError(f"encar: в карточке {listing.external_id} не найдены данные автомобиля")
            return self.apply_detail(listing, data)
        data = await self._get_json(f"{API}/v1/readside/vehicle/{listing.external_id}", headers=BROWSER_HEADERS)
        return self.apply_detail(listing, data)

    def apply_detail(self, listing: Listing, data: dict[str, Any]) -> Listing:
        category = data.get("category") or {}
        spec = data.get("spec") or {}
        ad = data.get("advertisement") or {}
        contact = data.get("contact") or {}
        photos = data.get("photos") or []

        update: dict[str, Any] = {
            "vin": (data.get("vin") or "").strip().upper() or None,
            "plate": data.get("vehicleNo") or None,
            "make": category.get("manufacturerName") or listing.make,
            "model": category.get("modelName") or listing.model,
            "trim": category.get("gradeName") or listing.trim,
            "year": to_int(category.get("formYear")) or listing.year,
            "mileage_km": to_int(spec.get("mileage")) or listing.mileage_km,
            "fuel": spec.get("fuelName") or listing.fuel,
            "transmission": spec.get("transmissionName") or listing.transmission,
            "location": contact.get("address") or listing.location,
        }
        price_man = to_float(ad.get("price"))
        if price_man is not None:
            update["price"] = price_man * MAN_WON
            update["price_usd"] = self.settings.to_usd(update["price"], self.currency)
        urls = [_photo_url(p.get("path")) for p in photos if isinstance(p, dict) and p.get("path")]
        urls = [u for u in dict.fromkeys(urls) if u][:30]
        if urls:
            update["photo"] = urls[0]
        extra = dict(listing.extra)
        if data.get("vehicleId"):
            extra["vehicle_id"] = data["vehicleId"]
        if spec.get("colorName"):
            extra["color"] = spec["colorName"]
        if spec.get("displacement"):
            extra["displacement_cc"] = spec["displacement"]
        if urls:
            extra["photos"] = urls
        update["extra"] = extra
        return listing.model_copy(update=update)

    async def collect(self, listing: Listing, with_history: bool = True) -> Listing:
        """Карточка + страховая история в одном объявлении — для удалённого сборщика."""
        listing = await self.fetch_detail(listing)
        if with_history and listing.plate:
            try:
                history = await self.fetch_history(listing)
            except SourceError:
                history = None
            if history:
                history = {k: v for k, v in history.items() if k != "raw"}
                listing = listing.model_copy(update={"extra": {**listing.extra, "history": history}})
        return listing

    async def fetch_history(self, listing: Listing) -> dict[str, Any] | None:
        """Страховая история (аналог carhistory.or.kr), которую Encar показывает в карточке."""
        if not listing.plate:
            listing = await self.fetch_detail(listing)
        if not listing.plate:
            return None
        data = await self._get_json(
            f"{API}/v1/readside/record/vehicle/{listing.external_id}/open",
            params={"vehicleNo": listing.plate},
            headers=BROWSER_HEADERS,
        )
        return self.parse_history(data)

    @staticmethod
    def parse_history(data: dict[str, Any]) -> dict[str, Any]:
        def num(key: str) -> int:
            return to_int(data.get(key)) or 0

        history = {
            "accidents_own": num("myAccidentCnt"),
            "accidents_other": num("otherAccidentCnt"),
            "accident_cost_own_krw": num("myAccidentCost"),
            "accident_cost_other_krw": num("otherAccidentCost"),
            "owner_changes": num("ownerChangeCnt"),
            "plate_changes": num("carNoChangeCnt"),
            "total_loss": num("totalLossCnt"),
            "flood_total_loss": num("floodTotalLossCnt"),
            "flood_partial_loss": num("floodPartLossCnt"),
            "theft": num("robberCnt"),
            "commercial_use": bool(data.get("business") or data.get("government")),
            "raw": data,
        }
        flags = []
        if history["total_loss"]:
            flags.append("Полная гибель (тотал) по данным страховых")
        if history["flood_total_loss"] or history["flood_partial_loss"]:
            flags.append("Утопленник (затопление)")
        if history["theft"]:
            flags.append("Числился в угоне")
        if history["commercial_use"]:
            flags.append("Использовался как коммерческий/гос. транспорт (такси, прокат)")
        if history["accident_cost_own_krw"] >= 5_000_000:
            flags.append("Крупные страховые выплаты по ДТП (от 5 млн вон)")
        history["flags"] = flags
        return history
