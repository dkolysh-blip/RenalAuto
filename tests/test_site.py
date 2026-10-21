import json

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
        # Palisade 3.8 из Кореи не проходит (объём > 2 л) — на витрине его нет
        assert "Kia K5" in html and "Hyundai Palisade" not in html
        assert "₽" in html
        by_make = client.get("/", params={"make": "Kia"}).text
        assert "Kia K5" in by_make
        assert "Kia K5" not in client.get("/", params={"make": "Hyundai"}).text
        assert "/car/kbchachacha/1" not in client.get("/sitemap.xml").text
        assert client.get("/partials/card/kbchachacha/1").status_code == 204

        car = client.get("/car/kbchachacha/1")
        assert car.status_code == 200
        assert "не получится привезти" in car.text and 'content="noindex"' in car.text
        assert "Проходимость в РФ" in car.text and "Рассчитать итоговую цену" in car.text
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


def test_port_landing_scene_and_message_match(settings):
    ok_car = kb(external_id="2", title="기아 K5 1.6 터보", make="기아", model="K5", extra={"displacement": "1,598cc", "color": "흰색"})
    client, app = make_client(settings, [kb(), ok_car])
    try:
        page = client.get("/port", params={"model": "k5"})
        assert page.status_code == 200
        assert "<em>Kia K5</em>" in page.text
        assert 'id="terminal" aria-hidden="true"' in page.text
        assert "/static/media/vydacha-1.mp4" in page.text and "vk.ru/renal_auto" in page.text
        assert client.get("/static/media/vydacha-2.jpg").status_code == 200
        scene = json.loads(page.text.split('id="port-data">')[1].split("</script>")[0])
        assert [c["key"] for c in scene["cars"]] == ["kbchachacha:2"]  # непроходной Palisade 3.8 не попадает
        assert scene["cars"][0] | {"title": "Kia K5", "body": "sedan", "color": "#eceef0"} == scene["cars"][0]
        assert scene["match"] == "Kia K5" and scene["demo"] is False
        assert client.get("/port", params={"demo": "1"}).text.count('"demo": true') == 1
        # ключевая фраза из рекламы в utm_term — не модель: заголовок общий, а «kia k5» из utm_term находит машину
        assert '"match": null' in client.get("/port", params={"utm_term": "авто из кореи"}).text
        assert '"match": "Kia K5"' in client.get("/port", params={"utm_term": "k5"}).text

        assert client.get("/api/port/kbchachacha/2").json()["title"] == "Kia K5"
        assert client.get("/api/port/kbchachacha/1").status_code == 204
        assert client.get("/api/port/kbchachacha/404").status_code == 204
    finally:
        client.__exit__(None, None, None)


def test_calc_api(settings):
    client, app = make_client(settings, [])
    try:
        r = client.get("/api/calc", params={"price": 25_000_000, "currency": "KRW", "cc": 1598, "hp": 180, "age": "mid"}).json()
        assert r["passable"] is False and r["total_is_from"] is True
        assert r["lines"][0]["rub"] == round(25_000_000 * settings.rate_krw_rub)
        assert any(l["title"] == "Наше вознаграждение" and l["rub"] == 50_000 for l in r["lines"])
        assert client.get("/api/calc", params={"price": 0}).status_code == 422
        assert 'data-calc' in client.get("/port").text
    finally:
        client.__exit__(None, None, None)


def test_privacy_consent_and_metrika(settings):
    settings.ym_id = None
    client, app = make_client(settings, [])
    try:
        page = client.get("/port").text
        assert page.count('name="consent" required') == 2  # форма подбора и форма машины
        assert "mc.yandex.ru" not in page  # без YM_ID счётчика нет
        privacy = client.get("/privacy")
        assert privacy.status_code == 200 and "152-ФЗ" in privacy.text and "Метрика" not in privacy.text
    finally:
        client.__exit__(None, None, None)
    settings.ym_id = 12345678
    client, app = make_client(settings, [])
    try:
        assert 'ym(12345678,"init"' in client.get("/port").text
        assert "Яндекс Метрика" in client.get("/privacy").text
    finally:
        client.__exit__(None, None, None)


