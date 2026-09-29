"""Сводная проверка VIN: офлайн-декодирование + сверка с объявлениями + история + внешние сервисы."""

from __future__ import annotations

import logging
import re
import statistics
from datetime import date
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from .. import i18n
from ..config import Settings
from ..models import Listing
from ..sources import Source
from ..storage import Storage
from .decoder import VinDecoded, decode, is_placeholder, normalize

log = logging.getLogger(__name__)

# Бренд (как он встречается в справочнике WMI) -> написания марки на площадках.
BRAND_ALIASES: dict[str, list[str]] = {
    "hyundai": ["hyundai", "현대", "现代", "제네시스"],  # старые Genesis выпускались под WMI Hyundai
    "genesis": ["genesis", "제네시스", "捷尼赛思"],
    "kia": ["kia", "기아", "起亚"],
    "renault": ["renault", "르노", "삼성"],
    "ssangyong": ["ssangyong", "쌍용", "kg모빌리티", "kg mobility", "kgm"],
    "chevrolet": ["chevrolet", "쉐보레", "대우", "gm대우", "雪佛兰"],
    "volkswagen": ["volkswagen", "vw", "폭스바겐", "大众"],
    "audi": ["audi", "아우디", "奥迪"],
    "bmw": ["bmw", "宝马"],
    "benz": ["benz", "mercedes", "벤츠", "奔驰"],
    "buick": ["buick", "别克"],
    "cadillac": ["cadillac", "凯迪拉克"],
    "mg": ["mg", "名爵"],
    "roewe": ["roewe", "荣威"],
    "wuling": ["wuling", "五菱", "宝骏"],
    "ford": ["ford", "포드", "福特"],
    "mazda": ["mazda", "马自达"],
    "changan": ["changan", "长安"],
    "honda": ["honda", "혼다", "本田"],
    "toyota": ["toyota", "도요타", "丰田"],
    "gac motor": ["trumpchi", "aion", "传祺", "埃安", "广汽"],
    "hongqi": ["hongqi", "红旗"],
    "nissan": ["nissan", "닛산", "日产"],
    "peugeot": ["peugeot", "标致"],
    "citroën": ["citroen", "雪铁龙"],
    "baic": ["baic", "北汽", "北京"],
    "tesla": ["tesla", "테슬라", "特斯拉"],
    "byd": ["byd", "比亚迪"],
    "geely": ["geely", "吉利", "领克"],
    "volvo": ["volvo", "볼보", "沃尔沃"],
    "chery": ["chery", "奇瑞"],
    "great wall": ["great wall", "haval", "长城", "哈弗", "坦克"],
    "jac": ["jac", "nio", "江淮", "蔚来"],
}

ROLLBACK_THRESHOLD_KM = 1000
HIGH_KM_PER_YEAR = 30_000  # такси, прокат, коммерческое использование
LOW_KM_PER_YEAR = 3_000  # подозрительно мало для машины старше 4 лет
MIN_MARKET_COMPS = 5

Verdict = Literal["ok", "warning", "danger"]
Severity = Literal["info", "warning", "danger"]


class Check(BaseModel):
    """Одна проверка с расшифровкой: что нашли, что это значит и что делать."""

    name: str
    ok: bool
    detail: str
    severity: Severity = "info"
    title: str = ""
    explain: str = ""
    advice: str = ""


class VinReport(BaseModel):
    vin: str
    query: str = ""
    query_type: Literal["vin", "plate"] = "vin"
    verdict: Verdict
    score: int = 100
    headline: str = ""
    decoded: VinDecoded | None = None
    identity: list[tuple[str, str]] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    listings: list[Listing] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    market: dict[str, Any] | None = None
    history: dict[str, Any] | None = None
    external: dict[str, Any] = Field(default_factory=dict)


