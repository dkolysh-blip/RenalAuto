"""Данные для отображения: объявление на русском, цена в ₽, проходимость."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import i18n
from .eligibility import Eligibility, evaluate
from .models import Listing
from .rates import Rates
from .vin.decoder import is_placeholder

SOURCE_NAMES = {
    "kbchachacha": "KB Chachacha",
    "encar": "Encar",
    "dongchedi": "Dongchedi",
    "che168": "Che168",
    "kcar": "K Car",
    "guazi": "Guazi",
}
COUNTRY_NAMES = {"KR": "Корея", "CN": "Китай"}
COUNTRY_FLAGS = {"KR": "🇰🇷", "CN": "🇨🇳"}


def fmt_int(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"{round(value):,}".replace(",", " ")


@dataclass
class CarView:
    listing: Listing
    title: str
    make: str | None
    model: str | None
    fuel: str | None
    transmission: str | None
    city: str | None
    body: str | None
    color: str | None
    price_rub: float | None
    photos: list[str]
    eligibility: Eligibility
    source_name: str
    country_name: str
    flag: str
    specs: list[tuple[str, str]] = field(default_factory=list)

    @property
    def path(self) -> str:
        return f"/car/{self.listing.source}/{self.listing.external_id}"

    @property
    def subtitle(self) -> str:
        parts = []
        if self.listing.year:
            parts.append(f"{self.listing.year} г.")
        if self.listing.mileage_km is not None:
            parts.append(f"{fmt_int(self.listing.mileage_km)} км")
        if self.fuel:
            parts.append(self.fuel)
        if self.city:
            parts.append(self.city)
        return " · ".join(parts)

    @property
    def seo_title(self) -> str:
        year = f" {self.listing.year}" if self.listing.year else ""
        return f"{self.title}{year} из {'Кореи' if self.listing.country == 'KR' else 'Китая'}"

    def as_json(self) -> dict[str, Any]:
        return {
            "listing": self.listing.model_dump(mode="json"),
            "title": self.title,
            "subtitle": self.subtitle,
            "path": self.path,
            "price_rub": self.price_rub,
            "photos": self.photos,
            "eligibility": self.eligibility.model_dump(),
            "source_name": self.source_name,
        }


def car_view(listing: Listing, rates: Rates) -> CarView:
    if listing.vin and is_placeholder(listing.vin):
        # в базе могла остаться заглушка вида 11111111111111111 — не показываем её как VIN
        listing = listing.model_copy(update={"vin": None})
    extra = listing.extra
    title = i18n.title(listing.title) or listing.external_id
    photos = list(extra.get("photos") or [])
    if listing.photo and listing.photo not in photos:
        photos.insert(0, listing.photo)
    eligibility = evaluate(listing)
    view = CarView(
        listing=listing,
        title=title,
        make=i18n.make(listing.make),
        model=i18n.model(listing.model),
        fuel=i18n.fuel(listing.fuel),
        transmission=i18n.transmission(listing.transmission),
        city=i18n.city(listing.location),
        body=i18n.body(extra.get("body")),
        color=i18n.color(extra.get("color")),
        price_rub=rates.rub(listing.price, listing.currency),
        photos=photos,
        eligibility=eligibility,
        source_name=SOURCE_NAMES.get(listing.source, listing.source),
        country_name=COUNTRY_NAMES.get(listing.country, listing.country),
        flag=COUNTRY_FLAGS.get(listing.country, ""),
    )
    specs = [
        ("Год", extra.get("year_raw") and f"{listing.year} (выпуск {extra['year_raw']})" or listing.year),
        ("Пробег", listing.mileage_km is not None and f"{fmt_int(listing.mileage_km)} км"),
        ("Двигатель", eligibility.displacement_cc and f"{fmt_int(eligibility.displacement_cc)} см³"),
        ("Топливо", view.fuel),
        ("Коробка", view.transmission),
        ("Класс / кузов", view.body),
        ("Цвет", view.color),
        ("Город", view.city),
        ("Госномер", listing.plate),
        ("VIN", listing.vin),
        ("Площадка", f"{view.source_name} ({view.country_name})"),
    ]
    view.specs = [(k, str(v)) for k, v in specs if v]
    return view
