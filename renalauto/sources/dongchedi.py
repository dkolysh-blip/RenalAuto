"""Dongchedi (懂车帝, ByteDance) — одна из крупнейших площадок б/у авто в Китае.

Используется JSON-эндпоинт, который вызывает страница https://www.dongchedi.com/usedcar :
  POST https://www.dongchedi.com/motor/pc/sh/sh_sku_list?aid=1839&app_name=auto_web_pc
Цены в выдаче — в 万元 (10 000 юаней), пробег — строкой вида "3.5万公里".
Китайские площадки, как правило, не публикуют VIN целиком: его запрашивают у продавца
и проверяют через /api/vin/{vin}.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

from ..models import Listing
from .base import Source, SourceError, to_float, to_int

LIST_URL = "https://www.dongchedi.com/motor/pc/sh/sh_sku_list"
CARD_URL = "https://www.dongchedi.com/usedcar/{id}"
WAN = 10_000

_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")


def parse_mileage(value: Any) -> int | None:
    """'3.5万公里' -> 35000, '8000公里' -> 8000, 3.5 (число в 万公里) -> 35000."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(value * WAN)) if value < 200 else int(value)
    text = str(value)
    number = to_float(text)
    if number is None:
        return None
    return int(round(number * WAN)) if "万" in text else int(round(number))


def parse_price_wan(value: Any) -> float | None:
    """'12.58' / '12.58万' -> 125800.0 юаней."""
    number = to_float(value)
    if number is None:
        return None
    return round(number * WAN, 2)


class DongchediSource(Source):
    name = "dongchedi"
    country = "CN"
    currency = "CNY"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.city = os.getenv("DONGCHEDI_CITY", "全国")
        # sort_type=4 — «новые объявления» на момент написания; при смене API меняется через env
        self.sort_type = os.getenv("DONGCHEDI_SORT_TYPE", "4")

    async def fetch_latest(self, limit: int = 50, page: int = 1, **_: Any) -> list[Listing]:
        data = await self._post_json(
            LIST_URL,
            params={"aid": "1839", "app_name": "auto_web_pc"},
            data={
                "sh_city_name": self.city,
                "page": str(page),
                "limit": str(limit),
                "sort_type": self.sort_type,
            },
            headers={"Referer": "https://www.dongchedi.com/usedcar"},
        )
        payload = data.get("data") if isinstance(data, dict) else None
        items = (payload or {}).get("search_sh_sku_info_list")
        if items is None:
            raise SourceError("dongchedi: unexpected list response shape")
        return [self.parse_item(item) for item in items if item.get("sku_id")]

    def parse_item(self, item: dict[str, Any]) -> Listing:
        sku_id = str(item["sku_id"])
        price = parse_price_wan(item.get("sh_price"))
        year = to_int(item.get("car_year"))
        title = item.get("title") or " ".join(
            filter(None, [item.get("brand_name"), item.get("series_name"), item.get("car_name")])
        )
        vin = None
        for key in ("vin", "vin_code"):
            if item.get(key) and _VIN_RE.fullmatch(str(item[key]).upper()):
                vin = str(item[key]).upper()
        listed_at = None
        if item.get("publish_time"):
            try:
                listed_at = datetime.fromtimestamp(int(item["publish_time"]), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                listed_at = None
        extra = {}
        if item.get("official_price"):
            extra["new_price_cny"] = parse_price_wan(item["official_price"])
        if item.get("tags"):
            extra["tags"] = [t.get("text") if isinstance(t, dict) else t for t in item["tags"]]
        for key in ("spu_id", "series_id", "car_id"):
            if item.get(key):
                extra[key] = item[key]
        return Listing(
            source=self.name,
            external_id=sku_id,
            country="CN",
            url=CARD_URL.format(id=sku_id),
            title=title or sku_id,
            make=item.get("brand_name"),
            model=item.get("series_name"),
            trim=item.get("car_name"),
            year=year,
            mileage_km=parse_mileage(item.get("car_mileage")),
            price=price,
            currency=self.currency,
            price_usd=self.settings.to_usd(price, self.currency),
            location=item.get("car_source_city_name"),
            photo=item.get("image"),
            vin=vin,
            listed_at=listed_at,
            extra=extra,
        )
