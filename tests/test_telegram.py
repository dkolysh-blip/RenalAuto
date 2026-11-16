import asyncio
import json

import httpx

from renalauto.notify import TelegramNotifier, join_code

from .conftest import ADMIN
from .test_site import kb, make_client


def test_telegram_chat_links_from_admin_and_receives_leads(settings):
    client, app = make_client(settings, [kb()])
    settings.telegram_bot_token = "123:abc"  # после запуска приложения: настоящий бот в тесте не слушает сеть
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": {}})

    old = app.state.notifier
    notifier = TelegramNotifier(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                                storage=app.state.storage)
    notifier.bot_username = "renal_leads_bot"
    app.state.notifier = notifier
    code = join_code(settings.admin_token)
    try:
        # пока никто не подключился — заявка сохраняется, но никуда не уходит; админка говорит об этом прямо
        assert notifier.lead_chats() == []
        page = client.get("/admin", headers=ADMIN).text
        assert "получателей нет" in page and f"https://t.me/renal_leads_bot?start={code}" in page
        assert settings.admin_token not in code
        assert client.post("/api/telegram/test", headers=ADMIN).status_code == 409

        # чужой человек написал боту — не подключается; по ссылке из админки — подключается (и группа тоже)
        asyncio.run(notifier.handle_message({"chat": {"id": 5, "first_name": "Чужой"}, "text": "/start"}))
        asyncio.run(notifier.handle_message({"chat": {"id": 5, "first_name": "Чужой"}, "text": "/start nope"}))
        assert notifier.lead_chats() == []
        asyncio.run(notifier.handle_message({"chat": {"id": 42, "first_name": "Иван"}, "text": f"/start {code}"}))
        asyncio.run(notifier.handle_message(
            {"chat": {"id": -100, "title": "Менеджеры"}, "text": f"/start@renal_leads_bot {code}"}))
        assert notifier.lead_chats() == ["42", "-100"]
        assert "Иван" in client.get("/admin", headers=ADMIN).text

        calls.clear()
        r = client.post("/api/leads", json={"name": "Пётр", "phone": "+79990000000", "source": "kbchachacha",
                                             "external_id": "1"})
        assert r.status_code == 201
        assert [c[1]["chat_id"] for c in calls] == ["42", "-100"] and "Пётр" in calls[0][1]["text"]
        health = client.get("/health").json()["lead_notify"]
        assert health["bot"] and health["chats"] == 2 and health["last_lead_sent"]

        assert client.post("/api/telegram/test", headers=ADMIN).json()["sent"] == 2
        asyncio.run(notifier.handle_message({"chat": {"id": 42}, "text": "/stop"}))
        assert client.delete("/api/telegram/chats/-100", headers=ADMIN).status_code == 204
        assert notifier.lead_chats() == []
    finally:
        app.state.notifier = old
        client.__exit__(None, None, None)


def test_offices_in_footer_trust_row_and_markup(settings):
    client, _ = make_client(settings, [kb()])
    try:
        home = client.get("/").text
        assert "Офисы в 3 городах" in home and 'id="offices"' in home
        assert "ул. Параллельная, д. 10" in home and "Благовещенск" in home
        org = json.loads(home.split('<script type="application/ld+json">')[1].split("</script>")[0])
        # в разметку для поисковиков попадают только офисы с известным адресом
        assert [d["address"]["addressLocality"] for d in org["department"]] == ["Владивосток", "Калуга"]
        assert 'id="offices"' in client.get("/cars").text
    finally:
        client.__exit__(None, None, None)


def test_header_contact_window_and_callback_lead(settings):
    settings.company_instagram = "https://instagram.com/renal_auto"
    settings.company_telegram_channel = "https://t.me/renal_auto_channel"
    client, _ = make_client(settings, [kb()])
    try:
        for url in ("/", "/cars", "/vin", "/car/kbchachacha/1"):
            page = client.get(url).text
            assert 'id="contact-dlg"' in page and "data-contact-open" in page, url
            assert "Написать в Telegram" in page and "https://t.me/+79140668808" in page
            assert "instagram.com/renal_auto" in page and "признана в России экстремистской" in page
            assert "t.me/renal_auto_channel" in page
        assert '<a href="/cars" class="on">Каталог</a>' in client.get("/cars").text
        assert '<a href="/" class="on">Стоянка</a>' in client.get("/").text

        r = client.post("/api/leads", json={"name": "Олег", "phone": "+79990000001", "kind": "callback",
                                             "comment": "Ответить: Telegram"})
        assert r.status_code == 201
        lead = client.get("/api/leads", headers=ADMIN).json()[0]
        assert lead["kind"] == "callback" and "Telegram" in lead["comment"]
        assert "Просьба связаться" in client.get("/admin", headers=ADMIN).text
    finally:
        client.__exit__(None, None, None)


def test_instagram_note_only_when_instagram_is_set(settings):
    client, _ = make_client(settings, [])
    try:
        assert "экстремистской" not in client.get("/cars").text
    finally:
        client.__exit__(None, None, None)


def test_telegram_link_from_settings_is_never_a_placeholder(monkeypatch):
    from renalauto.config import Settings

    default = "https://t.me/+79140668808"
    for raw, want in [("@ваш_аккаунт", default), ("@renal_auto", "https://t.me/renal_auto"), ("renal_auto", "https://t.me/renal_auto"),
                      ("+7 (914) 066-88-08", default), ("https://t.me/renal_auto", "https://t.me/renal_auto"),
                      ("javascript:alert(1)", default), ("", None)]:
        monkeypatch.setenv("COMPANY_TELEGRAM", raw)
        assert Settings().company_telegram == want, raw
    monkeypatch.delenv("COMPANY_TELEGRAM")
    assert Settings().company_telegram == default
    monkeypatch.setenv("COMPANY_TELEGRAM_CHANNEL", "@ваш_канал")
    assert Settings().company_telegram_channel == "https://t.me/RenalautoChina"  # заглушка — берём канал компании


def test_calculator_page_explains_the_same_rates_it_uses(settings):
    from renalauto import customs

    ok_car = kb(external_id="2", title="기아 K5 1.6 터보", make="기아", model="K5", extra={"displacement": "1,598cc"})
    client, _ = make_client(settings, [ok_car])
    try:
        page = client.get("/calc")
        assert page.status_code == 200 and "data-calc" in page.text and "/static/calc.js" in page.text
        assert '<a href="/calc" class="on">Калькулятор</a>' in page.text
        # пояснения берут цифры из тех же таблиц, что и расчёт
        assert f"не больше {customs.LOW_UTIL_MAX_HP} л.с." in page.text
        assert "5 200" in page.text and "750 000" in page.text and "1 067" in page.text
        assert "до 1,5 л — 1,7 €" in page.text and "больше 3 л — 5,7 €" in page.text
        assert "их назовёт менеджер" in page.text  # доставка не задана в настройках — в итог не входит

        r = client.get("/api/calc", params={"price": 1_500_000, "currency": "RUB", "cc": 1600, "hp": 150, "age": "mid"}).json()
        duty = next(l["rub"] for l in r["lines"] if l["title"].startswith("Таможенная пошлина"))
        assert duty == round(2.5 * 1600 * settings.rate_eur_rub) and r["passable"] and r["total_is_from"]
        assert "/calc</loc>" in client.get("/sitemap.xml").text
        # со страницы машины — ссылка в калькулятор с её параметрами
        assert "/calc?price=" in client.get("/car/kbchachacha/2").text
    finally:
        client.__exit__(None, None, None)
