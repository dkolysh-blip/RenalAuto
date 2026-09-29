import pytest

from renalauto.sources.dongchedi import DongchediSource, parse_mileage, parse_price_wan
from renalauto.sources.encar import EncarSource

from .conftest import fixture, mock_client


@pytest.mark.asyncio
async def test_encar_search_and_detail(settings, monkeypatch):
    monkeypatch.setenv("ENCAR_QUERIES", "(And.Hidden.N._.CarType.Y.)")
    client = mock_client(
        {
            "/search/car/list/general": fixture("encar_search.json"),
            "/readside/vehicle/": fixture("encar_detail.json"),
        }
    )
    src = EncarSource(settings, client)
    listings = await src.fetch_latest(limit=2)
    assert [l.external_id for l in listings] == ["38912345", "38912001"]
    first = listings[0]
    assert first.price == 18_900_000
    assert first.currency == "KRW"
    assert first.year == 2021 and first.mileage_km == 35210
    assert first.photo == "https://ci.encar.com/carpicture07/pic3891/38912345_001.jpg"
    assert first.url == "https://fem.encar.com/cars/detail/38912345"
    assert first.listed_at.utcoffset().total_seconds() == 9 * 3600
    assert first.vin is None

    detailed = await src.fetch_detail(first)
    assert detailed.vin == "KMHLM41C6MU123457"
    assert detailed.plate == "123가4567"
    assert detailed.price == 18_500_000
    assert detailed.extra["color"] == "흰색"


@pytest.mark.asyncio
async def test_encar_history(settings):
    seen = {}

    def record(request):
        seen["vehicleNo"] = request.url.params["vehicleNo"]
        return fixture("encar_record.json")

    client = mock_client({"/record/vehicle/": record, "/readside/vehicle/": fixture("encar_detail.json")})
    src = EncarSource(settings, client)
    listing = src.parse_search_item(fixture("encar_search.json")["SearchResults"][0])
    history = await src.fetch_history(listing)
    assert seen["vehicleNo"] == "123가4567"
    assert history["accidents_own"] == 1 and history["accidents_other"] == 2
    assert history["owner_changes"] == 2
    assert any("5 млн" in f for f in history["flags"])


@pytest.mark.asyncio
async def test_dongchedi_list(settings):
    client = mock_client({"/sh_sku_list": fixture("dongchedi_list.json")})
    src = DongchediSource(settings, client)
    listings = await src.fetch_latest(limit=2)
    han, camry = listings
    assert han.external_id == "17712345"
    assert han.price == 152_800 and han.currency == "CNY"
    assert han.mileage_km == 35_000
    assert han.make == "比亚迪" and han.year == 2022
    assert han.extra["new_price_cny"] == 279_500
    assert han.url == "https://www.dongchedi.com/usedcar/17712345"
    assert camry.mileage_km == 8000 and camry.year == 2019


def test_dongchedi_parsers():
    assert parse_mileage("3.5万公里") == 35000
    assert parse_mileage("8000公里") == 8000
    assert parse_mileage(None) is None
    assert parse_price_wan("12.58万") == 125800


@pytest.mark.asyncio
async def test_encar_falls_back_to_working_search_path(settings, monkeypatch):
    monkeypatch.setenv("ENCAR_QUERIES", "(And.Hidden.N._.CarType.Y.)")
    import httpx

    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/premium"):
            assert request.headers["Referer"] == "https://www.encar.com/"
            return httpx.Response(200, json=fixture("encar_search.json"))
        return httpx.Response(404)

    src = EncarSource(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert len(await src.fetch_latest(limit=2)) == 2
    assert src.search_paths[0] == "premium"
    calls.clear()
    await src.fetch_latest(limit=2)
    assert calls == ["/search/car/list/premium"]


@pytest.mark.asyncio
async def test_encar_block_page_is_reported(settings, monkeypatch):
    monkeypatch.setenv("ENCAR_QUERIES", "(And.Hidden.N._.CarType.Y.)")
    import httpx

    from renalauto.sources.base import SourceError

    blocked = '<meta http-equiv="refresh" content="0; url=https://api.encar.com/has_been_cr_blocked_AWS.html" />'
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404, text=blocked)))
    with pytest.raises(SourceError, match="заблокирован"):
        await EncarSource(settings, client).fetch_latest(limit=2)


@pytest.mark.asyncio
async def test_kbchachacha_list_and_detail(settings):
    import httpx

    from renalauto.sources.kbchachacha import KbChachachaSource

    from .conftest import FIXTURES

    list_html = (FIXTURES / "kbchachacha_list.html").read_text(encoding="utf-8")
    detail_html = (FIXTURES / "kbchachacha_detail.html").read_text(encoding="utf-8")

    def handler(request):
        if request.url.path.endswith("list.empty"):
            body = list_html if request.url.params["page"] == "1" else ""
            return httpx.Response(200, text=body)
        assert request.url.params["carSeq"] == "27892372"
        return httpx.Response(200, text=detail_html)

    src = KbChachachaSource(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    bongo, sonata = await src.fetch_latest(limit=10)

    assert bongo.external_id == "27892372"
    assert bongo.make == "기아" and bongo.model == "봉고3"
    assert bongo.price == 10_400_000 and bongo.currency == "KRW"
    assert bongo.photo.startswith("https://img.kbchachacha.com/IMG/carimg/l/img09/img2789/27892372_")
    assert bongo.url == "https://www.kbchachacha.com/public/car/detail.kbc?carSeq=27892372"
    assert bongo.extra["section"] == "KB스타픽"

    assert sonata.price == 23_500_000
    assert sonata.year == 2024 and sonata.mileage_km == 31_200

    detailed = await src.fetch_detail(bongo)
    assert detailed.plate == "83루1615"
    assert detailed.year == 2019
    assert detailed.mileage_km == 195_945
    assert detailed.fuel == "디젤" and detailed.transmission == "수동"
    assert detailed.location == "인천"
    assert detailed.extra["displacement"] == "2,497cc"
    assert detailed.vin is None