def test_port_filter_api(settings):
    k5 = kb(external_id="2", title="기아 K5 1.6 터보", make="기아", model="K5", year=2022, price=20_000_000,
            extra={"displacement": "1,598cc"})
    suv = kb(external_id="3", title="기아 스포티지 1.6 터보", make="기아", model="스포티지", year=2022, price=60_000_000,
             extra={"displacement": "1,598cc"})
    client, app = make_client(settings, [k5, suv])
    try:
        r = client.get("/api/port/cars", params={"q": "Kia K5"}).json()
        assert [c["id"] for c in r["cars"]] == ["2"] and r["total"] == 1
        car = r["cars"][0]
        assert car["turnkey"] > 20_000_000 * settings.rate_krw_rub and car["turnkey_from"] is True
        assert car["calc"] == {"country": "KR", "engine": "ice", "age": car["calc"]["age"], "cc": 1598,
                               "price": round(20_000_000 * settings.rate_krw_rub)}
        assert {c["id"] for c in client.get("/api/port/cars", params={"q": "kia"}).json()["cars"]} == {"2", "3"}
        assert client.get("/api/port/cars", params={"body": "suv"}).json()["total"] == 1
        cheap = client.get("/api/port/cars", params={"budget": 2_000_000}).json()
        assert [c["id"] for c in cheap["cars"]] == ["2"]
        assert client.get("/api/port/cars", params={"country": "CN"}).json() == {"cars": [], "total": 0}
    finally:
        client.__exit__(None, None, None)


def test_port_models_catalog(settings):
    cars = [kb(external_id=str(i), title="기아 K5 1.6 터보", make="기아", model="K5", year=y, price=p,
               extra={"displacement": "1,598cc"}) for i, (y, p) in enumerate([(2022, 20_000_000), (2022, 22_000_000), (2020, 15_000_000)])]
    client, app = make_client(settings, cars)
    try:
        makes = client.get("/api/port/models").json()["makes"]
        assert [m["make"] for m in makes] == ["Kia"] and makes[0]["count"] == 3
        k5 = makes[0]["models"][0]
        assert k5["model"] == "K5" and k5["country"] == "KR" and k5["engine"] == "ice" and k5["cc"] == 1600
        assert list(k5["years"]) == ["2022", "2020"] and k5["years"]["2022"]["n"] == 2
        assert k5["years"]["2022"]["price"] == round(21_000_000 * settings.rate_krw_rub, -4)
        assert client.get("/api/port/cars", params={"make": "Kia", "model": "K5"}).json()["total"] == 3
        assert client.get("/api/port/cars", params={"make": "Kia", "model": "K3"}).json()["total"] == 0
    finally:
        client.__exit__(None, None, None)


def test_title_leaves_no_hangul():
    assert i18n.title("BMW 1시리즈 (F40) 120i Advantage") == "BMW 1 Series (F40) 120i Advantage"
    assert i18n.title("Renault Korea (삼성) The New QM6 2.0 LPe") == "Renault Korea The New QM6 2.0 LPe"
    assert i18n.title("벤츠 GLC-클래스 X253") == "Mercedes-Benz GLC-Class X253"
    assert not i18n.has_foreign(i18n.title("기아 더 뉴 레이 시그니처"))


def test_not_found_page_favicon_and_share_image(settings):
    client, app = make_client(settings, [])
    try:
        page = client.get("/nope", headers={"accept": "text/html"})
        assert page.status_code == 404 and "Такой страницы нет" in page.text
        assert client.get("/api/nope").json() == {"detail": "Not Found"}
        assert client.get("/favicon.ico").headers["content-type"] == "image/x-icon"
        port = client.get("/port").text
        assert "/static/brand/og.jpg" in port and 'href="/credits"' in port
        assert "Hyundai Tucson" in client.get("/credits").text
        assert client.get("/static/brand/og.jpg").status_code == 200
    finally:
        client.__exit__(None, None, None)
