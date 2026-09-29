"""Описание лота на русском: из названия, комплектации и данных объявления.

Справочник моделей и уровней комплектаций — общеизвестные факты. Оснащение описываем как типовое
(«обычно»): точную комплектацию конкретной машины менеджер сверяет по VIN.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .view import CarView, fmt_int

# Ключ — модель латиницей, как её выдаёт i18n.title (регистр не важен)
MODELS: dict[str, tuple[str, str]] = {
    # модель: (класс/кузов, как известна в России / комментарий)
    "avante": ("компактный седан C-класса", "в России и Европе продавался как Hyundai Elantra"),
    "sonata": ("седан D-класса", "одна из самых популярных моделей Hyundai"),
    "grandeur": ("бизнес-седан E-класса", "флагманский седан марки Hyundai в Корее"),
    "palisade": ("большой трёхрядный кроссовер", "флагманский кроссовер Hyundai на 7–8 мест"),
    "santa fe": ("среднеразмерный кроссовер", "хорошо знаком в России по официальным продажам"),
    "tucson": ("компактный кроссовер", "продавался в России официально"),
    "kona": ("субкомпактный кроссовер", "городской кроссовер с экономичными моторами"),
    "casper": ("городской микро-кроссовер", "компактная машина для города, в Россию официально не поставлялась"),
    "staria": ("минивэн", "преемник Hyundai H-1 / Grand Starex"),
    "starex": ("минивэн", "в России известен как Hyundai H-1 / Grand Starex"),
    "porter": ("малотоннажный грузовик", "популярная коммерческая машина"),
    "ioniq": ("электромобиль", "семейство электрических моделей Hyundai"),
    "accent": ("компактный седан B-класса", "в России продавался как Hyundai Solaris / Accent"),
    "k3": ("компактный седан C-класса", "в России известен как Kia Cerato"),
    "k5": ("седан D-класса", "в России известен как Kia Optima / K5"),
    "k7": ("бизнес-седан E-класса", "в России продавался как Kia Cadenza"),
    "k8": ("бизнес-седан E-класса", "преемник K7, флагманский седан Kia"),
    "k9": ("представительский седан", "в России известен как Kia Quoris / K900"),
    "sorento": ("среднеразмерный кроссовер", "хорошо знаком в России по официальным продажам"),
    "sportage": ("компактный кроссовер", "один из самых популярных кроссоверов Kia"),
    "seltos": ("субкомпактный кроссовер", "продавался в России официально"),
    "carnival": ("большой минивэн", "в России известен как Kia Carnival / Sedona"),
    "morning": ("городской хэтчбек A-класса", "в России известен как Kia Picanto"),
    "ray": ("городской микровэн", "компактная машина с высоким салоном и сдвижной дверью"),
    "mohave": ("рамный внедорожник", "в России продавался как Kia Mohave"),
    "niro": ("компактный кроссовер", "выпускается в гибридной и электрической версиях"),
    "stinger": ("спортивный лифтбек", "продавался в России официально"),
    "bongo": ("малотоннажный грузовик", "коммерческая машина Kia"),
    "g70": ("спортивный седан D-класса", "премиальная марка Genesis"),
    "g80": ("бизнес-седан E-класса", "премиальная марка Genesis"),
    "g90": ("представительский седан", "флагман марки Genesis"),
    "gv70": ("премиальный среднеразмерный кроссовер", "марка Genesis"),
    "gv80": ("большой премиальный кроссовер", "флагманский кроссовер Genesis"),
    "trax": ("субкомпактный кроссовер", "городской кроссовер Chevrolet"),
    "trailblazer": ("компактный кроссовер", "кроссовер Chevrolet корейской сборки"),
    "malibu": ("седан D-класса", "продавался в России официально"),
    "spark": ("городской хэтчбек A-класса", "в России известен как Chevrolet Spark / Ravon R2"),
    "sm6": ("седан D-класса", "корейская версия Renault Talisman"),
    "qm6": ("среднеразмерный кроссовер", "корейская версия Renault Koleos"),
    "xm3": ("кросс-купе", "корейская версия Renault Arkana"),
    "tivoli": ("субкомпактный кроссовер", "модель SsangYong / KG Mobility"),
    "korando": ("компактный кроссовер", "модель SsangYong / KG Mobility"),
    "torres": ("среднеразмерный внедорожник", "модель KG Mobility"),
    "rexton": ("рамный внедорожник", "модель SsangYong / KG Mobility"),
    "camry": ("седан D-класса", "одна из самых востребованных в России моделей Toyota"),
    "corolla": ("компактный седан C-класса", "одна из самых популярных моделей в мире"),
    "tayron": ("среднеразмерный кроссовер", "кроссовер Volkswagen китайской сборки, лидер ввоза из Китая"),
    "han": ("седан бизнес-класса", "флагманский седан BYD"),
    "tang": ("трёхрядный кроссовер", "кроссовер BYD"),
}

# Уровень комплектации по названию: (уровень, что обычно входит)
TRIM_LEVELS: dict[str, tuple[str, str]] = {
    "smart": ("базовая", "базовое оснащение для своего года"),
    "trendy": ("базовая", "базовое оснащение для своего года"),
    "modern": ("средняя", "сбалансированное оснащение: больше комфортных опций, чем в базовой версии"),
    "prestige": ("средняя или высокая", "сбалансированное оснащение: больше комфортных опций, чем в базовой версии"),
    "premium": ("высокая", "расширенное оснащение: заметно больше комфортных опций и ассистентов, чем в средних версиях"),
    "exclusive": ("высокая", "расширенное оснащение: заметно больше комфортных опций и ассистентов, чем в средних версиях"),
    "noblesse": ("высокая", "расширенное оснащение: заметно больше комфортных опций и ассистентов, чем в средних версиях"),
    "luxury": ("высокая", "расширенное оснащение: заметно больше комфортных опций и ассистентов, чем в средних версиях"),
    "inspiration": ("топовая", "максимальное оснащение, доступное для этой модели и года"),
    "calligraphy": ("топовая", "максимальное оснащение, доступное для этой модели и года"),
    "signature": ("топовая", "максимальное оснащение, доступное для этой модели и года"),
    "gravity": ("топовая (спортивное оформление)", "максимальное оснащение, доступное для этой модели и года"),
}

_TITLE_FEATURES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:4WD|AWD|4MATIC|xDrive|quattro|4x4|HTRAC)\b", re.I), "Полный привод"),
    (re.compile(r"\b(?:HEV|гибрид|hybrid)\b", re.I), "Гибрид"),
    (re.compile(r"\bPHEV\b", re.I), "Подключаемый гибрид"),
    (re.compile(r"\b(?:EV|электро)\b", re.I), "Электромобиль"),
    (re.compile(r"\bLPi?\b|газ", re.I), "Газовый двигатель (LPG)"),
    (re.compile(r"\b(\d\.\d)\s*(?:T|Turbo|турбо)\b", re.I), "Турбо"),
]


@dataclass
class Description:
    highlights: list[str] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    meta: str = ""


def _model_info(v: CarView) -> tuple[str, str] | None:
    haystack = f" {(v.model or '')} {v.title} ".lower()
    for key in sorted(MODELS, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", haystack):
            return MODELS[key]
    return None


def _trim_info(v: CarView) -> tuple[str, str, str] | None:
    haystack = v.title.lower()
    for key, (level, text) in TRIM_LEVELS.items():
        if re.search(rf"\b{key}\b", haystack):
            return key.capitalize(), level, text
    return None


def _engine(v: CarView) -> str | None:
    m = re.search(r"(?<![\d.])(\d\.\d)\s*(T|Turbo|турбо)?", v.title, re.I)
    cc = v.eligibility.displacement_cc
    parts = []
    if m:
        parts.append(f"{m.group(1)} л" + (" турбо" if m.group(2) else ""))
    elif cc:
        parts.append(f"{cc / 1000:.1f} л")
    if v.fuel:
        parts.append(v.fuel.lower())
    return ", ".join(parts) or None


def describe(v: CarView, company: str = "Renal Auto", today: date | None = None) -> Description:
    l = v.listing
    d = Description()
    today = today or date.today()

    # --- ключевые метки -------------------------------------------------------------
    for pattern, label in _TITLE_FEATURES:
        if pattern.search(v.title) and label not in d.highlights:
            if label == "Электромобиль" and "Гибрид" in d.highlights:
                continue
            d.highlights.append(label)
    seats = re.search(r"(\d)\s*мест", v.title)
    if seats:
        d.highlights.append(f"{seats.group(1)} мест")
    if v.transmission:
        d.highlights.append(v.transmission)
    per_year = None
    if l.year and l.mileage_km is not None and today.year - l.year >= 2:
        # для совсем новых машин пробег в год по году выпуска не показателен
        years = today.year - l.year + 0.5
        per_year = l.mileage_km / years
        if per_year <= 12_000:
            d.highlights.append("Небольшой пробег")
    history = l.extra.get("history")
    if history and not history.get("flags") and not (history.get("accidents_own") or history.get("accidents_other")):
        d.highlights.append("Без страховых случаев")
    if v.eligibility.age_group == "3–5 лет":
        d.highlights.append("Проходной возраст 3–5 лет")

    # --- абзацы -----------------------------------------------------------------------
    model = _model_info(v)
    year = f" {l.year} года" if l.year else ""
    intro = f"{v.title}{year}"
    if model:
        intro += f" — {model[0]}; {model[1]}."
    else:
        intro += "."
    engine = _engine(v)
    if engine:
        intro += f" Двигатель: {engine}."
    d.paragraphs.append(intro)

    trim = _trim_info(v)
    if trim:
        name, level, text = trim
        d.paragraphs.append(
            f"Комплектация {name} — {level} в линейке. {text[0].upper()}{text[1:]}. "
            "Точный список опций менеджер сверит по VIN перед покупкой."
        )

    facts = []
    if l.mileage_km is not None:
        s = f"пробег {fmt_int(l.mileage_km)} км"
        if per_year is not None:
            s += f" (≈ {fmt_int(per_year)} км в год"
            s += ", меньше среднего)" if per_year <= 12_000 else (", интенсивная эксплуатация)" if per_year > 30_000 else ")")
        facts.append(s)
    if v.color:
        facts.append(f"цвет — {v.color.lower()}")
    if v.city:
        facts.append(f"машина находится в регионе {v.city}")
    if facts:
        d.paragraphs.append("По объявлению: " + "; ".join(facts) + ".")

    if history:
        acc = (history.get("accidents_own") or 0) + (history.get("accidents_other") or 0)
        if history.get("flags"):
            d.paragraphs.append("Внимание: в страховой истории есть отметки — " + "; ".join(history["flags"]).lower() + ".")
        elif acc:
            d.paragraphs.append(f"По страховой истории: {acc} страховых случаев, смен владельца — {history.get('owner_changes', 0)}.")
        else:
            d.paragraphs.append(f"По страховой истории страховых случаев нет, смен владельца — {history.get('owner_changes', 0)}.")

    country = "Кореи" if l.country == "KR" else "Китая"
    price = f"≈ {fmt_int(v.price_rub)} ₽" if v.price_rub else "по запросу"
    where = "Корее" if l.country == "KR" else "Китае"
    if v.eligibility.verdict == "bad":
        d.paragraphs.append(
            f"Цена в {where} {price}. Эту машину не получится привезти в Россию по обычной схеме: "
            f"{v.eligibility.summary.split(': ', 1)[-1].lower()}. {company} подберёт похожую проходную машину."
        )
    else:
        d.paragraphs.append(
            f"Цена в {where} {price} без доставки и растаможки. {v.eligibility.summary}. "
            f"{company} привезёт машину из {country} под ключ: осмотр на месте, выкуп, доставка и оформление документов."
        )

    meta_bits = [v.title + year]
    if model:
        meta_bits.append(model[0])
    if l.mileage_km is not None:
        meta_bits.append(f"пробег {fmt_int(l.mileage_km)} км")
    meta_bits.append(f"цена {price}")
    d.meta = ", ".join(meta_bits) + ". Проверка истории и VIN, доставка под ключ."
    return d
