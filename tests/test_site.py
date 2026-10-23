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
        assert "/static/media/reel.mp4" in page.text and "vk.ru/renal_auto" in page.text
        assert "Что говорят клиенты" in page.text and "ИНН 2543160025" in page.text
        assert page.text.count('class="review rv-card"') >= 10 and "/static/brand/max.webp" in page.text
        assert client.get("/static/media/reel.jpg").status_code == 200
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
    finally:
        client.__exit__(None, None, None)


def test_privacy_consent_and_metrika(settings):
    settings.ym_id = None
    client, app = make_client(settings, [])
    try:
        page = client.get("/port").text
        assert page.count('name="consent" required') == 1  # одна всплывающая форма заявки на всю страницу
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
        assert client.get("/api/port/cars", params={"country": "CN"}).json() == {"cars": [], "total": 0, "more": False}
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
        credits = client.get("/credits").text
        assert "Hyundai Tucson" in credits and "Wikimedia Commons" in credits and "CC BY-SA 4.0" in credits
        assert client.get("/static/brand/og.jpg").status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_scene_title_without_double_make_and_cn_price_without_engine(settings):
    from renalauto.models import Listing
    audi = Listing(source="dongchedi", external_id="7", country="CN", url="https://example.com/7", title="奥迪 Audi A4L 2022款 40 TFSI",
                   make="奥迪", model="Audi A4L", year=2022, price=200_000, currency="CNY")
    client, app = make_client(settings, [audi])
    try:
        car = client.get("/api/port/dongchedi/7").json()
        assert car["title"] == "Audi A4L"
        assert car["turnkey"] and car["turnkey_from"] is True  # объём не указан — 1,5 л по умолчанию, цена «от»
    finally:
        client.__exit__(None, None, None)


def test_only_configured_sources_on_site(settings):
    # на сайте — только площадки из SOURCES; старые объявления других площадок остаются в базе, но не показываются
    settings.sources = ["encar", "dongchedi"]
    old = kb(external_id="7", title="기아 K5 1.6 터보", make="기아", model="K5", extra={"displacement": "1,598cc"})
    fresh = kb(source="encar", external_id="8", title="기아 K5 1.6 터보", make="기아", model="K5", extra={"displacement": "1,598cc"})
    client, app = make_client(settings, [old, fresh])
    try:
        r = client.get("/api/port/cars").json()
        assert [c["source"] for c in r["cars"]] == ["encar"]
    finally:
        client.__exit__(None, None, None)


def test_port_share_title(settings):
    # ссылка с подборкой: заголовок страницы (и превью в мессенджере) описывает выбор
    client, app = make_client(settings, [])
    try:
        page = client.get("/port", params={"country": "KR", "budget": "2500000", "year_from": "2020"})
        assert "<title>Авто из Кореи до 2,5 млн ₽ от 2020 г. — живая подборка | Ренал Авто</title>" in page.text
    finally:
        client.__exit__(None, None, None)


def test_car_share_preview(settings):
    # ссылка на машину в мессенджере: картинка с ценой и расклад в описании
    k5 = kb(external_id="9", title="기아 K5 1.6 터보", make="기아", model="K5", photo=None, extra={"displacement": "1,598cc"})
    client, app = make_client(settings, [k5])
    try:
        page = client.get("/car/kbchachacha/9").text
        assert "/og/car/kbchachacha/9.png" in page
        assert "с растаможкой" in page and 'og:description" content="Машина' in page
        img = client.get("/og/car/kbchachacha/9.png")
        assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content[:4] == b"\x89PNG"
        assert client.get("/og/car/kbchachacha/nope.png", follow_redirects=False).status_code in (302, 307)
    finally:
        client.__exit__(None, None, None)


def test_port_compare_share_title(settings):
    # прислали ссылку на сравнение — в заголовке превью названия машин
    a = kb(source="encar", external_id="11", title="기아 K5 1.6 터보", make="기아", model="K5", year=2021, extra={"displacement": "1,598cc"})
    b = kb(source="encar", external_id="12", title="현대 투싼 1.6", make="현대", model="투싼", year=2022, extra={"displacement": "1,598cc"})
    client, app = make_client(settings, [a, b])
    try:
        page = client.get("/port", params={"cmp": "encar:11,encar:12,encar:nope"})
        assert "<title>Сравнение: Kia K5 2021, Hyundai Tucson 2022 — цены с растаможкой | Ренал Авто</title>" in page.text
    finally:
        client.__exit__(None, None, None)


def test_port_feed_recent(settings):
    # лента-чат под сценой: последние объявления со временем появления
    settings.sources = ["encar"]
    car = kb(source="encar", external_id="21", title="기아 K5 1.6 터보", make="기아", model="K5", extra={"displacement": "1,598cc"})
    client, app = make_client(settings, [car])
    try:
        page = client.get("/port").text
        assert "data-feed" in page
        scene = json.loads(page.split('id="port-data">')[1].split("</script>")[0])
        assert scene["recent"][0]["title"] == "Kia K5" and scene["recent"][0]["seen"]
    finally:
        client.__exit__(None, None, None)


def test_stock_cars_admin_and_landing(settings):
    # машины в наличии: менеджер добавляет с фото, на лендинге — карточка; «Продана» — пропадает
    import base64, io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (40, 30), (200, 30, 30)).save(buf, "PNG")
    photo = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    client, app = make_client(settings, [])
    try:
        assert client.post("/api/stock", json={"title": "Kia K5"}).status_code == 403
        r = client.post("/api/stock", headers=ADMIN, json={"title": "Kia K5 2.0", "year": 2021, "price_rub": 2350000,
                                                           "status": "vlad", "photos_add": [photo]})
        assert r.status_code == 201
        car = r.json()
        assert len(car["photos"]) == 1 and client.get(f"/media/stock/{car['photos'][0]}").headers["content-type"] == "image/webp"
        page = client.get("/port").text
        assert "Уже выкуплены" in page and "Kia K5 2.0, 2021" in page and "Во Владивостоке" in page and "2 350 000 ₽" in page
        assert "Машины в наличии" in client.get("/admin/stock", params={"token": "secret"}).text
        assert client.patch(f"/api/stock/{car['id']}", headers=ADMIN, json={"status": "sold"}).json()["status"] == "sold"
        assert "Уже выкуплены" not in client.get("/port").text
        assert client.delete(f"/api/stock/{car['id']}", headers=ADMIN).status_code == 204
        assert client.get(f"/media/stock/{car['photos'][0]}").status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_port_filter_total_not_capped(settings, monkeypatch):
    # «под ваш запрос N машин»: когда перебрали не всё, без бюджета считаем по базе, а не «ровно PORT_SCAN»
    import renalauto.api as api_mod
    monkeypatch.setattr(api_mod, "PORT_SCAN", 2)
    settings.sources = ["encar"]
    cars = [kb(source="encar", external_id=str(30 + i), title="기아 K5 1.6 터보", make="기아", model="K5", extra={"displacement": "1,598cc"}) for i in range(5)]
    client, app = make_client(settings, cars)
    try:
        r = client.get("/api/port/cars", params={"country": "KR"}).json()
        assert r["total"] == 5 and r["more"] is False
        r = client.get("/api/port/cars", params={"country": "KR", "budget": 99_000_000}).json()
        assert r["more"] is True
    finally:
        client.__exit__(None, None, None)
