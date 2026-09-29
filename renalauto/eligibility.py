"""Проходимость в РФ: можно ли легально вывезти авто и сколько примерно стоит растаможка.

Правила меняются — все пороги здесь, с датой актуальности. Результат ориентировочный:
точный расчёт делает менеджер.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel

from .models import Listing

RULES_AS_OF = "сентябрь 2026"

KOREA_MAX_CC = 2000  # экспортный контроль Кореи: > 2,0 л в РФ вывозить нельзя
KOREA_MAX_USD = 50_000  # и дороже $50 000
LOW_UTIL_MAX_HP = 160  # льготный утильсбор для физлиц — до 160 л.с.
LOW_UTIL_MAX_CC = 3000

Status = Literal["ok", "warn", "bad", "unknown"]

_HYBRID_WORDS = ("하이브리드", "hybrid", "混动", "混合", "增程", "phev", "гибрид")
_EV_WORDS = ("전기", "electric", "纯电", " ev", "электро")


class Badge(BaseModel):
    code: str
    status: Status
    title: str
    detail: str


class Eligibility(BaseModel):
    verdict: Status
    summary: str
    age_group: str | None
    displacement_cc: int | None
    badges: list[Badge]
    rules_as_of: str = RULES_AS_OF


def displacement_cc(listing: Listing) -> int | None:
    raw = listing.extra.get("displacement") or listing.extra.get("displacement_cc")
    if raw:
        digits = re.sub(r"[^\d]", "", str(raw))
        if digits:
            return int(digits)
    # из названия: "2.5T", "1.6 터보", "2.0G"
    m = re.search(r"(?<![\d.])([0-6]\.\d)\s*(?:T|L|G|터보|турбо)?(?![\d])", listing.title or "")
    if m:
        return int(round(float(m.group(1)) * 1000))
    return None


def _has(words: tuple[str, ...], *texts: str | None) -> bool:
    haystack = " " + " ".join(t for t in texts if t).lower()
    return any(w in haystack for w in words)


def age_group(year: int | None, today: date | None = None) -> str | None:
    if not year:
        return None
    age = (today or date.today()).year - year
    if age < 3:
        return "до 3 лет"
    if age <= 5:
        return "3–5 лет"
    return "старше 5 лет"


def evaluate(listing: Listing, today: date | None = None) -> Eligibility:
    badges: list[Badge] = []
    cc = displacement_cc(listing)
    hybrid = _has(_HYBRID_WORDS, listing.fuel, listing.title)
    electric = not hybrid and _has(_EV_WORDS, listing.fuel, listing.title)

    if listing.country == "KR":
        if cc is None:
            badges.append(Badge(code="kr_cc", status="unknown", title="Объём двигателя",
                                detail="Объём не указан — уточнит менеджер (для вывоза из Кореи нужно ≤ 2,0 л)"))
        elif cc > KOREA_MAX_CC:
            badges.append(Badge(code="kr_cc", status="bad", title="Вывоз из Кореи",
                                detail=f"Объём {cc} см³ > 2,0 л — экспорт таких авто в РФ Корея запрещает"))
        else:
            badges.append(Badge(code="kr_cc", status="ok", title="Объём до 2,0 л",
                                detail=f"{cc} см³ — проходит ограничения экспорта Кореи"))
        if listing.price_usd is not None and listing.price_usd > KOREA_MAX_USD:
            badges.append(Badge(code="kr_price", status="bad", title="Вывоз из Кореи",
                                detail="Стоимость > $50 000 — экспорт в РФ запрещён"))
        if hybrid or electric:
            badges.append(Badge(code="kr_hybrid", status="bad", title="Гибрид / электро",
                                detail="Гибриды и электромобили под экспортным контролем Кореи"))
    elif listing.country == "CN":
        badges.append(Badge(code="cn_used", status="ok", title="Вывоз из Китая",
                            detail="Авто с пробегом вывозить можно (ограничение 180 дней — только для новых)"))

    if cc is not None and cc > LOW_UTIL_MAX_CC:
        badges.append(Badge(code="util", status="bad", title="Утильсбор",
                            detail="Объём > 3,0 л — коммерческий утильсбор (сотни тысяч ₽)"))
    else:
        badges.append(Badge(code="util", status="warn", title="Мощность ≤ 160 л.с.?",
                            detail="Льготный утильсбор — только до 160 л.с.; на 161+ л.с. сбор от ~750 тыс. ₽. "
                                   "Мощность проверит менеджер"))

    group = age_group(listing.year, today)
    if group:
        status: Status = "ok" if group == "3–5 лет" else "warn"
        detail = {
            "3–5 лет": "Самая выгодная растаможка для физлица («проходной» возраст)",
            "до 3 лет": "Пошлина — процент от стоимости, обычно дороже, чем для 3–5 лет",
            "старше 5 лет": "Пошлина по объёму двигателя заметно выше",
        }[group]
        badges.append(Badge(code="age", status=status, title=f"Возраст: {group}", detail=detail))

    if any(b.status == "bad" for b in badges):
        verdict: Status = "bad"
        summary = "Не проходит: привезти в РФ по обычной схеме нельзя или слишком дорого"
    elif any(b.status == "unknown" for b in badges):
        verdict = "unknown"
        summary = "Нужно уточнить параметры — менеджер проверит"
    else:
        verdict = "ok" if all(b.status == "ok" for b in badges if b.code != "util") else "warn"
        summary = "Можно привезти — точную цену под ключ рассчитает менеджер"
    return Eligibility(verdict=verdict, summary=summary, age_group=group, displacement_cc=cc, badges=badges)
