"""Encar.com — крупнейшая площадка б/у авто в Южной Корее.

Используются публичные JSON-эндпоинты, которые дергает сам сайт fem.encar.com:
  * поиск:   https://api.encar.com/search/car/list/general
  * карточка: https://api.encar.com/v1/readside/vehicle/{id}           (VIN, госномер)
  * история: https://api.encar.com/v1/readside/record/vehicle/{id}/open (ДТП, владельцы — данные страховых)
Цена в выдаче — в 만원 (10 000 вон).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any

from ..models import Listing
from .base import Source, SourceError, to_float, to_int

API = "https://api.encar.com"
PHOTO_HOST = "https://ci.encar.com"
CARD_URL = "https://fem.encar.com/cars/detail/{id}"

# Отечественные (CarType.Y) и импортные (CarType.N) авто, скрытые объявления исключены.
DEFAULT_QUERIES = "(And.Hidden.N._.CarType.Y.);(And.Hidden.N._.CarType.N.)"

MAN_WON = 10_000


def _photo_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http"):
        return path
    # В выдаче путь без номера кадра: "/carpicture07/pic3812/38123456_"
    if path.endswith("_"):
        path += "001.jpg"
    return PHOTO_HOST + path


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

    async def fetch_latest(self, limit: int = 50, query: str | None = None, **_: Any) -> list[Listing]:
        queries = [query] if query else self.queries
        batches = await asyncio.gather(*(self._search(q, limit) for q in queries))
        listings = [item for batch in batches for item in batch]
        listings.sort(key=lambda l: l.listed_at or datetime.min.astimezone(), reverse=True)
        return listings

    async def _search(self, query: str, limit: int) -> list[Listing]:
        data = await self._get_json(
            f"{API}/search/car/list/general",
            params={"count": "false", "q": query, "sr": f"|ModifiedDate|0|{limit}"},
        )
        results = data.get("SearchResults") if isinstance(data, dict) else None
        if results is None:
            raise SourceError("encar: unexpected search response shape")
        return [self.parse_search_item(item) for item in results if item.get("Id")]

    def parse_search_item(self, item: dict[str, Any]) -> Listing:
        car_id = str(item["Id"])
        price_man = to_float(item.get("Price"))
        price = price_man * MAN_WON if price_man is not None else None
        year = to_int(item.get("FormYear")) or (to_int(item.get("Year")) // 100 if item.get("Year") else None)
        make, model = item.get("Manufacturer"), item.get("Model")
        trim = " ".join(filter(None, [item.get("Badge"), item.get("BadgeDetail")])) or None
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
            photo=_photo_url(item.get("Photo")),
            listed_at=_parse_date(item.get("ModifiedDate")),
            extra={k: item[k] for k in ("SellType", "Separation", "Trust", "ServiceMark") if item.get(k)},
        )

    async def fetch_detail(self, listing: Listing) -> Listing:
        data = await self._get_json(f"{API}/v1/readside/vehicle/{listing.external_id}")
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
        if photos and isinstance(photos[0], dict) and photos[0].get("path"):
            update["photo"] = _photo_url(photos[0]["path"])
        extra = dict(listing.extra)
        if data.get("vehicleId"):
            extra["vehicle_id"] = data["vehicleId"]
        if spec.get("colorName"):
            extra["color"] = spec["colorName"]
        if spec.get("displacement"):
            extra["displacement_cc"] = spec["displacement"]
        update["extra"] = extra
        return listing.model_copy(update=update)

    async def fetch_history(self, listing: Listing) -> dict[str, Any] | None:
        """Страховая история (аналог carhistory.or.kr), которую Encar показывает в карточке."""
        if not listing.plate:
            listing = await self.fetch_detail(listing)
        if not listing.plate:
            return None
        data = await self._get_json(
            f"{API}/v1/readside/record/vehicle/{listing.external_id}/open",
            params={"vehicleNo": listing.plate},
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