def _aliases_for_manufacturer(manufacturer: str) -> set[str]:
    name = manufacturer.lower()
    return {alias for brand, aliases in BRAND_ALIASES.items() if brand in name for alias in aliases}


def _make_known(make: str) -> bool:
    make = make.lower()
    return any(alias in make for aliases in BRAND_ALIASES.values() for alias in aliases)


def _fmt(n: float | int | None) -> str:
    return "—" if n is None else f"{round(n):,}".replace(",", " ")


def check_make(decoded: VinDecoded, listing: Listing) -> Check | None:
    make = " ".join(filter(None, [listing.make, listing.title]))
    if not decoded.manufacturer or not make or not _make_known(make):
        return None
    aliases = _aliases_for_manufacturer(decoded.manufacturer)
    if not aliases:
        return None
    ok = any(alias in make.lower() for alias in aliases)
    if ok:
        return Check(
            name="make_match", ok=True, title="Марка совпадает с VIN",
            detail=f"В объявлении {i18n.make(listing.make)}, по VIN — {decoded.manufacturer}",
            explain="Первые три символа VIN кодируют производителя. Совпадение значит, что VIN относится к этой машине.",
        )
    return Check(
        name="make_match", ok=False, severity="danger", title="Марка НЕ совпадает с VIN",
        detail=f"В объявлении {i18n.make(listing.make)}, а VIN выдан производителем {decoded.manufacturer}",
        explain="VIN от другой машины: ошибка продавца, чужой номер в объявлении или попытка скрыть историю.",
        advice="Не вносить предоплату. Запросить фото VIN с кузова и из техпаспорта.",
    )


def check_year(decoded: VinDecoded, listing: Listing) -> Check | None:
    if not decoded.model_year or not listing.year:
        return None
    # Модельный год может опережать год выпуска/регистрации на 1
    ok = abs(decoded.model_year - listing.year) <= 1
    if ok:
        return Check(
            name="year_match", ok=True, title="Год совпадает с VIN",
            detail=f"Модельный год по VIN {decoded.model_year}, в объявлении {listing.year}",
            explain="10-й символ VIN — модельный год. Разница в 1 год нормальна: модельный год может опережать дату выпуска.",
        )
    return Check(
        name="year_match", ok=False, severity="warning", title="Год не совпадает с VIN",
        detail=f"Модельный год по VIN {decoded.model_year}, в объявлении {listing.year}",
        explain="Машину могли «омолодить» в объявлении или указать год первой регистрации вместо года выпуска.",
        advice="Сверить год по техпаспорту: от возраста зависит таможенная пошлина.",
    )


def check_mileage_history(observations: list[dict[str, Any]]) -> list[Check]:
    checks: list[Check] = []
    max_seen: dict[str, Any] | None = None
    for obs in observations:
        mileage = obs.get("mileage_km")
        if mileage is None:
            continue
        if max_seen and max_seen["mileage_km"] - mileage > ROLLBACK_THRESHOLD_KM:
            checks.append(Check(
                name="mileage_rollback", ok=False, severity="danger", title="Пробег уменьшился — признак скрутки",
                detail=(f"{_fmt(max_seen['mileage_km'])} км ({max_seen['source']}, {str(max_seen['seen_at'])[:10]}) → "
                        f"{_fmt(mileage)} км ({obs['source']}, {str(obs['seen_at'])[:10]})"),
                explain="Эта же машина раньше продавалась с большим пробегом. Честный пробег со временем только растёт.",
                advice="Скорее всего, пробег скручен. Проверить по истории ТО и отчёту CarHistory или отказаться.",
            ))
        if max_seen is None or mileage > max_seen["mileage_km"]:
            max_seen = obs
    if not checks and sum(1 for o in observations if o.get("mileage_km") is not None) > 1:
        checks.append(Check(
            name="mileage_rollback", ok=True, title="Скрутки по нашей истории нет",
            detail=f"Записей о пробеге: {len(observations)}; пробег не уменьшался",
            explain="Мы сохраняем пробег при каждом появлении машины на площадках. Уменьшения не найдено.",
        ))
    return checks


