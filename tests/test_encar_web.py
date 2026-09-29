import httpx
import pytest

from renalauto.sources.encar import EncarSource, extract_vehicle

from .conftest import FIXTURES


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_encar_web_list_and_detail(settings, monkeypatch):
    monkeypatch.setenv("ENCAR_MODE", "web")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "car.encar.com":
            assert '"sort":"ModifiedDate"' in request.url.params["search"]
            return httpx.Response(200, text=read("encar_web_list.html") if request.url.params["page"] == "1" else "")
        if request.url.host == "fem.encar.com":
            return httpx.Response(200, text=read("encar_web_detail.html"))
        return httpx.Response(404, text="<meta http-equiv='refresh' content='0; url=https://api.encar.com/has_been_cr_blocked_AWS.html'>")

    src = EncarSource(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    jeep, kia = await src.fetch_latest(limit=20)
    assert not any("api.encar.com" in u for u in seen)

    assert jeep.external_id == "40878322" and jeep.make == "지프" and jeep.year == 2016
    assert jeep.price == 7_700_000 and jeep.mileage_km == 94775
    assert jeep.photo == "https://ci.encar.com/carpicture07/pic4087/40878322_001.jpg"
    assert len(jeep.extra["photos"]) == 2
    assert kia.photo == "https://ci.encar.com/carpicture01/pic4095/40952334_001.jpg"

    detailed = await src.fetch_detail(kia.model_copy(update={"external_id": "42680859"}))
    assert detailed.vin == "KNAPL812HNK932842"
    assert detailed.plate == "321무9905"
    assert detailed.mileage_km == 143432 and detailed.fuel == "디젤"
    assert detailed.extra["displacement_cc"] == 1598
    assert detailed.location == "대전 유성구"
    assert len(detailed.extra["photos"]) == 2


def test_extract_vehicle_missing():
    assert extract_vehicle("<html>nothing</html>", "1") is None
    data = extract_vehicle(read("encar_web_detail.html"), "42680859")
    assert data["category"]["formYear"] == "2022"
    assert data["advertisement"]["price"] == 1050
