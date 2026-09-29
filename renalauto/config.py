"""Настройки сервиса. Все значения читаются из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "renalauto.db"))
    # Какие площадки опрашивать (имена из renalauto.sources.REGISTRY)
    sources: list[str] = field(default_factory=lambda: _list("SOURCES", "encar,dongchedi"))
    # Интервал опроса каждой площадки, секунды
    poll_interval: int = field(default_factory=lambda: int(os.getenv("POLL_INTERVAL", "60")))
    # Сколько свежих объявлений забирать за один опрос
    poll_limit: int = field(default_factory=lambda: int(os.getenv("POLL_LIMIT", "50")))
    poller_enabled: bool = field(default_factory=lambda: _bool("POLLER_ENABLED", True))
    # Подгружать карточку нового объявления (там VIN, госномер и т.п.)
    enrich_details: bool = field(default_factory=lambda: _bool("ENRICH_DETAILS", True))
    enrich_concurrency: int = field(default_factory=lambda: int(os.getenv("ENRICH_CONCURRENCY", "3")))

    http_timeout: float = field(default_factory=lambda: float(os.getenv("HTTP_TIMEOUT", "20")))
    # Прокси для площадок (китайские сайты часто режут зарубежные IP)
    proxy_kr: str | None = field(default_factory=lambda: os.getenv("PROXY_KR") or None)
    proxy_cn: str | None = field(default_factory=lambda: os.getenv("PROXY_CN") or None)
    user_agent: str = field(
        default_factory=lambda: os.getenv(
            "USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        )
    )

    # Курсы для пересчёта в USD (1 единица валюты = X USD)
    rate_krw_usd: float = field(default_factory=lambda: float(os.getenv("RATE_KRW_USD", "0.00072")))
    rate_cny_usd: float = field(default_factory=lambda: float(os.getenv("RATE_CNY_USD", "0.14")))

    # Проверка VIN во внешнем декодере NHTSA vPIC (бесплатно, без ключа)
    vin_nhtsa: bool = field(default_factory=lambda: _bool("VIN_NHTSA", True))

    telegram_bot_token: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN") or None)
    telegram_chat_id: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID") or None)

    def to_usd(self, amount: float | None, currency: str) -> float | None:
        if amount is None:
            return None
        rate = {"KRW": self.rate_krw_usd, "CNY": self.rate_cny_usd, "USD": 1.0}.get(currency)
        return round(amount * rate, 2) if rate else None
