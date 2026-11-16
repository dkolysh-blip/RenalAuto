import asyncio
import json

import httpx

from renalauto.shopbot import ShopBot

from .conftest import ADMIN
from .test_site import kb, make_client


def test_customer_bot_picks_a_car_and_leaves_a_lead(settings):
    k5 = kb(external_id="2", title="기아 K5 1.6 터보", make="기아", model="K5", extra={"displacement": "1,598cc"})
    ray = kb(external_id="3", title="기아 레이 1.0", make="기아", model="레이", price=9_000_000, price_usd=6_500,
             extra={"displacement": "998cc"})
    client, app = make_client(settings, [kb(), k5, ray])  # первая — Palisade 3.8: в РФ не проходит
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content) if request.headers.get("content-type", "").startswith("application/json") else {}
        calls.append((method, body))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(calls)}})

    old = app.state.shop
    bot = ShopBot("1:x", find_cars=old.find_cars, top_makes=old.top_makes, create_lead=old.create_lead,
                  site_url=settings.site_url, company=settings.company_name,
                  client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    chat = {"id": 7, "type": "private"}
    user = {"first_name": "Анна", "username": "anna"}

    def press(data):
        asyncio.run(bot.handle_update({"callback_query": {"id": "q", "data": data, "message": {"chat": chat}}}))

    def write(**message):
        asyncio.run(bot.handle_update({"message": {"chat": chat, "from": user, **message}}))

    def last(method):
        return [body for m, body in calls if m == method][-1]

    try:
        write(text="/start")
        assert "Откуда смотреть" in last("sendMessage")["text"]
        press("c:KR")
        assert "бюджет" in last("sendMessage")["text"]
        press("b:4")  # любой бюджет
        makes = [b["text"] for row in last("sendMessage")["reply_markup"]["inline_keyboard"] for b in row]
        assert "Kia" in makes and "Любая марка" in makes

        press(f"m:{makes.index('Kia')}")
        card = last("sendPhoto")
        assert "Kia" in card["caption"] and "с растаможкой" in card["caption"] and "1 из 2" in card["caption"]
        assert "Palisade" not in json.dumps(calls, ensure_ascii=False)  # непроходную не предлагаем
        press("n:1")
        assert "2 из 2" in last("sendPhoto")["caption"] and calls[-1][0] == "deleteMessage"

        press("w:car")
        assert last("sendMessage")["reply_markup"]["keyboard"][0][0]["request_contact"] is True
        write(text="позвоните мне")
        assert "Не похоже на номер" in last("sendMessage")["text"]
        write(contact={"phone_number": "+79140000000"})
        assert "принята" in [b for m, b in calls if m == "sendMessage"][-2]["text"]

        lead = client.get("/api/leads", headers=ADMIN).json()[0]
        assert lead["name"] == "Анна" and lead["phone"] == "+79140000000" and lead["kind"] == "calc"
        assert lead["source"] == "kbchachacha" and "@anna" in lead["comment"] and lead["page"] == "telegram-bot"

        # бюджет, под который ничего нет: бот предлагает подбор менеджером, заявка — «подбор под бюджет»
        press("r:")
        press("c:KR")
        bot.chats["7"]["budget"] = 100_000
        bot.chats["7"]["makes"] = ["Kia"]
        press("m:any")
        assert "ничего нет" in last("sendMessage")["text"]
        press("w:pick")
        write(text="+7 914 000-00-00")
        pick = client.get("/api/leads", headers=ADMIN).json()[0]
        assert pick["kind"] == "pick" and pick["budget_rub"] == 100_000 and pick["source"] is None

        # бот перезапустился и забыл переписку: старая кнопка начинает разговор заново, а не падает
        bot.chats.clear()
        press("n:1")
        assert "Откуда смотреть" in last("sendMessage")["text"]
        # ссылка на бота в подвале сайта — только когда бот подключён
        assert "t.me/renalauto_bot" not in client.get("/cars").text
        app.state.shop.username = "renalauto_bot"
        assert "https://t.me/renalauto_bot" in client.get("/cars").text
        app.state.shop.username = None
        assert client.get("/health").json()["catalog_bot"] == {"bot": False, "bot_username": None, "last_error": None}
    finally:
        client.__exit__(None, None, None)


def test_catalog_uses_the_scene_filters_and_view_switch(settings):
    k5 = kb(external_id="2", title="기아 K5 1.6 터보", make="기아", model="K5", extra={"displacement": "1,598cc"})
    ray = kb(external_id="3", title="기아 레이 1.0", make="기아", model="레이", price=9_000_000, price_usd=6_500,
             extra={"displacement": "998cc"})
    client, _ = make_client(settings, [kb(), k5, ray])
    try:
        page = client.get("/cars").text
        assert 'data-cat-filter' in page and 'name="budget"' in page and "Kia · 2" in page
        assert 'href="/#terminal"' in page and 'aria-current="page"' in page  # переключатель «Стоянка / Список»
        assert "/car/kbchachacha/2" in page and "/car/kbchachacha/3" in page and "/car/kbchachacha/1" not in page

        # марка и модель — из справочника, как на стоянке
        one = client.get("/cars", params={"make": "Kia", "model": "K5"}).text
        assert "/car/kbchachacha/2" in one and "/car/kbchachacha/3" not in one and "<b>1 машина</b>" in one
        assert 'href="/?make=Kia&amp;model=K5#terminal"' in one  # выбор переезжает на стоянку

        # бюджет считается по цене с растаможкой, а не по цене площадки
        prices = {c["path"].rsplit("/", 1)[-1]: c["turnkey"] for c in client.get("/api/port/cars").json()["cars"]}
        cheap, dear = sorted(prices, key=prices.get)
        mid = (prices[cheap] + prices[dear]) // 2
        budget = client.get("/cars", params={"budget": mid}).text
        assert f"/car/kbchachacha/{cheap}" in budget and f"/car/kbchachacha/{dear}" not in budget
        assert "data-stream" not in budget  # живая лента под бюджет не подмешивает лишнее
        assert "машин сейчас нет" in client.get("/cars", params={"budget": 1000}).text

        # старые ссылки с маркой текстом продолжают работать
        assert "/car/kbchachacha/2" in client.get("/cars", params={"make": "kia", "mileage_max": 60000}).text
        assert 'data-view-link="/cars"' in client.get("/").text
    finally:
        client.__exit__(None, None, None)
