import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from renalauto.api import create_app
from renalauto.marketing import MarketingAgent, PostWriter, PublishError, car_facts, pick_cars, sanitize
from renalauto.models import Listing
from renalauto.notify import TelegramNotifier
from renalauto.rates import Rates
from renalauto.storage import Storage
from renalauto.view import car_view

from .conftest import ADMIN

RATES = Rates({"KRW": 0.06, "CNY": 11.0, "USD": 80.0, "EUR": 90.0})
MONDAY = datetime(2026, 10, 19, 9, tzinfo=timezone.utc)
TUESDAY = datetime(2026, 10, 20, 9, tzinfo=timezone.utc)


def car(i: int, make: str = "기아", **kw) -> Listing:
    base = dict(source="kbchachacha", external_id=str(i), country="KR", url=f"https://kb/{i}",
                title=f"{make} K5 1.6 터보 <b>노블레스</b>", make=make, model="K5", year=2022, mileage_km=40_000 + i,
                price=25_000_000, currency="KRW", price_usd=18_000, fuel="가솔린", location="경기",
                photo=f"https://img/{i}.jpg", extra={"displacement": "1,598cc"})
    base.update(kw)
    return Listing(**base)


def fill(storage: Storage) -> None:
    storage.upsert(car(1))
    storage.upsert(car(2, make="현대", model="Avante", title="현대 아반떼 1.6 가솔린"))
    storage.upsert(car(3))
    storage.upsert(car(4, make="쉐보레", model="Trax", title="쉐보레 트랙스 1.4 터보"))
    storage.upsert(car(5, make="르노코리아", model="XM3", title="르노코리아 XM3 1.6"))
    # не годятся для канала: 3,8 л из Кореи (не проходит), без фото, без цены
    storage.upsert(car(6, title="현대 팰리세이드 3.8 가솔린", extra={"displacement": "3,778cc"}))
    storage.upsert(car(7, photo=None))
    storage.upsert(car(8, price=None, price_usd=None))


class FakeTelegram(TelegramNotifier):
    def __init__(self, settings, fail_photo: bool = False):
        self.calls: list[tuple[str, dict]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            method = request.url.path.rsplit("/", 1)[-1]
            payload = json.loads(request.content)
            self.calls.append((method, payload))
            if method == "sendPhoto" and fail_photo:
                return httpx.Response(400, json={"ok": False, "description": "Bad Request: wrong file"})
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 100 + len(self.calls)}})

        super().__init__(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        self.token = "TOKEN"
        self.manager_chat = "-1"


@pytest.fixture
def storage(settings):
    s = Storage(settings.db_path)
    fill(s)
    yield s
    s.close()


def agent_for(settings, storage, writer=None, **notifier_kw):
    settings.marketing_channel_id = "@renal_test"
    notifier = FakeTelegram(settings, **notifier_kw)
    writer = writer or PostWriter(None, "claude-opus-5-5", "Renal Auto")
    return MarketingAgent(settings, storage, RATES, notifier, writer), notifier


def test_pick_cars_skips_unsuitable_and_varies_makes(storage):
    picked = pick_cars(storage, RATES, exclude=set(), limit=4)
    ids = [v.listing.external_id for v in picked]
    assert not {"6", "7", "8"} & set(ids)
    assert len({v.make for v in picked}) == 4  # сначала по одной машине каждой марки
    assert "kbchachacha/1" not in {f"{v.listing.source}/{v.listing.external_id}" for v in
                                    pick_cars(storage, RATES, exclude={"kbchachacha/1"}, limit=10)}


def test_template_post_is_safe_and_honest_about_price(storage):
    v = car_view(storage.get("kbchachacha", "1"), RATES)
    facts = car_facts(v, "https://site/car/kbchachacha/1?utm_source=telegram")
    writer = PostWriter(None, "claude-opus-5-5", "Renal Auto")
    import asyncio

    text, by = asyncio.run(writer.car_post(facts))
    assert by == "template"
    assert "без доставки и растаможки" in text
    assert "1 500 000 ₽" in text  # 25 млн вон × 0,06
    assert "&lt;b&gt;" in text  # теги из названия объявления экранированы
    assert sanitize(text, {facts["ссылка"]}) == text


def test_sanitize_rejects_foreign_tags_and_links():
    ok = {"https://site/car/1"}
    assert sanitize('<b>Kia</b> <a href="https://site/car/1">смотреть</a>', ok)
    assert sanitize('<a href="https://evil.example">x</a>', ok) is None
    assert sanitize("<script>alert(1)</script>", ok) is None
    assert sanitize("  ", ok) is None
    assert sanitize("Kia & Hyundai &amp; Genesis", ok) == "Kia &amp; Hyundai &amp; Genesis"


class FakeClaude:
    def __init__(self, text: str, stop_reason: str = "end_turn"):
        self.requests: list[dict] = []
        self.text, self.stop_reason = text, stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(stop_reason=self.stop_reason, content=[
            SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.text)])


