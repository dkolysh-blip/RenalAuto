"""Курсы ЦБ РФ (рублей за единицу валюты) с кэшем и запасными значениями из настроек."""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger(__name__)

CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
TTL = 6 * 3600


class Rates:
    def __init__(self, fallback: dict[str, float], client: httpx.AsyncClient | None = None):
        self._rates = dict(fallback)
        self.source = "настройки"
        self.updated_at: float | None = None
        self._client = client

    def rub(self, amount: float | None, currency: str) -> float | None:
        if amount is None:
            return None
        rate = 1.0 if currency == "RUB" else self._rates.get(currency)
        return round(amount * rate) if rate else None

    def get(self, currency: str) -> float | None:
        return self._rates.get(currency)

    async def refresh(self, force: bool = False) -> None:
        if not force and self.updated_at and time.time() - self.updated_at < TTL:
            return
        client = self._client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.get(CBR_URL)
            response.raise_for_status()
            self.apply_cbr(response.json())
        except Exception as exc:  # noqa: BLE001 — остаёмся на прежних курсах
            log.warning("CBR rates refresh failed: %s", exc)
        finally:
            if self._client is None:
                await client.aclose()

    def apply_cbr(self, data: dict) -> None:
        valutes = data.get("Valute") or {}
        for code in ("KRW", "CNY", "USD", "EUR", "JPY"):
            item = valutes.get(code)
            if item and item.get("Value") and item.get("Nominal"):
                self._rates[code] = float(item["Value"]) / float(item["Nominal"])
        self.source = "ЦБ РФ"
        self.updated_at = time.time()

    def as_dict(self) -> dict:
        return {"source": self.source, "rates": {k: round(v, 5) for k, v in self._rates.items()}}
