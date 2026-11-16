"""Telegram-бот для покупателей: подобрать машину кнопками и оставить заявку менеджеру.

Страна → бюджет с растаможкой → марка → карточки машин с фото и ценой, листаются кнопками.
«Хочу расчёт» просит номер телефона и создаёт такую же заявку, как форма на сайте.
Включается токеном TELEGRAM_CATALOG_BOT_TOKEN — это отдельный бот, не тот, что шлёт заявки менеджерам.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import httpx

log = logging.getLogger(__name__)

BUDGETS = [(1_500_000, "до 1,5 млн ₽"), (2_000_000, "до 2 млн ₽"), (3_000_000, "до 3 млн ₽"),
           (5_000_000, "до 5 млн ₽"), (0, "Любой бюджет")]
COUNTRIES = [("KR", "🇰🇷 Корея"), ("CN", "🇨🇳 Китай"), ("any", "Обе страны")]
LEADS_PER_CHAT, LEADS_WINDOW = 5, 600
PHONE_RE = re.compile(r"^[\d\s()+\-]{7,25}$")
MAX_PHOTO_BYTES = 5_000_000


def rub(value: float | int | None) -> str:
    return f"{round(value):,}".replace(",", " ") if value is not None else "—"


def kb(rows: list[list[tuple[str, str]]]) -> dict:
    """Кнопки под сообщением: (подпись, данные) — данные с «http» становятся ссылкой."""
    return {"inline_keyboard": [[{"text": t, "url": d} if d.startswith("http") else {"text": t, "callback_data": d}
                                 for t, d in row] for row in rows]}


class ShopBot:
    def __init__(
        self,
        token: str | None,
        *,
        find_cars: Callable[[str | None, int | None, str | None], list[dict[str, Any]]],
        top_makes: Callable[[str | None], list[str]],
        create_lead: Callable[..., Awaitable[int | None]],
        site_url: str,
        company: str,
        client: httpx.AsyncClient | None = None,
    ):
        self.token = token
        self.find_cars, self.top_makes, self.create_lead = find_cars, top_makes, create_lead
        self.site_url, self.company = site_url, company
        self.username: str | None = None
        self.last_error: str | None = None
        self.chats: dict[str, dict[str, Any]] = {}
        self._lead_hits: dict[str, deque[float]] = defaultdict(deque)
        self._client = client or httpx.AsyncClient(timeout=40)
        self._task: asyncio.Task | None = None

    def status(self) -> dict:
        return {"bot": bool(self.token), "bot_username": self.username, "last_error": self.last_error}

    # --- Telegram API -----------------------------------------------------------------

    async def _api(self, method: str, files: dict | None = None, **payload) -> dict:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        if files:
            response = await self._client.post(url, data={k: v if isinstance(v, str) else json.dumps(v)
                                                          for k, v in payload.items()}, files=files)
        else:
            response = await self._client.post(url, json=payload)
        data = response.json()
        if not data.get("ok"):
            raise httpx.HTTPError(f"{method}: {data.get('description') or response.status_code}")
        return data

    async def say(self, chat_id: str, text: str, markup: dict | None = None) -> dict | None:
        try:
            return (await self._api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                                    disable_web_page_preview=True, **({"reply_markup": markup} if markup else {})))["result"]
        except (httpx.HTTPError, ValueError) as exc:
            self._note(exc)
            return None

    def _note(self, exc: Exception) -> None:
        self.last_error = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}: {exc}"
        log.warning("shop bot: %s", exc)

    def start(self) -> None:
        if self.token and self._task is None:
            self._task = asyncio.create_task(self._listen())

    async def aclose(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()

    async def _listen(self) -> None:
        offset, pause = 0, 5
        while True:
            try:
                if not self.username:
                    self.username = (await self._api("getMe"))["result"].get("username")
                    await self._api("setMyCommands", commands=[{"command": "start", "description": "Подобрать машину"}])
                updates = (await self._api("getUpdates", offset=offset, timeout=25,
                                           allowed_updates=["message", "callback_query"]))["result"]
                pause = 5
                for update in updates:
                    offset = update["update_id"] + 1
                    try:
                        await self.handle_update(update)
                    except Exception as exc:  # одна сломанная переписка не должна останавливать бота
                        self._note(exc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._note(exc)
                await asyncio.sleep(pause)
                pause = min(pause * 2, 300)

    # --- разговор ---------------------------------------------------------------------

    async def handle_update(self, update: dict) -> None:
        if update.get("callback_query"):
            await self.on_button(update["callback_query"])
        elif update.get("message"):
            await self.on_message(update["message"])

    async def on_message(self, message: dict) -> None:
        chat = message.get("chat") or {}
        if chat.get("type") not in (None, "private") or not chat.get("id"):
            return  # бот для личной переписки; в группах молчит
        chat_id, st = str(chat["id"]), self.chats.get(str(chat["id"]))
        text = (message.get("text") or "").strip()
        phone = (message.get("contact") or {}).get("phone_number") or (text if PHONE_RE.match(text) else None)
        if st and st.get("want") and phone and sum(c.isdigit() for c in phone) >= 10:
            await self.take_lead(chat_id, st, message.get("from") or {}, phone)
        elif st and st.get("want") and not text.startswith("/"):
            await self.say(chat_id, "Не похоже на номер телефона. Нажмите кнопку «Отправить мой номер» внизу "
                                    "или напишите номер цифрами, например +7 914 000-00-00.")
        else:
            await self.welcome(chat_id)

    async def welcome(self, chat_id: str) -> None:
        self.chats[chat_id] = {}
        await self.say(
            chat_id,
            f"Здравствуйте! Это бот компании «{html.escape(self.company)}».\n\n"
            "Покажу машины из Кореи и Китая, которые продаются прямо сейчас и которые можно ввезти в Россию, — "
            "с ориентировочной ценой с растаможкой.\n\n<b>Откуда смотреть машины?</b>",
            kb([[(label, f"c:{code}")] for code, label in COUNTRIES]))

    async def on_button(self, query: dict) -> None:
        chat_id = str(((query.get("message") or {}).get("chat") or {}).get("id") or "")
        data = query.get("data") or ""
        try:
            await self._api("answerCallbackQuery", callback_query_id=query.get("id"))
        except (httpx.HTTPError, ValueError):
            pass
        if not chat_id:
            return
        st = self.chats.get(chat_id)
        kind, _, arg = data.partition(":")
        if kind == "r" or st is None:  # «изменить условия» или бот перезапускался и забыл переписку
            await self.welcome(chat_id)
        elif kind == "c":
            st.update(country=None if arg == "any" else arg, want=None)
            await self.say(chat_id, "<b>Какой бюджет вместе с растаможкой?</b>",
                           kb([[(BUDGETS[0][1], "b:0"), (BUDGETS[1][1], "b:1")], [(BUDGETS[2][1], "b:2"), (BUDGETS[3][1], "b:3")],
                               [(BUDGETS[4][1], "b:4")]]))
        elif kind == "b" and arg.isdigit() and int(arg) < len(BUDGETS):
            st["budget"] = BUDGETS[int(arg)][0] or None
            st["makes"] = self.top_makes(st.get("country"))[:9]
            rows = [[(m, f"m:{i + j}") for j, m in enumerate(st["makes"][i:i + 3])] for i in range(0, len(st["makes"]), 3)]
            await self.say(chat_id, "<b>Какая марка?</b>", kb(rows + [[("Любая марка", "m:any")]]))
        elif kind == "m":
            makes = st.get("makes") or []
            st["make"] = makes[int(arg)] if arg.isdigit() and int(arg) < len(makes) else None
            st["cars"], st["i"] = self.find_cars(st.get("country"), st.get("budget"), st.get("make")), 0
            if st["cars"]:
                await self.show_car(chat_id, st)
            else:
                await self.say(chat_id, "Под эти условия сейчас ничего нет. Объявления обновляются каждый день — "
                                        "менеджер может подобрать машину под ваш бюджет сам.",
                               kb([[("Пусть подберёт менеджер", "w:pick")], [("Изменить условия", "r:")]]))
        elif kind == "n" and st.get("cars"):
            st["i"] = (st["i"] + (1 if arg == "1" else -1)) % len(st["cars"])
            await self.show_car(chat_id, st)
        elif kind == "w":
            car = st["cars"][st["i"]] if arg != "pick" and st.get("cars") else None
            st["want"] = {"source": car["source"], "external_id": car["external_id"], "title": car["title"]} if car else {"pick": True}
            about = f"по машине <b>{html.escape(car['title'])}</b>" if car else "и подберёт варианты"
            await self.say(
                chat_id,
                f"Менеджер посчитает точную цену в вашем городе {about} и свяжется с вами. Это бесплатно.\n\n"
                "Нажмите кнопку внизу, чтобы отправить номер, или напишите его сообщением.\n\n"
                f"Отправляя номер, вы соглашаетесь с <a href=\"{html.escape(self.site_url)}/privacy\">политикой конфиденциальности</a>.",
                {"keyboard": [[{"text": "📱 Отправить мой номер", "request_contact": True}]],
                 "resize_keyboard": True, "one_time_keyboard": True})
        else:
            await self.welcome(chat_id)

    def card(self, st: dict) -> tuple[dict, str, dict]:
        car, n = st["cars"][st["i"]], len(st["cars"])
        facts = " · ".join(str(x) for x in [f"{car['year']} г." if car.get("year") else None,
                                            f"{rub(car['mileage_km'])} км" if car.get("mileage_km") is not None else None,
                                            car.get("fuel"), car.get("city")] if x)
        lines = [f"<b>{html.escape(car['title'])}</b>", html.escape(facts)]
        if car.get("turnkey"):
            lines.append(f"\n<b>≈ {rub(round(car['turnkey'], -4))} ₽</b> с растаможкой")
            if car.get("price_rub"):
                lines.append(f"на площадке ≈ {rub(car['price_rub'])} ₽ · доставку посчитает менеджер")
        elif car.get("price_rub"):
            lines.append(f"\n<b>≈ {rub(car['price_rub'])} ₽</b> на площадке, без растаможки")
        lines.append(f"\n{st['i'] + 1} из {n}" + (" — показаны самые свежие" if car.get("more") else ""))
        nav = [[("◀", "n:0"), ("▶", "n:1")]] if n > 1 else []
        markup = kb(nav + [[("Хочу расчёт по этой машине", "w:car")],
                           [("Все фото и расклад цены", self.site_url + car["path"])], [("Изменить условия", "r:")]])
        return car, "\n".join(lines), markup

    async def show_car(self, chat_id: str, st: dict) -> None:
        car, caption, markup = self.card(st)
        previous, sent = st.get("card_id"), None
        if car.get("photo"):
            try:  # сначала Telegram сам скачивает фото по ссылке; если площадка не отдаёт — скачиваем и загружаем мы
                sent = (await self._api("sendPhoto", chat_id=chat_id, photo=car["photo"], caption=caption,
                                        parse_mode="HTML", reply_markup=markup))["result"]
            except (httpx.HTTPError, ValueError):
                try:
                    image = await self._client.get(car["photo"], timeout=8, follow_redirects=True)
                    if image.status_code == 200 and 0 < len(image.content) <= MAX_PHOTO_BYTES:
                        sent = (await self._api("sendPhoto", files={"photo": ("car.jpg", image.content)}, chat_id=chat_id,
                                                caption=caption, parse_mode="HTML", reply_markup=markup))["result"]
                except (httpx.HTTPError, ValueError) as exc:
                    self._note(exc)
        if sent is None:
            sent = await self.say(chat_id, caption, markup)
        st["card_id"] = (sent or {}).get("message_id")
        if previous and sent:  # одна карточка на экране: прошлую убираем
            try:
                await self._api("deleteMessage", chat_id=chat_id, message_id=previous)
            except (httpx.HTTPError, ValueError):
                pass

    async def take_lead(self, chat_id: str, st: dict, user: dict, phone: str) -> None:
        hits, now = self._lead_hits[chat_id], time.monotonic()
        while hits and now - hits[0] > LEADS_WINDOW:
            hits.popleft()
        want, off = st["want"], {"remove_keyboard": True}
        if len(hits) >= LEADS_PER_CHAT:
            await self.say(chat_id, "Слишком много заявок подряд — попробуйте через несколько минут.", off)
            return
        hits.append(now)
        name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or user.get("username") or "Клиент из Telegram"
        lead_id = await self.create_lead(name=name[:100], phone=phone[:40], username=user.get("username"),
                                         source=want.get("source"), external_id=want.get("external_id"),
                                         budget=st.get("budget"), country=st.get("country"), make=st.get("make"))
        st["want"] = None
        if lead_id is None:
            await self.say(chat_id, "Не получилось сохранить заявку. Позвоните нам, пожалуйста, — номер есть на сайте: "
                                    f"{html.escape(self.site_url)}", off)
            return
        await self.say(chat_id, f"✅ Заявка №{lead_id} принята. Менеджер свяжется с вами по номеру {html.escape(phone)}.", off)
        if st.get("cars"):
            await self.say(chat_id, "Можно смотреть дальше:", kb([[("Продолжить просмотр", "n:1")], [("Изменить условия", "r:")]]))
