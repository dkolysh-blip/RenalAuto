"""KB Chachacha (KB차차차) — площадка б/у авто KB Financial, Южная Корея.

В отличие от Encar, не блокирует облачные IP. Отдаёт HTML:
  * выдача:   https://www.kbchachacha.com/public/search/list.empty?page=1&sort=-orderDate
              (блоки <div class="area" data-car-seq="...">, в data-ga4 — JSON с названием и ценой)
  * карточка: https://www.kbchachacha.com/public/car/detail.kbc?carSeq=...
              (таблица «기본정보»: госномер, год, пробег, топливо, КПП, объём, цвет; цена в 만원)
VIN на площадке не публикуется — только госномер.
"""

from __future__ import annotations

import html
import json
import os
import re
from typing import Any

from ..models import Listing
from .base import Source, SourceError, to_int

BASE = "https://www.kbchachacha.com"
LIST_URL = BASE + "/public/search/list.empty"
CARD_URL = BASE + "/public/car/detail.kbc?carSeq={id}"
MAN_WON = 10_000

_AREA_RE = re.compile(r'<div class="area[^"]*"\s+data-car-seq="(\d+)"')
_GA4_RE = re.compile(r"data-ga4='([^']*)'")
_IMG_RE = re.compile(r'<img[^>]+src="(https://img\.kbchachacha\.com/[^"]+)"')
# "18년04월(19년형)" -> модельный год 2019; "18년04월" -> 2018
_YEAR_RE = re.compile(r"(\d{2})년\s*(\d{2})월(?:\s*\((\d{2})년형\))?")
_KM_RE = re.compile(r"([\d,]+)\s*km")
_PRICE_RE = re.compile(r"([\d,]+)\s*만원")
_TABLE_RE = re.compile(r'<th[^>]*scope="col"[^>]*>\s*([^<]+?)\s*</th>\s*<td[^>]*>\s*(.*?)\s*</td>', re.S)
_TITLE_RE = re.compile(r"<title>\s*(.*?)\s*\|\s*매물번호", re.S)
_OG_IMAGE_RE = re.compile(r'<meta property="og:image" content="([^"]+)"')
_BRAND_RE = re.compile(r'"brand"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"')
_SALE_PRICE_RE = re.compile(r"판매가격</dt>\s*<dd>\s*<strong[^>]*>\s*([\d,]+)\s*만원")
_TAG_RE = re.compile(r"<[^>]+>")
_LD_IMAGES_RE = re.compile(r'"image"\s*:\s*\[(.*?)\]', re.S)
_URL_RE = re.compile(r'"(https?://[^"]+)"')
MAX_PHOTOS = 30


