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
