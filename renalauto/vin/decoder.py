"""Офлайн-разбор VIN (ISO 3779): формат, контрольный знак, WMI, модельный год."""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field

from . import wmi

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

_TRANSLIT = {
    **{str(d): d for d in range(10)},
    **dict(zip("ABCDEFGH", range(1, 9))),
    **dict(zip("JKLMN", range(1, 6))),
    "P": 7,
    "R": 9,
    **dict(zip("STUVWXYZ", range(2, 10))),
}
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]

# 10-й символ: A=1980 ... Y=2000, 1=2001 ... 9=2009, далее цикл повторяется с 2010.
_YEAR_CODES = "ABCDEFGHJKLMNPRSTVWXY123456789"


class CheckDigit(BaseModel):
    expected: str
    actual: str
    valid: bool
    mandatory: bool  # обязателен в Китае (GB 16735) и Северной Америке


class VinDecoded(BaseModel):
    vin: str
    valid_format: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    wmi: str | None = None
    vds: str | None = None
    vis: str | None = None
    country: str | None = None
    manufacturer: str | None = None
    check_digit: CheckDigit | None = None
    model_year: int | None = None
    model_year_candidates: list[int] = Field(default_factory=list)
    serial: str | None = None


def normalize(vin: str) -> str:
    return re.sub(r"[\s\-]", "", vin or "").upper()


def compute_check_digit(vin: str) -> str:
    total = sum(_TRANSLIT[ch] * w for ch, w in zip(vin, _WEIGHTS))
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def model_year_candidates(code: str, max_year: int | None = None) -> list[int]:
    if code not in _YEAR_CODES:
        return []
    max_year = max_year or date.today().year + 1
    base = 1980 + _YEAR_CODES.index(code)
    return [y for y in (base, base + 30, base + 60) if y <= max_year]


def decode(raw: str, year_hint: int | None = None) -> VinDecoded:
    vin = normalize(raw)
    result = VinDecoded(vin=vin, valid_format=False)

    if len(vin) != 17:
        result.errors.append(f"VIN должен содержать 17 символов, получено {len(vin)}")
        return result
    bad = sorted({ch for ch in vin if ch in "IOQ"})
    if bad:
        result.errors.append(f"Недопустимые символы {', '.join(bad)} (в VIN не используются I, O, Q)")
        return result
    if not VIN_RE.match(vin):
        result.errors.append("VIN содержит недопустимые символы")
        return result

    result.valid_format = True
    result.wmi, result.vds, result.vis = vin[:3], vin[3:9], vin[9:]
    result.country = wmi.region(vin)
    result.manufacturer = wmi.manufacturer(vin)
    result.serial = vin[11:]

    expected = compute_check_digit(vin)
    mandatory = vin[0] in "L12345"
    result.check_digit = CheckDigit(expected=expected, actual=vin[8], valid=expected == vin[8], mandatory=mandatory)
    if not result.check_digit.valid:
        if mandatory:
            result.errors.append(
                f"Контрольный знак не совпадает (9-й символ {vin[8]}, должен быть {expected}) — "
                "VIN с ошибкой или поддельный"
            )
        else:
            result.warnings.append(
                f"Контрольный знак не совпадает (9-й символ {vin[8]}, по ISO 3779 — {expected}). "
                "Для корейского внутреннего рынка это встречается и само по себе не криминал"
            )

    if vin[9] in "UZ0":
        result.warnings.append(f"10-й символ «{vin[9]}» не является кодом модельного года")
    candidates = model_year_candidates(vin[9])
    result.model_year_candidates = candidates
    if candidates:
        if year_hint:
            result.model_year = min(candidates, key=lambda y: abs(y - year_hint))
        else:
            result.model_year = candidates[-1]
    if result.manufacturer is None:
        result.warnings.append(f"Производитель по WMI {result.wmi} не найден в справочнике")
    return result