def check_mileage_per_year(listing: Listing, today: date | None = None) -> Check | None:
    if not listing.year or listing.mileage_km is None:
        return None
    years = max(0.5, (today or date.today()).year - listing.year + 0.5)
    per_year = listing.mileage_km / years
    base = f"{_fmt(listing.mileage_km)} км за ~{years:.1f} г. — около {_fmt(per_year)} км в год"
    if per_year > HIGH_KM_PER_YEAR:
        return Check(
            name="mileage_per_year", ok=False, severity="warning", title="Очень большой пробег в год",
            detail=base,
            explain="Обычно в Корее проезжают 12–20 тыс. км в год. Больше 30 тыс. — часто такси, прокат или коммерческая машина.",
            advice="Уточнить, как использовалась машина; проверить отметки такси/прокат в отчёте CarHistory.",
        )
    if per_year < LOW_KM_PER_YEAR and years >= 4:
        return Check(
            name="mileage_per_year", ok=False, severity="warning", title="Подозрительно маленький пробег",
            detail=base,
            explain="Для машины старше 4 лет такой пробег встречается редко и бывает признаком скрутки.",
            advice="Сверить пробег с историей ТО и техосмотров (Автомобиль365 / CarHistory).",
        )
    return Check(
        name="mileage_per_year", ok=True, title="Пробег в норме для возраста", detail=base,
        explain="Средний пробег соответствует обычной личной эксплуатации.",
    )


def check_relisting(listings: list[Listing]) -> Check | None:
    if len(listings) < 2:
        return None
    places = ", ".join(
        f"{l.source} №{l.external_id}" + (f" за {_fmt(l.price)} {l.currency}" if l.price else "") for l in listings[:6]
    )
    return Check(
        name="relisted", ok=False, severity="warning", title="Машина продаётся в нескольких объявлениях",
        detail=f"Найдено объявлений: {len(listings)} — {places}",
        explain="Одну машину выставляют разные дилеры или её перевыставляли после неудачной продажи. "
                "Иногда это значит, что предыдущие покупатели отказались после осмотра.",
        advice="Сравнить цены и описания во всех объявлениях; спросить продавца, почему машина долго продаётся.",
    )


def check_market(listing: Listing, storage: Storage) -> tuple[Check | None, dict[str, Any] | None]:
    if not (listing.make and listing.model and listing.year and listing.price):
        return None, None
    comps = [
        l for l in storage.search(make=listing.make, model=listing.model, year_from=listing.year - 1,
                                  year_to=listing.year + 1, limit=300)
        if l.key != listing.key and l.price and l.currency == listing.currency and (not listing.vin or l.vin != listing.vin)
    ]
    if len(comps) < MIN_MARKET_COMPS:
        return None, None
    median_price = statistics.median(l.price for l in comps)
    diff = listing.price / median_price - 1
    market = {"median": median_price, "count": len(comps), "diff": round(diff * 100, 1), "currency": listing.currency}
    base = (f"Цена {_fmt(listing.price)} {listing.currency}; медиана по {len(comps)} похожим "
            f"({listing.year - 1}–{listing.year + 1} г.) — {_fmt(median_price)} {listing.currency}")
    if diff <= -0.25:
        return Check(
            name="market_price", ok=False, severity="warning", title=f"Цена на {abs(diff) * 100:.0f}% ниже рынка",
            detail=base,
            explain="Слишком низкая цена часто скрывает серьёзное ДТП, утопление, залог или проблемы с документами.",
            advice="Обязательно заказать отчёт CarHistory и осмотр до предоплаты.",
        ), market
    if diff <= -0.05:
        return Check(
            name="market_price", ok=True, title=f"Цена на {abs(diff) * 100:.0f}% ниже рынка", detail=base,
            explain="Выгодное предложение относительно похожих машин в нашей базе.",
        ), market
    if diff >= 0.15:
        return Check(
            name="market_price", ok=True, title=f"Цена на {diff * 100:.0f}% выше рынка", detail=base,
            explain="Дороже похожих машин: возможно, лучшая комплектация или состояние — или есть смысл торговаться.",
        ), market
    return Check(name="market_price", ok=True, title="Цена в рынке", detail=base,
                 explain="Цена близка к медиане похожих машин."), market


