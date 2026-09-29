import httpx
import pytest
from fastapi.testclient import TestClient

from renalauto.api import create_app
from renalauto.collector import Collector
from renalauto.sources.encar import EncarSource

from .conftest import fixture, mock_client


@pytest.mark.asyncio
async def test_collector_collects_detail_and_history_and_pushes(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("ENCAR_QUERIES", "(And.Hidden.N._.CarType.Y.)")
    detail_calls = []

    def detail(request):
        detail_calls.append(request.url.path)
        return fixture("encar_detail.json")

    encar = EncarSource(settings, mock_client({
        "/search/car/list/": fixture("encar_search.json"),
        "/record/vehicle/": fixture("encar_record.json"),
        "/readside/vehicle/": detail,
    }))
    pushed = []

    def server(request: httpx.Request) -> httpx.Response:
        import json
        assert request.headers["X-Ingest-Token"] == "tok"
        body = json.loads(request.content)
        pushed.append(body)
        return httpx.Response(200, json={"ok": True, "counts": {"new": len(body["listings"])}})

    collector = Collector(settings, server="https://srv", token="tok", source_names=["encar"],
                          state_path=str(tmp_path / "c.db"), name="seoul-1", detail_delay=0,
                          http=httpx.AsyncClient(transport=httpx.MockTransport(server)), sources={"encar": encar})
    await collector.run_once(encar)
    listings = pushed[0]["listings"]
    assert pushed[0]["collector"] == "seoul-1" and len(listings) == 2
    first = next(l for l in listings if l["external_id"] == "38912345")
    assert first["vin"] == "KMHLM41C6MU123457"
    assert first["extra"]["history"]["owner_changes"] == 2
    assert "raw" not in first["extra"]["history"]

    # второй цикл: карточки уже известных объявлений повторно не открываются
    calls_after_first = len(detail_calls)
    await collector.run_once(encar)
    assert len(detail_calls) == calls_after_first
    assert all(l["extra"].get("detail_loaded") for l in pushed[1]["listings"])
    await collector.aclose()


def test_ingest_endpoint(settings):
    settings.ingest_token = "tok"
    app = create_app(settings, sources={})
    listing = {"source": "encar", "external_id": "1", "country": "KR", "url": "u", "title": "현대 아반떼",
               "currency": "KRW", "price": 18_000_000, "extra": {"history": {"accidents_own": 1, "accidents_other": 0,
               "owner_changes": 3, "flags": ["Утопленник (затопление)"]}}}
    with TestClient(app) as client:
        assert client.post("/api/ingest/encar", json={"listings": [listing]}).status_code == 403
        r = client.post("/api/ingest/encar", headers={"X-Ingest-Token": "tok"}, json={"collector": "x", "listings": [listing]})
        assert r.json()["counts"]["new"] == 1
        bad = client.post("/api/ingest/kbchachacha", headers={"X-Ingest-Token": "tok"}, json={"listings": [listing]})
        assert bad.status_code == 422
        page = client.get("/car/encar/1").text
        assert "Страховая история" in page and "Утопленник" in page
        assert client.get("/health").json()["sources"]["encar"]["via"] == "collector:x"
