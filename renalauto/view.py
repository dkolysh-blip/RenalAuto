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


# --- сцена «Порт» на лендинге: машина сверху = кузов + цвет ------------------------

SCENE_COLORS = {
    "Белый": "#eceef0", "Чёрный": "#1c1e22", "Серый": "#8a9099", "Серебристый": "#c3c7cc",
    "Тёмно-серый": "#4b5058", "Перламутровый": "#f2eee4", "Синий": "#2f5fa6", "Красный": "#c62a24",
    "Коричневый": "#6e4b33", "Зелёный": "#3e7a4c", "Жёлтый": "#e2b33c", "Оранжевый": "#e07a2c",
}
# цвета, которых больше всего на рынке, — если площадка цвет не отдала
COMMON_COLORS = ["#eceef0", "#eceef0", "#1c1e22", "#8a9099", "#c3c7cc", "#4b5058"]
SUV_WORDS = (
    "suv", "sportage", "sorento", "tucson", "santa fe", "palisade", "seltos", "niro", "kona", "mohave", "venue",
    "torres", "tivoli", "rexton", "qm6", "trailblazer", "trax", "equinox", "gv70", "gv80", "x1", "x3", "x5", "q3",
    "q5", "glc", "gle", "rav4", "cr-v", "harrier", "highlander", "tiguan", "xc40", "xc60", "song", "tang", "yuan",
    "monjaro", "atlas", "coolray", "tiggo", "jolion", "haval", "h6", "uni-k", "uni-t", "cs35", "cs55", "cs75",
    "li l", "zeekr 7x", "model y", "jimny", "defender", "越野",
)
VAN_WORDS = ("carnival", "staria", "sienna", "odyssey", "alphard", "gl8", "mpv", "starex", "денза d9", "denza d9")
HATCH_WORDS = ("ray", "morning", "spark", "casper", "golf", "polo", "yaris", "dolphin", "seagull", "i30", "mini")


def scene_body(v: CarView) -> str:
    """Силуэт для сцены: sedan / suv / van / hatch."""
    body = (v.body or "").lower()
    if "внедорож" in body or "кроссовер" in body:
        return "suv"
    if "минивэн" in body or "микроавтобус" in body:
        return "van"
    if body in ("микро", "малый класс"):
        return "hatch"
    name = f" {(v.title or '').lower()} {(v.model or '').lower()} "
    for kind, words in (("van", VAN_WORDS), ("suv", SUV_WORDS), ("hatch", HATCH_WORDS)):
        if any(f" {w}" in name for w in words):
            return kind
    return "sedan"


def scene_color(v: CarView) -> str:
    for name, hex_ in SCENE_COLORS.items():
        if v.color and v.color.startswith(name):
            return hex_
    key = sum(map(ord, v.listing.external_id))
    return COMMON_COLORS[key % len(COMMON_COLORS)]


# машины, у которых есть спрайт из настоящей 3D-модели (design/blender/real_cars.py): (марка, слово в модели) → файл
REAL_SPRITES = [
    ("Hyundai", "Tucson", "hyundai-tucson"), ("Hyundai", "Santa Fe", "hyundai-santafe24"), ("Hyundai", "Ioniq 5", "hyundai-ioniq5"),
    ("Chery", "Tiggo 8", "chery-tiggo8"), ("BYD", "Seal", "byd-seal"), ("BYD", "Song", "byd-song"),
    ("Geely", "Monjaro", "geely-monjaro"), ("Geely", "Xingyue L", "geely-monjaro"),
]


SINGLE_PAINT = {"byd-seal", "byd-song", "geely-monjaro", "hyundai-santafe24", "chery-tiggo8"}  # кузов не перекрашивается


def sprite_file(v: CarView, paint: str = "white") -> str:
    """Имя спрайта машины в static/port/cars без расширения: настоящая модель или условный кузов."""
    slug = real_sprite(v)
    if slug:
        return f"{slug}-{'native' if slug in SINGLE_PAINT else paint}"
    return f"{scene_body(v)}-{paint}"


def real_sprite(v: CarView) -> str | None:
    text = f" {v.model or ''} {v.title} ".lower()
    for make, word, slug in REAL_SPRITES:
        if (v.make or "").lower() == make.lower() and word.lower() in text:
            return slug
    return None


def scene_car(v: CarView) -> dict[str, Any]:
    """Короткая запись для сцены терминала (уходит в браузер JSON-ом)."""
    title = v.title
    if v.make and v.model:
        # «Audi A4L», а не «Audi Audi A4L»: в китайских объявлениях модель часто уже начинается с марки
        short = v.model if v.model.lower().startswith(v.make.lower()) else f"{v.make} {v.model}"
        if len(short) < len(title):
            title = short  # на плашке «Kia K5 2020» без комплектации
    return {
        "key": f"{v.listing.source}:{v.listing.external_id}",
        "source": v.listing.source,
        "id": v.listing.external_id,
        "country": v.listing.country,
        "title": title,
        "year": v.listing.year,
        "price": fmt_int(v.price_rub) if v.price_rub else None,
        "photo": v.photos[0] if v.photos else None,
        "path": v.path,
        "verdict": v.eligibility.verdict,
        "body": scene_body(v),
        "color": scene_color(v),
        "model": real_sprite(v),
    }