async def nhtsa_decode(vin: str, client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get(
        f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}", params={"format": "json"}
    )
    response.raise_for_status()
    results = response.json().get("Results") or [{}]
    wanted = (
        "Make", "Model", "ModelYear", "Trim", "BodyClass", "DriveType", "FuelTypePrimary",
        "DisplacementL", "EngineModel", "PlantCountry", "PlantCity", "ErrorCode", "ErrorText",
    )  # fmt: skip
    return {k: v for k, v in results[0].items() if k in wanted and v not in (None, "", "Not Applicable")}


def _vin_checks(decoded: VinDecoded) -> list[Check]:
    checks = []
    for error in decoded.errors:
        checks.append(Check(
            name="vin_format", ok=False, severity="danger", title="VIN некорректен", detail=error,
            explain="Настоящий VIN всегда из 17 символов без I, O, Q, а в Китае и США обязательно сходится контрольный знак.",
            advice="Перепроверить VIN по фото таблички и техпаспорта. Если ошибка подтвердится — номер поддельный или перебит.",
        ))
    for warning in decoded.warnings:
        checks.append(Check(
            name="vin_format", ok=False, severity="warning", title="Замечание по VIN", detail=warning,
            explain="Не всегда проблема, но требует сверки с документами.",
        ))
    if decoded.valid_format and decoded.check_digit and decoded.check_digit.valid:
        checks.append(Check(
            name="check_digit", ok=True, title="Контрольный знак сходится",
            detail=f"9-й символ «{decoded.check_digit.actual}» совпадает с расчётным",
            explain="Контрольный знак вычисляется из остальных 16 символов. Совпадение говорит, что VIN набран без ошибок "
                    "и, скорее всего, не выдуман.",
        ))
    return checks


def _history_checks(history: dict[str, Any], source_name: str) -> list[Check]:
    checks = []
    for flag in history.get("flags", []):
        checks.append(Check(
            name="history", ok=False, severity="danger", title=flag, detail=f"По данным страховых компаний ({source_name})",
            explain="Официальная запись страховой компании Кореи — это не мнение продавца.",
            advice="Такие машины обычно не берут под перепродажу; если брать — только с глубокой скидкой и после осмотра.",
        ))
    accidents = history.get("accidents_own", 0) + history.get("accidents_other", 0)
    if accidents:
        cost = history.get("accident_cost_own_krw", 0)
        checks.append(Check(
            name="accidents", ok=False, severity="warning", title=f"Страховые случаи: {accidents}",
            detail=(f"По своей вине: {history.get('accidents_own', 0)}"
                    + (f" (выплаты {_fmt(cost)} ₩)" if cost else "")
                    + f"; по чужой: {history.get('accidents_other', 0)}; смен владельца: {history.get('owner_changes', 0)}"),
            explain="Мелкие выплаты (до 1–2 млн ₩) обычно — царапины и бамперы. Крупные — серьёзный ремонт кузова.",
            advice="Попросить у продавца лист диагностики (성능점검) и фото мест ремонта.",
        ))
    else:
        checks.append(Check(
            name="accidents", ok=True, title="Страховых случаев нет",
            detail=f"Смен владельца: {history.get('owner_changes', 0)}",
            explain="В базе страховых компаний нет выплат по этой машине.",
        ))
    return checks


