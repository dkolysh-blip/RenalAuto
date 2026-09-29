import pytest

from renalauto.models import Listing, SavedFilter
from renalauto.storage import Storage
from renalauto.vin.report import build_report


def make_listing(**kw):
    base = dict(source="encar", external_id="1", country="KR", url="u", title="현대 아반떼", make="현대",
                year=2021, mileage_km=50000, price=18_000_000, currency="KRW", price_usd=13000)
    base.update(kw)
    return Listing(**base)


def test_upsert_statuses_and_vin_preserved(settings):
    st = Storage(settings.db_path)
    assert st.upsert(make_listing(vin="KMHLM41C6MU123457"))[0] == "new"
    status, merged, _ = st.upsert(make_listing())  # выдача без VIN
    assert status == "unchanged" and merged.vin == "KMHLM41C6MU123457"
    status, merged, old = st.upsert(make_listing(price=17_000_000))
    assert status == "price_changed" and old == 18_000_000
    assert [h["price"] for h in st.history("encar", "1")] == [18_000_000, 17_000_000]


def test_filter_matching():
    l = make_listing()
    assert SavedFilter(name="a", make="현대", year_from=2020, price_usd_max=15000).matches(l)
    assert not SavedFilter(name="b", country="CN").matches(l)
    assert not SavedFilter(name="c", mileage_max=40000).matches(l)


@pytest.mark.asyncio
async def test_report_detects_rollback_relisting_and_make_mismatch(settings):
    st = Storage(settings.db_path)
    vin = "KMHLM41C6MU123457"
    st.upsert(make_listing(external_id="1", vin=vin, mileage_km=120_000))
    st.upsert(make_listing(external_id="2", vin=vin, mileage_km=60_000, price=21_000_000))
    report = await build_report(vin, storage=st, settings=settings, sources={})
    names = {c.name: c for c in report.checks if not c.ok}
    assert "mileage_rollback" in names and "relisted" in names
    assert report.verdict == "danger"

    wrong = make_listing(source="dongchedi", external_id="9", country="CN", make="丰田", title="丰田 凯美瑞",
                         vin="LGXCE4CB8N0012345", year=2022, currency="CNY")
    st.upsert(wrong)
    report = await build_report("LGXCE4CB8N0012345", storage=st, settings=settings, sources={})
    mismatch = [c for c in report.checks if c.name == "make_match"]
    assert mismatch and not mismatch[0].ok


@pytest.mark.asyncio
async def test_clean_report(settings):
    st = Storage(settings.db_path)
    st.upsert(make_listing(vin="KMHLM41C6MU123457"))
    report = await build_report("KMHLM41C6MU123457", storage=st, settings=settings, sources={})
    assert report.verdict == "ok"
    assert any(c.name == "make_match" and c.ok for c in report.checks)
