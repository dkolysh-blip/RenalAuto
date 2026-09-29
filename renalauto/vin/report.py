"""Сводная проверка VIN: офлайн-декодирование + сверка с объявлениями + история + внешние сервисы."""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from ..config import Settings
from ..models import Listing
from ..sources import Source
from ..storage import Storage
from .decoder import VinDecoded, decode

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

Verdict = Literal["ok", "warning", "danger"]


class Check(BaseModel):
    name: str
    ok: bool
    detail: str
    severity: Literal["info", "warning", "danger"] = "info"


class VinReport(BaseModel):
    vin: str
    verdict: Verdict
    decoded: VinDecoded
    checks: list[Check] = Field(default_factory=list)
    listings: list[Listing] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    history: dict[str, Any] | None = None
    external: dict[str, Any] = Field(default_factory=dict)


def _aliases_for_manufacturer(manufacturer: str) -> set[str]:
    name = manufacturer.lower()
    return {alias for brand, aliases in BRAND_ALIASES.items() if brand in name for alias in aliases}


def _make_known(make: str) -> bool:
    make = make.lower()
    return any(alias in make for aliases in BRAND_ALIASES.values() for alias in aliases)


def check_make(decoded: VinDecoded, listing: Listing) -> Check | None:
    make = " ".join(filter(None, [listing.make, listing.title]))
    if not decoded.manufacturer or not make or not _make_known(make):
        return None
    aliases = _aliases_for_manufacturer(decoded.manufacturer)
    if not aliases:
        return None
    ok = any(alias in make.lower() for alias in aliases)
    return Check(
        name="make_match",
        ok=ok,
        severity="info" if ok else "danger",
        detail=(
            f"Марка в объявлении ({listing.make}) соответствует WMI ({decoded.manufacturer})"
            if ok
            else f"Марка в объявлении ({listing.make}) НЕ соответствует производителю по VIN ({decoded.manufacturer})"
        ),
    )


def check_year(decoded: VinDecoded, listing: Listing) -> Check | None:
    if not decoded.model_year or not listing.year:
        return None
    # Модельный год может опережать год выпуска/регистрации на 1
    ok = abs(decoded.model_year - listing.year) <= 1
    return Check(
        name="year_match",
        ok=ok,
        severity="info" if ok else "warning",
        detail=f"Модельный год по VIN {decoded.model_year}, в объявлении {listing.year}",
    )


def check_mileage_history(observations: list[dict[str, Any]]) -> list[Check]:
    checks: list[Check] = []
    max_seen: dict[str, Any] | None = None
    for obs in observations:
        mileage = obs.get("mileage_km")
        if mileage is None:
            continue
        if max_seen and max_seen["mileage_km"] - mileage > ROLLBACK_THRESHOLD_KM:
            checks.append(
                Check(
                    name="mileage_rollback",
                    ok=False,
                    severity="danger",
                    detail=(
                        f"Пробег уменьшился: {max_seen['mileage_km']} км ({max_seen['source']}, "
                        f"{max_seen['seen_at']}) -> {mileage} км ({obs['source']}, {obs['seen_at']})"
                    ),
                )
            )
        if max_seen is None or mileage > max_seen["mileage_km"]:
            max_seen = obs
    if not checks and any(o.get("mileage_km") is not None for o in observations):
        checks.append(Check(name="mileage_rollback", ok=True, detail="Скрутки пробега по нашей истории не видно"))
    return checks


def check_relisting(listings: list[Listing]) -> Check | None:
    if len(listings) < 2:
        return None
    places = ", ".join(f"{l.source}#{l.external_id} ({l.price:,.0f} {l.currency})" for l in listings if l.price)
    return Check(
        name="relisted",
        ok=False,
        severity="warning",
        detail=f"Этот VIN встречается в {len(listings)} объявлениях: {places}",
    )


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


async def build_report(
    vin: str,
    *,
    storage: Storage,
    settings: Settings,
    sources: dict[str, Source],
    listing: Listing | None = None,
    http: httpx.AsyncClient | None = None,
) -> VinReport:
    listings = storage.search(vin=vin.upper(), limit=100)
    if listing and all(l.key != listing.key for l in listings):
        listings.insert(0, listing)
    context = listing or (listings[0] if listings else None)
    decoded = decode(vin, year_hint=context.year if context else None)

    checks: list[Check] = []
    for error in decoded.errors:
        checks.append(Check(name="vin_format", ok=False, severity="danger", detail=error))
    for warning in decoded.warnings:
        checks.append(Check(name="vin_format", ok=False, severity="warning", detail=warning))
    if decoded.valid_format and decoded.check_digit and decoded.check_digit.valid:
        checks.append(Check(name="check_digit", ok=True, detail="Контрольный знак VIN корректен"))

    for item in listings:
        for check in (check_make(decoded, item), check_year(decoded, item)):
            if check:
                check.detail = f"[{item.source}#{item.external_id}] {check.detail}"
                checks.append(check)

    observations = storage.observations_for_vin(decoded.vin) if decoded.valid_format else []
    checks.extend(check_mileage_history(observations))
    relisted = check_relisting(listings)
    if relisted:
        checks.append(relisted)

    report = VinReport(vin=decoded.vin, verdict="ok", decoded=decoded, listings=listings, observations=observations)

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
            for flag in history.get("flags", []):
                checks.append(Check(name="history", ok=False, severity="danger", detail=flag))
            accidents = history.get("accidents_own", 0) + history.get("accidents_other", 0)
            if accidents:
                checks.append(
                    Check(
                        name="accidents",
                        ok=False,
                        severity="warning",
                        detail=f"Страховых случаев: {accidents}, смен владельца: {history.get('owner_changes', 0)}",
                    )
                )
            break

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
    if any(c.severity == "danger" for c in checks):
        report.verdict = "danger"
    elif any(c.severity == "warning" for c in checks):
        report.verdict = "warning"
    return report