def _identity(decoded: VinDecoded | None, listing: Listing | None, listings: list[Listing]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str | None]] = []
    if listing:
        rows += [
            ("Автомобиль", i18n.title(listing.title)),
            ("Год (объявление)", str(listing.year) if listing.year else None),
        ]
    if decoded and decoded.valid_format:
        rows += [
            ("VIN", decoded.vin),
            ("Производитель по VIN", decoded.manufacturer),
            ("Страна выпуска", decoded.country),
            ("Завод", decoded.plant),
            ("Модельный год по VIN", str(decoded.model_year) if decoded.model_year else None),
            ("Серийный номер", decoded.serial),
        ]
    if listing:
        extra = listing.extra
        cc = extra.get("displacement") or extra.get("displacement_cc")
        rows += [
            ("Двигатель", f"{cc} см³".replace("cc см³", " см³") if cc else None),
            ("Топливо", i18n.fuel(listing.fuel)),
            ("Коробка", i18n.transmission(listing.transmission)),
            ("Цвет", i18n.color(extra.get("color"))),
            ("Госномер", listing.plate),
            ("Пробег (последний)", f"{_fmt(listing.mileage_km)} км" if listing.mileage_km is not None else None),
        ]
    if listings:
        rows.append(("Где встречалась", ", ".join(sorted({l.source for l in listings}))))
    return [(k, v) for k, v in rows if v]


def _finalize(report: VinReport) -> VinReport:
    checks = report.checks
    danger = sum(1 for c in checks if c.severity == "danger")
    warning = sum(1 for c in checks if c.severity == "warning")
    report.score = max(0, min(100, 100 - 35 * danger - 12 * warning))
    if danger:
        report.verdict = "danger"
        report.headline = "Есть серьёзные риски — покупать только после полной проверки"
    elif warning:
        report.verdict = "warning"
        report.headline = "Есть моменты, которые нужно проверить перед покупкой"
    else:
        report.verdict = "ok"
        report.headline = "Явных проблем не найдено"
    # важное — сверху: опасности, затем замечания, затем пройденные проверки
    order = {"danger": 0, "warning": 1, "info": 2}
    report.checks = sorted(checks, key=lambda c: (order[c.severity], c.ok))
    return report


def _history_missing(listing: Listing | None) -> Check:
    return Check(
        name="history_missing", ok=False, severity="info", title="Страховая история не проверена",
        detail="ДТП, выплаты, смены владельцев, тотал, утопление, угон и такси — в отчёте CarHistory (Корея) "
               "или 查博士 (Китай)." + (f" Госномер для запроса: {listing.plate}." if listing and listing.plate else ""),
        explain="Это самая важная часть проверки: открытые данные площадок её не содержат.",
        advice="Оставьте заявку — менеджер закажет официальный отчёт бесплатно.",
    )


