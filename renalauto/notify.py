"""Уведомления в Telegram о новых объявлениях, подходящих под сохранённые фильтры."""

from __future__ import annotations

import html
import logging

import httpx

from .config import Settings
from .models import Lead, ListingEvent, SavedFilter

log = logging.getLogger(__name__)


def format_event(event: ListingEvent, flt: SavedFilter) -> str:
    l = event.listing
    lines = [f"<b>{html.escape(flt.name)}</b>"]
    if event.type == "price_changed" and event.old_price:
        lines.append(f"💸 Цена изменилась: {event.old_price:,.0f} → {l.price:,.0f} {l.currency}")
    else:
        lines.append("🆕 Новое объявление")
    lines.append(f"<a href=\"{html.escape(l.url)}\">{html.escape(l.title)}</a>")
    facts = []
    if l.year:
        facts.append(str(l.year))
    if l.mileage_km is not None:
        facts.append(f"{l.mileage_km:,} км".replace(",", " "))
    if l.price:
        price = f"{l.price:,.0f} {l.currency}".replace(",", " ")
        if l.price_usd:
            price += f" (~${l.price_usd:,.0f})".replace(",", " ")
        facts.append(price)
    if l.location:
        facts.append(html.escape(l.location))
    lines.append(" · ".join(facts))
    if l.vin:
        lines.append(f"VIN: <code>{l.vin}</code>")
    return "\n".join(lines)


class TelegramNotifier:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.token = settings.telegram_bot_token
        self.default_chat = settings.telegram_chat_id
        self.manager_chat = settings.telegram_manager_chat_id
        self._client = client or httpx.AsyncClient(timeout=15)

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    async def send(self, event: ListingEvent, flt: SavedFilter) -> None:
        chat_id = flt.telegram_chat_id or self.default_chat
        if not self.token or not chat_id:
            return
        try:
            response = await self._client.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": chat_id, "text": format_event(event, flt), "parse_mode": "HTML"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("telegram send failed: %s", exc)

    async def send_lead(self, lead: Lead, site_url: str | None = None) -> bool:
        """Новая заявка — сразу менеджеру."""
        chat_id = self.manager_chat or self.default_chat
        if not self.token or not chat_id:
            return False
        lines = [f"🔥 <b>Заявка #{lead.id}</b>"]
        if lead.listing_title:
            car = html.escape(lead.listing_title)
            if site_url and lead.source and lead.external_id:
                car = f'<a href="{html.escape(site_url)}/car/{lead.source}/{lead.external_id}">{car}</a>'
            lines.append(f"🚗 {car}")
            if lead.listing_url:
                lines.append(f'Оригинал: <a href="{html.escape(lead.listing_url)}">{html.escape(lead.source or "")}</a>')
        else:
            lines.append("🚗 Подбор под бюджет")
        lines.append(f"👤 {html.escape(lead.name)}")
        if lead.phone:
            lines.append(f"📞 {html.escape(lead.phone)}")
        if lead.telegram:
            lines.append(f"✈️ {html.escape(lead.telegram)}")
        if lead.city:
            lines.append(f"📍 {html.escape(lead.city)}")
        if lead.budget_rub:
            lines.append(f"💰 до {lead.budget_rub:,} ₽".replace(",", " "))
        if lead.comment:
            lines.append(f"💬 {html.escape(lead.comment)}")
        try:
            response = await self._client.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": chat_id, "text": "\n".join(lines), "parse_mode": "HTML",
                      "disable_web_page_preview": True},
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.warning("telegram lead send failed: %s", exc)
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