@pytest.mark.asyncio
async def test_claude_writer_uses_facts_and_falls_back(storage):
    v = car_view(storage.get("kbchachacha", "1"), RATES)
    link = "https://site/car/kbchachacha/1"
    facts = car_facts(v, link)

    good = FakeClaude(f'<b>Kia K5</b> — ≈ 1 500 000 ₽ в Корее. <a href="{link}">Цена под ключ</a>')
    text, by = await PostWriter(None, "claude-opus-5-5", "Renal Auto", client=good).car_post(facts)
    assert by == "claude" and text.startswith("<b>Kia K5</b>")
    request = good.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["fallbacks"] == "default"
    assert "Renal Auto" in request["system"]
    assert link in request["messages"][0]["content"]

    for bad in (FakeClaude('<a href="https://other">x</a>'), FakeClaude("x" * 2000), FakeClaude("ok", "refusal")):
        text, by = await PostWriter(None, "claude-opus-5-5", "Renal Auto", client=bad).car_post(facts)
        assert by == "template"


@pytest.mark.asyncio
async def test_run_once_makes_drafts_digest_and_does_not_repeat(settings, storage):
    settings.marketing_posts_per_run = 2
    settings.marketing_digest_weekday = 0
    agent, tg = agent_for(settings, storage)

    posts = await agent.run_once(MONDAY)
    kinds = [p.kind for p in posts]
    assert kinds == ["car", "car", "digest"]
    assert all(p.status == "draft" for p in posts)
    assert "utm_source=telegram" in posts[0].text
    assert posts[0].photo == "https://img/" + posts[0].cars[0].split("/")[1] + ".jpg"
    assert tg.calls[-1][0] == "sendMessage" and "/admin/marketing" in tg.calls[-1][1]["text"]
    used = {k for p in posts for k in p.cars}
    assert len(used) == 5  # подборка не повторяет «машины дня»

    # во вторник подборки нет, и уже показанные машины не повторяются
    assert await agent.run_once(TUESDAY) == []


@pytest.mark.asyncio
async def test_publish_and_fallback_to_text(settings, storage):
    agent, tg = agent_for(settings, storage, fail_photo=True)
    post = (await agent.run_once(TUESDAY))[0]
    published = await agent.publish(post.id)
    assert published.status == "published" and published.message_id
    assert [c[0] for c in tg.calls[-2:]] == ["sendPhoto", "sendMessage"]
    assert tg.calls[-1][1]["chat_id"] == "@renal_test"

    settings.marketing_channel_id = None
    other = storage.list_posts("draft")[0]
    with pytest.raises(PublishError):
        await agent.publish(other.id)


def test_seconds_until_next_run(settings, storage):
    settings.marketing_interval_hours = 24
    agent, _ = agent_for(settings, storage)
    assert agent.seconds_until_next_run(TUESDAY) == 0
    from renalauto.models import Post

    storage.add_post(Post(kind="car", text="x"))
    last = storage.last_post_at()
    assert 23 * 3600 < agent.seconds_until_next_run(last) <= 24 * 3600


def test_admin_marketing_api(settings):
    settings.marketing_channel_id = "@renal_test"
    app = create_app(settings, sources={})
    with TestClient(app) as client:
        fill(app.state.storage)
        app.state.marketing.notifier = FakeTelegram(settings)

        assert client.post("/api/marketing/run").status_code == 403
        posts = client.post("/api/marketing/run", headers=ADMIN).json()
        assert posts and posts[0]["status"] == "draft"
        pid = posts[0]["id"]

        page = client.get("/admin/marketing?token=secret")
        assert page.status_code == 200 and "Опубликовать" in page.text

        edited = client.patch(f"/api/marketing/posts/{pid}", json={"text": "Новый текст"}, headers=ADMIN).json()
        assert edited["text"] == "Новый текст" and edited["writer"] == "edited"
        for bad in ('<a href="javascript:alert(1)">x</a>', '<img src=x onerror=alert(1)>', '<b onclick="x">x</b>'):
            assert client.patch(f"/api/marketing/posts/{pid}", json={"text": bad}, headers=ADMIN).status_code == 422

        published = client.post(f"/api/marketing/posts/{pid}/publish", headers=ADMIN).json()
        assert published["status"] == "published"
        assert client.post(f"/api/marketing/posts/{pid}/skip", headers=ADMIN).status_code == 409

        skipped = client.post(f"/api/marketing/posts/{posts[1]['id']}/skip", headers=ADMIN).json()
        assert skipped["status"] == "skipped"
        assert client.post("/api/marketing/posts/999/publish", headers=ADMIN).status_code == 404