def _unique(urls: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for url in urls:
        seen.setdefault(url, None)
    return list(seen)[:MAX_PHOTOS]


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", fragment))).strip()


def parse_year(text: str | None) -> int | None:
    """Модельный год (년형), иначе год выпуска."""
    if not text:
        return None
    m = _YEAR_RE.search(text)
    if not m:
        return None
    return 2000 + int(m.group(3) or m.group(1))


def parse_price_man(text: str | None) -> float | None:
    if not text:
        return None
    m = _PRICE_RE.search(text)
    return float(m.group(1).replace(",", "")) * MAN_WON if m else None


class KbChachachaSource(Source):
    name = "kbchachacha"
    country = "KR"
    currency = "KRW"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.sort = os.getenv("KBCHACHACHA_SORT", "-orderDate")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Referer": BASE + "/public/search/main.kbc",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "text/html, */*",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }

    async def _get_html(self, url: str, **kwargs: Any) -> str:
        response = await self.client.get(url, headers=self._headers, **kwargs)
        if response.status_code >= 400:
            raise SourceError(f"{self.name}: HTTP {response.status_code} for {response.request.url}")
        return response.text

    async def fetch_latest(self, limit: int = 50, **_: Any) -> list[Listing]:
        listings: dict[str, Listing] = {}
        page = 1
        while len(listings) < limit and page <= 5:
            text = await self._get_html(LIST_URL, params={"page": page, "sort": self.sort})
            batch = self.parse_list(text)
            if not batch:
                if page == 1:
                    raise SourceError("kbchachacha: no listings found in search page (markup changed?)")
                break
            for item in batch:
                listings.setdefault(item.external_id, item)
            page += 1
        return list(listings.values())[:limit]

    def parse_list(self, text: str) -> list[Listing]:
        matches = list(_AREA_RE.finditer(text))
        result = []
        for idx, m in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            result.append(self.parse_list_item(m.group(1), text[m.start() : end]))
        return result

    def parse_list_item(self, car_seq: str, chunk: str) -> Listing:
        info: dict[str, Any] = {}
        ga4 = _GA4_RE.search(chunk)
        if ga4:
            try:
                info = json.loads(html.unescape(ga4.group(1))).get("params", {})
            except ValueError:
                info = {}
        name = (info.get("vehicle_info") or "").strip()
        parts = name.split()
        visible = _text(chunk)
        price = parse_price_man(info.get("vehicle_price")) or parse_price_man(visible)
        km = _KM_RE.search(visible)
        img = _IMG_RE.search(chunk)
        extra: dict[str, Any] = {}
        if info.get("page_area"):
            extra["section"] = info["page_area"]
        photos = _unique(_IMG_RE.findall(chunk))
        if len(photos) > 1:
            extra["photos"] = photos
        return Listing(
            source=self.name,
            external_id=car_seq,
            country="KR",
            url=CARD_URL.format(id=car_seq),
            title=name or car_seq,
            make=parts[0] if parts else None,
            model=parts[1] if len(parts) > 1 else None,
            trim=" ".join(parts[2:]) or None,
            year=parse_year(visible),
            mileage_km=to_int(km.group(1).replace(",", "")) if km else None,
            price=price,
            currency=self.currency,
            price_usd=self.settings.to_usd(price, self.currency),
            photo=img.group(1) if img else None,
            extra=extra,
        )

    async def fetch_detail(self, listing: Listing) -> Listing:
        text = await self._get_html(BASE + "/public/car/detail.kbc", params={"carSeq": listing.external_id})
        return self.apply_detail(listing, text)

    def apply_detail(self, listing: Listing, text: str) -> Listing:
        table = {_text(k): _text(v) for k, v in _TABLE_RE.findall(text)}
        update: dict[str, Any] = {}

        plate = table.get("차량정보")
        if plate and re.search(r"\d", plate):
            update["plate"] = plate
        year = parse_year(table.get("연식"))
        if year:
            update["year"] = year
        km = _KM_RE.search(table.get("주행거리", ""))
        if km:
            update["mileage_km"] = int(km.group(1).replace(",", ""))
        if table.get("연료"):
            update["fuel"] = table["연료"]
        if table.get("변속기"):
            update["transmission"] = table["변속기"]

        sale = _SALE_PRICE_RE.search(text)
        if sale:
            update["price"] = float(sale.group(1).replace(",", "")) * MAN_WON
            update["price_usd"] = self.settings.to_usd(update["price"], self.currency)

        brand = _BRAND_RE.search(text)
        if brand:
            update["make"] = brand.group(1)
        title = _TITLE_RE.search(text)
        if title:
            # "기아 봉고3 · 디젤 · 인천"
            segments = [s.strip() for s in _text(title.group(1)).split("·")]
            if len(segments) >= 3:
                update["location"] = segments[-1]
        og_image = _OG_IMAGE_RE.search(text)
        if og_image and not listing.photo:
            update["photo"] = og_image.group(1)

        extra = dict(listing.extra)
        ld_images = _LD_IMAGES_RE.search(text)
        if ld_images:
            photos = _unique(_URL_RE.findall(ld_images.group(1)))
            if photos:
                extra["photos"] = photos
                if not listing.photo:
                    update["photo"] = photos[0]
        for key, field in (("차종", "body"), ("배기량", "displacement"), ("차량색상", "color"), ("연식", "year_raw")):
            if table.get(key):
                extra[field] = table[key]
        update["extra"] = extra
        return listing.model_copy(update=update)
