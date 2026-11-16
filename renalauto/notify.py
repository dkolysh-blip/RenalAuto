"""Telegram: заявки с сайта менеджерам и уведомления о новых объявлениях по сохранённым фильтрам.

Чат для заявок подключается без правки настроек: в админке — ссылка на бота с кодом, человек нажимает
«Запустить», и заявки начинают приходить ему (или в группу, куда добавили бота). Отключиться — /stop.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import logging
from collections.abc import Callable
from datetime import datetime, timezone

import httpx

from .config import Settings
from .models import LEAD_KIND_LABELS, Lead, ListingEvent, SavedFilter

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


def join_code(admin_token: str | None) -> str | None:
    """Код для ссылки «подключить Telegram»: выводится из пароля админки, сам пароль по нему не восстановить."""
    if not admin_token:
        return None
    return hmac.new(admin_token.encode(), b"telegram-leads", hashlib.sha256).hexdigest()[:20]


class TelegramNotifier:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None, storage=None):
        self.token = settings.telegram_bot_token
        self.default_chat = settings.telegram_chat_id
        self.manager_chat = settings.telegram_manager_chat_id
        self.join_code = join_code(settings.admin_token)
        self.storage = storage
        self.bot_username: str | None = None
        self.last_lead_sent: str | None = None
        self.last_error: str | None = None
        self._client = client or httpx.AsyncClient(timeout=40)
        self._task: asyncio.Task | None = None

    def lead_chats(self) -> list[str]:
        """Куда уходят заявки: чат из настроек (если задан) и все подключённые ссылкой из админки."""
        chats = [self.manager_chat or self.default_chat] if (self.manager_chat or self.default_chat) else []
        if self.storage is not None:
            chats += [c["chat_id"] for c in self.storage.tg_chats()]
        return list(dict.fromkeys(str(c) for c in chats))

    def status(self) -> dict:
        return {"bot": bool(self.token), "bot_username": self.bot_username, "chats": len(self.lead_chats()),
                "last_lead_sent": self.last_lead_sent, "last_error": self.last_error}

    async def _api(self, method: str, **payload) -> dict:
        response = await self._client.post(f"https://api.telegram.org/bot{self.token}/{method}", json=payload)
        data = response.json()
        if not data.get("ok"):
            raise httpx.HTTPError(f"{method}: {data.get('description') or response.status_code}")
        return data

    async def send_text(self, chat_id: str, text: str) -> bool:
        try:
            await self._api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)
            return True
        except (httpx.HTTPError, ValueError) as exc:
            self.last_error = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}: {exc}"
            log.warning("telegram send to %s failed: %s", chat_id, exc)
            return False

    # --- бот: подключение чатов командой /start <код> -------------------------------------

    def start(self) -> None:
        if self.token and self.storage is not None and self._task is None:
            self._task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        offset, pause = 0, 5
        while True:
            try:
                if not self.bot_username:
                    self.bot_username = (await self._api("getMe"))["result"].get("username")
                updates = (await self._api("getUpdates", offset=offset, timeout=25, allowed_updates=["message"]))["result"]
                pause = 5
                for update in updates:
                    offset = update["update_id"] + 1
                    await self.handle_message(update.get("message") or {})
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # сеть, неверный токен, второй получатель обновлений — ждём и пробуем снова
                self.last_error = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}: {exc}"
                log.warning("telegram bot: %s", exc)
                await asyncio.sleep(pause)
                pause = min(pause * 2, 300)

    async def handle_message(self, message: dict) -> None:
        chat, text = message.get("chat") or {}, (message.get("text") or "").strip()
        if not chat.get("id") or not text.startswith("/"):
            return
        command, _, arg = text.partition(" ")
        command = command.split("@")[0].lower()
        chat_id = str(chat["id"])
        name = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")])) \
            or chat.get("username") or chat_id
        if command == "/start":
            if self.join_code and hmac.compare_digest(arg.strip(), self.join_code):
                self.storage.add_tg_chat(chat_id, name)
                await self.send_text(chat_id, "✅ Готово: заявки с сайта будут приходить сюда. Отключить — /stop")
            elif chat_id in self.lead_chats():
                await self.send_text(chat_id, "Этот чат уже получает заявки с сайта. Отключить — /stop")
            else:
                await self.send_text(chat_id, "Чтобы получать заявки с сайта, откройте ссылку «Подключить Telegram» в админке сайта.")
        elif command == "/stop":
            removed = self.storage.remove_tg_chat(chat_id)
            await self.send_text(chat_id, "Заявки сюда больше не приходят." if removed else "Этот чат не был подключён.")

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
        chats = self.lead_chats()
        if not self.token or not chats:
            return False
        kind = LEAD_KIND_LABELS.get(lead.kind or "", "Заявка")
        lines = [f"🔥 <b>{kind} — заявка #{lead.id}</b>"]
        if lead.listing_title:
            car = html.escape(lead.listing_title)
            if site_url and lead.source and lead.external_id:
                car = f'<a href="{html.escape(site_url)}/car/{lead.source}/{lead.external_id}">{car}</a>'
            lines.append(f"🚗 {car}")
            if lead.listing_url:
                lines.append(f'Оригинал: <a href="{html.escape(lead.listing_url)}">{html.escape(lead.source or "")}</a>')
            if lead.kind == "history" and lead.plate:
                lines.append(f"🔎 Госномер для CarHistory: <code>{html.escape(lead.plate)}</code>")
        else:
            lines.append("🚗 Подбор под бюджет")
        lines.append(f"👤 {html.escape(lead.name)}")
        if lead.phone:
            lines.append(f"📞 {html.escape(lead.phone)}")
        if lead.telegram:
            lines.append(f"💬 MAX: {html.escape(lead.telegram)}")
        if lead.city:
            lines.append(f"📍 {html.escape(lead.city)}")
        if lead.budget_rub:
            lines.append(f"💰 до {lead.budget_rub:,} ₽".replace(",", " "))
        if lead.comment:
            lines.append(f"💬 {html.escape(lead.comment)}")
        results = [await self.send_text(chat_id, "\n".join(lines)) for chat_id in chats]
        if any(results):
            self.last_lead_sent = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return any(results)

    async def aclose(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()
