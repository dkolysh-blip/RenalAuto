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


def _int_or_none(name: str) -> int | None:
    value = (os.getenv(name) or "").replace(" ", "")
    return int(value) if value else None


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
    # Максимум загрузок карточек за один опрос (новые + догрузка неудавшихся)
    enrich_per_poll: int = field(default_factory=lambda: int(os.getenv("ENRICH_PER_POLL", "60")))

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
    # Куда приходят заявки с сайта (если не задан — в TELEGRAM_CHAT_ID)
    telegram_manager_chat_id: str | None = field(
        default_factory=lambda: os.getenv("TELEGRAM_MANAGER_CHAT_ID") or None
    )
    # Токен для служебных функций: заявки, фильтры, ручной опрос. Без него они открыты всем!
    admin_token: str | None = field(default_factory=lambda: os.getenv("ADMIN_TOKEN") or None)
    # Токен удалённых сборщиков (Encar с корейского IP). Пусто — приём данных выключен
    ingest_token: str | None = field(default_factory=lambda: os.getenv("INGEST_TOKEN") or None)
    # Публичный адрес сайта — для ссылок в Telegram и sitemap.xml
    site_url: str = field(default_factory=lambda: os.getenv("SITE_URL", "https://renal-auto.asia:8443").rstrip("/"))
    company_name: str = field(default_factory=lambda: os.getenv("COMPANY_NAME", "Ренал Авто"))
    company_phone: str | None = field(default_factory=lambda: os.getenv("COMPANY_PHONE", "+7 (914) 066-88-08") or None)
    # бесплатный номер 8 800 — в шапке и подвале; мобильный COMPANY_PHONE остаётся для SMS и в подвале
    company_hotline: str | None = field(default_factory=lambda: os.getenv("COMPANY_HOTLINE", "8 800 250-57-78") or None)
    company_email: str | None = field(
        default_factory=lambda: os.getenv("COMPANY_EMAIL", "renal_auto@mail.ru") or None
    )
    # Реквизиты юрлица для подвала сайта
    company_legal_name: str | None = field(
        default_factory=lambda: os.getenv("COMPANY_LEGAL_NAME", "ООО «ГАРАНТ-ЛОГИСТИКА»") or None
    )
    company_requisites: str | None = field(
        default_factory=lambda: os.getenv(
            "COMPANY_REQUISITES", "ИНН 2543160025 / КПП 254001001 · ОГРН 1212500021271"
        )
        or None
    )
    company_address: str | None = field(
        default_factory=lambda: os.getenv(
            "COMPANY_ADDRESS", "690078, Приморский край, г. Владивосток, ул. Мыс Чумака, д. 1а, стр. 3"
        )
        or None
    )
    # Мессенджер MAX: ссылка на профиль или канал компании (https://max.ru/…). Пусто — кнопки MAX не показываются
    company_max: str | None = field(default_factory=lambda: os.getenv("COMPANY_MAX", "https://max.ru/channel_renalauto") or None)
    # Яндекс Метрика: номер счётчика. Пусто — счётчик на сайт не ставится
    ym_id: int | None = field(default_factory=lambda: _int_or_none("YM_ID") if os.getenv("YM_ID") is not None else 113699503)
    company_vk: str | None = field(default_factory=lambda: os.getenv("COMPANY_VK", "https://vk.ru/renal_auto") or None)
    # профиль на Авито: пусто — значка нет
    company_avito: str | None = field(default_factory=lambda: os.getenv("COMPANY_AVITO") or None)
    company_2gis: str | None = field(
        default_factory=lambda: os.getenv("COMPANY_2GIS", "https://2gis.ru/vladivostok/geo/70000001101310074") or None
    )
    # Отзывы из 2ГИС для блока отзывов: рейтинг и число отзывов (их видно на странице компании в 2ГИС)
    company_2gis_rating: str | None = field(default_factory=lambda: os.getenv("COMPANY_2GIS_RATING", "5,0") or None)
    company_2gis_reviews: int | None = field(default_factory=lambda: _int_or_none("COMPANY_2GIS_REVIEWS") or 29)
    # Условия агентского договора — показываются на лендинге (как проходит сделка, FAQ)
    deal_fee_rub: int = field(default_factory=lambda: int(os.getenv("DEAL_FEE_RUB", "50000")))
    deal_deposit_rub: int = field(default_factory=lambda: int(os.getenv("DEAL_DEPOSIT_RUB", "120000")))
    deal_pick_days: int = field(default_factory=lambda: int(os.getenv("DEAL_PICK_DAYS", "20")))
    deal_invoice_days: int = field(default_factory=lambda: int(os.getenv("DEAL_INVOICE_DAYS", "10")))
    deal_delivery_weeks: int = field(default_factory=lambda: int(os.getenv("DEAL_DELIVERY_WEEKS", "8")))
    # Для калькулятора под ключ: доставка до Владивостока и оформление (СБКТС, ЭПТС, брокер), ₽.
    # Пусто — в расчёте «назовёт менеджер»
    deal_logistics_kr_rub: int | None = field(default_factory=lambda: _int_or_none("DEAL_LOGISTICS_KR_RUB"))
    deal_logistics_cn_rub: int | None = field(default_factory=lambda: _int_or_none("DEAL_LOGISTICS_CN_RUB"))
    deal_papers_rub: int | None = field(default_factory=lambda: _int_or_none("DEAL_PAPERS_RUB"))
    # Брать курсы с cbr-xml-daily.ru (иначе — значения RATE_*_RUB ниже)
    rates_live: bool = field(default_factory=lambda: _bool("RATES_LIVE", True))
    rate_krw_rub: float = field(default_factory=lambda: float(os.getenv("RATE_KRW_RUB", "0.058")))
    rate_cny_rub: float = field(default_factory=lambda: float(os.getenv("RATE_CNY_RUB", "11.2")))
    rate_usd_rub: float = field(default_factory=lambda: float(os.getenv("RATE_USD_RUB", "80")))
    rate_eur_rub: float = field(default_factory=lambda: float(os.getenv("RATE_EUR_RUB", "93")))

    def to_usd(self, amount: float | None, currency: str) -> float | None:
        if amount is None:
            return None
        rate = {"KRW": self.rate_krw_usd, "CNY": self.rate_cny_usd, "USD": 1.0}.get(currency)
        return round(amount * rate, 2) if rate else None
