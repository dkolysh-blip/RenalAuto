from fastapi.testclient import TestClient

from renalauto import i18n
from renalauto.api import create_app
from renalauto.eligibility import displacement_cc, evaluate
from renalauto.models import Listing
from renalauto.sources.kbchachacha import KbChachachaSource

from .conftest import ADMIN, FIXTURES


def kb(**kw):
    base = dict(source="kbchachacha", external_id="1", country="KR", url="https://kb/1",
                title="현대 팰리세이드 3.8 가솔린 8인승 프레스티지", make="현대", model="팰리세이드",
                year=2022, mileage_km=50_000, price=30_000_000, currency="KRW", price_usd=21_600,
                fuel="가솔린", location="경기", photo="https://img/1.jpg", plate="12가3456")
    base.update(kw)
    return Listing(**base)


def test_i18n_titles_and_aliases():
    assert i18n.title("현대 팰리세이드 3.8 가솔린 8인승 프레스티지") == "Hyundai Palisade 3.8 бензин 8 мест Prestige"
    assert i18n.title("丰田 凯美瑞 2019款 2.0G 豪华版") == "Toyota Camry 2019 г. 2.0G Luxury"
    assert "현대" in i18n.search_aliases("hyundai")
    assert i18n.fuel("하이브리드(가솔린)") == "Гибрид (бензин)"
    assert i18n.city("경기 수원시") == "Кёнгидо"


def test_eligibility_korea_rules():
    big = evaluate(kb())
    assert displacement_cc(kb()) == 3800
    assert big.verdict == "bad"
    assert any(b.code == "kr_cc" and b.status == "bad" for b in big.badges)

    small = evaluate(kb(title="기아 K5 1.6 터보", fuel="가솔린", year=2021, extra={"displacement": "1,598cc"}))
    assert small.verdict in ("ok", "warn")
    assert any(b.code == "kr_cc" and b.status == "ok" for b in small.badges)

    hybrid = evaluate(kb(title="기아 K8 하이브리드 1.6", fuel="하이브리드(가솔린)", extra={"displacement": "1,598cc"}))
    assert hybrid.verdict == "bad"

    unknown = evaluate(kb(title="기아 레이", fuel="가솔린"))
    assert unknown.verdict == "unknown"


def make_client(settings, listings):
    app = create_app(settings, sources={})
    client = TestClient(app)
    client.__enter__()
    for l in listings:
        app.state.storage.upsert(l)
    return client, app


def test_pages_render_and_filter(settings):
    ok_car = kb(external_id="2", title="기아 K5 1.6 터보", make="기아", model="K5", extra={"displacement": "1,598cc"})
    client, app = make_client(settings, [kb(), ok_car])
    try:
        page = client.get("/")
        assert page.headers["cache-control"] == "no-cache"
        assert client.get("/favicon.ico").status_code == 200
        html = page.text
        assert "Hyundai Palisade" in html and "Kia K5" in html
        assert "₽" in html
        only_ok = client.get("/", params={"passable": "1"}).text
        assert "Kia K5" in only_ok and "Hyundai Palisade" not in only_ok
        by_make = client.get("/", params={"make": "Hyundai"}).text
        assert "Hyundai Palisade" in by_make and "Kia K5" not in by_make

        car = client.get("/car/kbchachacha/1")
        assert car.status_code == 200
        assert "Проходимость в РФ" in car.text and "Рассчитать цену под ключ" in car.text
        assert '"@type": "Car"' in car.text
        assert client.get("/car/kbchachacha/nope").status_code == 404

        assert "/car/kbchachacha/2" in client.get("/sitemap.xml").text
        assert "Sitemap:" in client.get("/robots.txt").text
        assert client.get("/vin").status_code == 200
        assert client.get("/partials/card/kbchachacha/2").text.startswith('<a class="card fresh"')
    finally:
        client.__exit__(None, None, None)


def test_leads_flow(settings):
    client, app = make_client(settings, [kb()])
    sent = []

    async def fake_send(lead, site_url=None):
        sent.append(lead)
        return True

    app.state.notifier.send_lead = fake_send
    try:
        assert client.post("/api/leads", json={"name": "Иван"}).status_code == 422
        r = client.post("/api/leads", json={"name": "Иван", "phone": "+79990000000", "source": "kbchachacha",
                                             "external_id": "1", "comment": "Интересует"})
        assert r.status_code == 201
        assert sent and "Hyundai Palisade" in sent[0].listing_title

        # заявка на отчёт об истории: тип и госномер сохраняются, менеджер видит их в /admin
        r = client.post("/api/leads", json={"name": "Пётр", "telegram": "@petr", "kind": "history",
                                             "source": "kbchachacha", "external_id": "1"})
        assert r.status_code == 201
        assert sent[-1].kind == "history" and sent[-1].plate == "12가3456"

        # бот заполнил скрытое поле — заявка не сохраняется
        assert client.post("/api/leads", json={"name": "bot", "phone": "1", "website": "x"}).status_code == 201
        assert client.get("/api/leads").status_code == 403
        leads = client.get("/api/leads", headers=ADMIN).json()
        assert len(leads) == 2 and leads[-1]["listing_url"] == "https://kb/1" and leads[-1]["kind"] == "calc"
        assert "Отчёт об истории" in client.get("/admin", params={"token": "secret"}).text
        assert "Получить отчёт" in client.get("/car/kbchachacha/1").text

        lead_id = leads[-1]["id"]
        assert client.patch(f"/api/leads/{lead_id}", json={"status": "deal"}, headers=ADMIN).json()["status"] == "deal"
        assert client.get("/api/leads/stats", headers=ADMIN).json()["deal"] == 1
        assert client.get("/admin", params={"token": "secret"}).status_code == 200
        assert client.get("/admin").status_code == 403

        for _ in range(10):
            last = client.post("/api/leads", json={"name": "Спам", "phone": "+7"})
        assert last.status_code == 429
    finally:
        client.__exit__(None, None, None)


def test_kb_detail_collects_photo_gallery(settings):
    src = KbChachachaSource(settings)
    detail = (FIXTURES / "kbchachacha_detail.html").read_text(encoding="utf-8")
    listing = src.apply_detail(kb(external_id="27892372", photo=None), detail)
    assert len(listing.extra["photos"]) == 2
    assert listing.photo == listing.extra["photos"][0]
