from datetime import date

import pytest
from fastapi.testclient import TestClient

from renalauto.api import create_app
from renalauto.models import Listing
from renalauto.storage import Storage
from renalauto.vin.report import build_report, build_report_for_plate, check_mileage_per_year, looks_like_plate

VIN = "KMHRK81ADTU021265"


def car(i, **kw):
    base = dict(source="encar", external_id=str(i), country="KR", url=f"https://e/{i}", title="현대 팰리세이드 2.5T",
                make="현대", model="팰리세이드", year=2022, mileage_km=40_000, price=40_000_000, currency="KRW",
                plate=f"12가{1000 + i}")
    base.update(kw)
    return Listing(**base)


def test_mileage_per_year_rules():
    today = date(2026, 9, 1)
    taxi = check_mileage_per_year(car(1, year=2023, mileage_km=150_000), today)
    assert taxi.severity == "warning" and "такси" in taxi.explain
    low = check_mileage_per_year(car(1, year=2016, mileage_km=12_000), today)
    assert low.severity == "warning" and "скрутк" in low.explain
    assert check_mileage_per_year(car(1, year=2022, mileage_km=60_000), today).ok


def test_plate_detection():
    assert looks_like_plate("12가3456") and looks_like_plate("321 무 9905")
    assert not looks_like_plate(VIN)


@pytest.mark.asyncio
async def test_report_explains_and_scores(settings):
    st = Storage(settings.db_path)
    for i in range(2, 9):  # рынок: похожие машины
        st.upsert(car(i, price=40_000_000 + i * 100_000))
    st.upsert(car(1, vin=VIN, price=27_000_000))  # на ~33% дешевле рынка
    report = await build_report(VIN, storage=st, settings=settings, sources={})
    names = {c.name: c for c in report.checks}
    assert names["market_price"].severity == "warning"
    assert report.market["count"] == 7 and report.market["diff"] < -25
    assert "history_missing" in names and names["history_missing"].advice
    assert all(c.title for c in report.checks)
    assert report.checks[0].severity == "warning"  # важное — сверху
    assert report.verdict == "warning" and 0 < report.score < 100
    assert ("Завод", "Ульсан, Корея") in report.identity


@pytest.mark.asyncio
async def test_plate_report_uses_vin_when_known(settings):
    st = Storage(settings.db_path)
    st.upsert(car(1, vin=VIN))
    by_plate = await build_report_for_plate("12가 1001", storage=st, settings=settings, sources={})
    assert by_plate.query_type == "plate" and by_plate.vin == VIN

    st.upsert(car(2, plate="55나5555"))
    no_vin = await build_report_for_plate("55나5555", storage=st, settings=settings, sources={})
    assert no_vin.vin == "" and no_vin.listings and no_vin.identity

    missing = await build_report_for_plate("99다9999", storage=st, settings=settings, sources={})
    assert missing.checks[0].name in ("not_found", "history_missing")


def test_report_pages(settings):
    app = create_app(settings, sources={})
    with TestClient(app) as client:
        app.state.storage.upsert(car(1, vin=VIN))
        page = client.get(f"/vin/{VIN}")
        assert page.status_code == 200
        assert "Расшифровка результатов" in page.text and "Паспорт автомобиля" in page.text
        assert "Что делать:" in page.text
        assert client.get("/vin/12가1001").status_code == 200
        redirect = client.get("/vin", params={"vin": VIN}, follow_redirects=False)
        assert redirect.status_code == 303 and redirect.headers["location"] == f"/vin/{VIN}"
        assert client.get(f"/api/check/{VIN}").json()["vin"] == VIN
        assert f'href="/vin/{VIN}"' in client.get("/car/encar/1").text
