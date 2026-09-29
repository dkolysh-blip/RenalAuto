"""Справочник WMI (первые 3 символа VIN) для марок, актуальных для Кореи и Китая."""

from __future__ import annotations

# Точные WMI. Список не исчерпывающий — неизвестный WMI не ошибка, просто марка не определяется.
WMI: dict[str, str] = {
    # Южная Корея
    "KMH": "Hyundai",
    "KMF": "Hyundai (коммерческие)",
    "KMJ": "Hyundai (автобусы/микроавтобусы)",
    "KMT": "Genesis",
    "KNA": "Kia",
    "KNC": "Kia (коммерческие)",
    "KND": "Kia (SUV/MPV)",
    "KNE": "Kia (экспортные)",
    "KNM": "Renault Korea (Renault Samsung)",
    "KPA": "SsangYong / KG Mobility",
    "KPT": "SsangYong / KG Mobility",
    # Китай
    "LSV": "SAIC Volkswagen",
    "LFV": "FAW-Volkswagen / Audi",
    "LBV": "BMW Brilliance",
    "LE4": "Beijing Benz",
    "LSG": "SAIC-GM (Buick/Chevrolet/Cadillac)",
    "LSJ": "SAIC Motor (MG/Roewe)",
    "LZW": "SAIC-GM-Wuling",
    "LVS": "Changan Ford",
    "LVR": "Changan Mazda",
    "LS5": "Changan",
    "LVH": "Dongfeng Honda",
    "LHG": "GAC Honda",
    "LVG": "GAC Toyota",
    "LMG": "GAC Motor (Trumpchi/Aion)",
    "LFM": "FAW Toyota",
    "LTV": "FAW Toyota (Tianjin)",
    "LFP": "FAW Car (Hongqi/Bestune)",
    "LGB": "Dongfeng Nissan",
    "LDC": "Dongfeng Peugeot-Citroën",
    "LJD": "Dongfeng Yueda Kia",
    "LBE": "Beijing Hyundai",
    "LNB": "BAIC Motor",
    "LRW": "Tesla (Shanghai)",
    "LGX": "BYD",
    "LC0": "BYD",
    "L6T": "Geely",
    "LB3": "Geely",
    "LYV": "Volvo Cars (China)",
    "LVV": "Chery",
    "LGW": "Great Wall / Haval",
    "LJ1": "JAC (в т.ч. NIO)",
}

# Страна по первым двум символам: (от, до, страна). Диапазоны по ISO 3780.
REGIONS: list[tuple[str, str, str]] = [
    ("KL", "KR", "Южная Корея"),
    ("LA", "L0", "Китай"),
    ("JA", "J0", "Япония"),
    ("WA", "W0", "Германия"),
    ("SA", "SM", "Великобритания"),
    ("VF", "VR", "Франция"),
    ("VS", "VW", "Испания"),
    ("YS", "YW", "Швеция"),
    ("ZA", "ZR", "Италия"),
    ("XL", "XM", "Нидерланды"),
    ("X3", "X0", "Россия"),
    ("TM", "TM", "Чехия"),
    ("MA", "ME", "Индия"),
    ("RF", "RK", "Тайвань"),
    ("1A", "10", "США"),
    ("4A", "40", "США"),
    ("5A", "50", "США"),
    ("2A", "20", "Канада"),
    ("3A", "37", "Мексика"),
]

# Порядок символов во втором знаке диапазона (ISO 3780): A..Z, затем 1..9, 0.
_ORDER = "ABCDEFGHJKLMNPRSTUVWXYZ1234567890"


def region(vin: str) -> str | None:
    first, second = vin[0], vin[1]
    if second not in _ORDER:
        return None
    for start, end, country in REGIONS:
        if first == start[0] and _ORDER.index(start[1]) <= _ORDER.index(second) <= _ORDER.index(end[1]):
            return country
    return None


def manufacturer(vin: str) -> str | None:
    return WMI.get(vin[:3]) or ("GM Korea (Daewoo/Chevrolet)" if vin.startswith("KL") else None)