async def build_report(
    vin: str,
    *,
    storage: Storage,
    settings: Settings,
    sources: dict[str, Source],
    listing: Listing | None = None,
    http: httpx.AsyncClient | None = None,
) -> VinReport:
    listings = storage.search(vin=normalize(vin), limit=100)
    if listing and all(l.key != listing.key for l in listings):
        listings.insert(0, listing)
    context = listing or (listings[0] if listings else None)
    decoded = decode(vin, year_hint=context.year if context else None)

    checks: list[Check] = _vin_checks(decoded)
    seen_checks: set[str] = set()
    for item in listings:
        for check in (check_make(decoded, item), check_year(decoded, item)):
            if check and (check.name, check.ok) not in seen_checks:
                seen_checks.add((check.name, check.ok))
                if len(listings) > 1:
                    check.detail = f"{check.detail} ({item.source} №{item.external_id})"
                checks.append(check)

    observations = storage.observations_for_vin(decoded.vin) if decoded.valid_format else []
    checks.extend(check_mileage_history(observations))
    relisted = check_relisting(listings)
    if relisted:
        checks.append(relisted)

    report = VinReport(vin=decoded.vin, query=normalize(vin), verdict="ok", decoded=decoded, listings=listings,
                       observations=observations)
    if context:
        per_year = check_mileage_per_year(context)
        if per_year:
            checks.append(per_year)
        market_check, report.market = check_market(context, storage)
        if market_check:
            checks.append(market_check)

    # История от площадки (для Encar — страховые записи о ДТП/владельцах/тотале/угоне)
    for item in listings:
        source = sources.get(item.source)
        stored_history = item.extra.get("history")
        if source is None and not stored_history:
            continue
        try:
            # История, которую уже привёз сборщик, — без повторного запроса к площадке
            history = stored_history or await source.fetch_history(item)
        except Exception as exc:  # noqa: BLE001 — внешний сервис не должен ронять отчёт
            log.warning("history fetch failed for %s: %s", item.key, exc)
            report.external[f"{item.source}_history_error"] = str(exc)
            continue
        if history:
            report.history = {"source": item.source, "external_id": item.external_id, **history}
            checks.extend(_history_checks(history, item.source))
            break
    if report.history is None and decoded.valid_format:
        checks.append(_history_missing(context))

    if settings.vin_nhtsa and decoded.valid_format:
        owns_client = http is None
        client = http or httpx.AsyncClient(timeout=settings.http_timeout)
        try:
            report.external["nhtsa"] = await nhtsa_decode(decoded.vin, client)
        except Exception as exc:  # noqa: BLE001
            report.external["nhtsa_error"] = str(exc)
        finally:
            if owns_client:
                await client.aclose()

    report.checks = checks
    report.identity = _identity(decoded, context, listings)
    return _finalize(report)


PLATE_RE = re.compile(r"^\d{2,3}\s*[가-힣]\s*\d{4}$")


def looks_like_plate(query: str) -> bool:
    return bool(PLATE_RE.match(query.strip()))


async def build_report_for_plate(
    plate: str, *, storage: Storage, settings: Settings, sources: dict[str, Source]
) -> VinReport:
    """Проверка по корейскому госномеру: находим машину в базе; если у неё есть VIN — полный отчёт по VIN."""
    plate_n = re.sub(r"\s+", "", plate)
    listings = storage.search(plate=plate_n, limit=50)
    with_vin = next((l for l in listings if l.vin and not is_placeholder(l.vin)), None)
    if with_vin:
        report = await build_report(with_vin.vin, storage=storage, settings=settings, sources=sources, listing=with_vin)
        report.query, report.query_type = plate_n, "plate"
        return report
    context = listings[0] if listings else None
    checks: list[Check] = []
    if not listings:
        checks.append(Check(
            name="not_found", ok=False, severity="info", title="В нашей базе этого номера нет",
            detail="Машина с таким госномером не встречалась на KB Chachacha и Encar с момента запуска сервиса.",
            explain="База пополняется каждую минуту, но охватывает только свежие объявления.",
            advice="Оставьте заявку — менеджер проверит номер по CarHistory напрямую.",
        ))
    else:
        observations = []
        for l in listings:
            observations += [dict(o, source=l.source) for o in storage.history(l.source, l.external_id)]
        observations.sort(key=lambda o: o["seen_at"])
        checks.extend(check_mileage_history(observations))
        relisted = check_relisting(listings)
        if relisted:
            checks.append(relisted)
        per_year = check_mileage_per_year(context)
        if per_year:
            checks.append(per_year)
        market_check, market = check_market(context, storage)
        if market_check:
            checks.append(market_check)
    checks.append(_history_missing(context or Listing(source="-", external_id="-", country="KR", url="", title="",
                                                      currency="KRW", plate=plate_n)))
    report = VinReport(vin="", query=plate_n, query_type="plate", verdict="ok", listings=listings, checks=checks)
    report.market = market if listings else None
    report.identity = _identity(None, context, listings)
    return _finalize(report)
