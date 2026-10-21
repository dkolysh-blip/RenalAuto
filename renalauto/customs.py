"""Растаможка для физлица (личное пользование) и цена под ключ — для калькулятора на лендинге.

Ставки — по старому калькулятору Renal Auto (июнь 2026): пошлина по ЕТС (Решение Совета ЕЭК № 107),
утильсбор (ПП РФ № 1713 с изменениями с 01.12.2025), таможенный сбор за оформление.
Результат ориентировочный: итог подтверждает менеджер.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .eligibility import LOW_UTIL_MAX_CC, LOW_UTIL_MAX_HP

Age = Literal["new", "mid", "old"]  # до 3 лет / 3–5 лет / старше 5
Engine = Literal["ice", "hybrid", "ev"]

LOW_UTIL_RUB = {"new": 3400, "mid": 5200, "old": 5200}
LOW_UTIL_MAX_HP_ELECTRIC = 80  # для гибридов и электро льгота — до 80 л.с.
COMMERCIAL_UTIL_FROM_RUB = 750_000  # на 161+ л.с. сбор считается по коммерческой шкале

# до 3 лет: (стоимость до, €) -> (% от стоимости, минимум € за см³)
DUTY_NEW = [(8500, 0.54, 2.5), (16700, 0.48, 3.5), (42300, 0.48, 5.5), (84500, 0.48, 7.5), (169000, 0.48, 15.0),
            (float("inf"), 0.48, 20.0)]
# 3–5 и старше 5 лет: (объём до, см³) -> € за см³
DUTY_MID = [(1000, 1.5), (1500, 1.7), (1800, 2.5), (2300, 2.7), (3000, 3.0), (float("inf"), 3.6)]
DUTY_OLD = [(1000, 3.0), (1500, 3.2), (1800, 3.5), (2300, 4.8), (3000, 5.0), (float("inf"), 5.7)]
# таможенный сбор за оформление: (стоимость до, ₽) -> ₽
CUSTOMS_FEE = [(200_000, 1067), (450_000, 2134), (1_200_000, 4269), (2_700_000, 11746), (4_200_000, 16524),
               (5_500_000, 21344), (7_000_000, 27540), (float("inf"), 30000)]


def duty_rub(price_rub: float, cc: int, age: Age, eur_rub: float) -> float:
    if age == "new":
        value_eur = price_rub / eur_rub
        pct, per_cc = next((p, c) for limit, p, c in DUTY_NEW if value_eur <= limit)
        return max(pct * price_rub, per_cc * cc * eur_rub)
    table = DUTY_MID if age == "mid" else DUTY_OLD
    per_cc = next(rate for limit, rate in table if cc <= limit)
    return per_cc * cc * eur_rub


def customs_fee_rub(price_rub: float) -> int:
    return next(fee for limit, fee in CUSTOMS_FEE if price_rub <= limit)


def low_util_applies(engine: Engine, hp: int, cc: int) -> bool:
    if engine in ("hybrid", "ev"):
        return hp <= LOW_UTIL_MAX_HP_ELECTRIC
    return hp <= LOW_UTIL_MAX_HP and cc <= LOW_UTIL_MAX_CC


class Line(BaseModel):
    title: str
    rub: int | None  # None — сумму назовёт менеджер
    note: str | None = None


class TurnkeyCalc(BaseModel):
    passable: bool
    verdict: str
    lines: list[Line]
    total_rub: int | None  # без неизвестных строк; см. total_is_from
    total_is_from: bool  # «от …»: часть сумм уточнит менеджер


def turnkey(
    *,
    price_rub: float,
    cc: int,
    hp: int,
    age: Age,
    engine: Engine,
    eur_rub: float,
    fee_rub: int,
    logistics_rub: int | None = None,
    papers_rub: int | None = None,
) -> TurnkeyCalc:
    passable = low_util_applies(engine, hp, cc)
    if passable:
        verdict = "Проходной: льготный утильсбор для личного пользования"
    elif engine in ("hybrid", "ev"):
        verdict = f"Непроходной: мощность выше {LOW_UTIL_MAX_HP_ELECTRIC} л.с. — коммерческий утильсбор"
    elif cc > LOW_UTIL_MAX_CC:
        verdict = "Непроходной: объём больше 3,0 л — коммерческий утильсбор"
    else:
        verdict = f"Непроходной: мощность выше {LOW_UTIL_MAX_HP} л.с. — коммерческий утильсбор"

    lines = [Line(title="Автомобиль", rub=round(price_rub))]
    if engine == "ev":
        lines.append(Line(title="Таможенная пошлина", rub=None, note="для электромобилей считается отдельно"))
    else:
        lines.append(Line(title="Таможенная пошлина (ЕТС)", rub=round(duty_rub(price_rub, cc, age, eur_rub))))
    if passable:
        lines.append(Line(title="Утилизационный сбор", rub=LOW_UTIL_RUB[age]))
    else:
        lines.append(Line(title="Утилизационный сбор", rub=COMMERCIAL_UTIL_FROM_RUB, note="от этой суммы"))
    lines.append(Line(title="Таможенный сбор", rub=customs_fee_rub(price_rub)))
    lines.append(Line(title="Доставка до Владивостока", rub=logistics_rub,
                      note=None if logistics_rub is not None else "зависит от страны и порта — назовёт менеджер"))
    lines.append(Line(title="СБКТС, ЭПТС, брокер", rub=papers_rub,
                      note=None if papers_rub is not None else "назовёт менеджер"))
    lines.append(Line(title="Наше вознаграждение", rub=fee_rub, note="не больше этой суммы"))

    known = [l.rub for l in lines if l.rub is not None]
    total_is_from = not passable or any(l.rub is None for l in lines)
    return TurnkeyCalc(passable=passable, verdict=verdict, lines=lines, total_rub=sum(known), total_is_from=total_is_from)
