import asyncio

import pytest
from fastapi.testclient import TestClient

from renalauto.api import create_app
from renalauto.models import ListingEvent
from renalauto.sources.dongchedi import DongchediSource
from renalauto.sources.encar import EncarSource

from .conftest import fixture, mock_client


def make_sources(settings, dongchedi_payload):
    return {
        "encar": EncarSource(
            settings,
            mock_client(
                {
                    "/search/car/list/general": fixture("encar_search.json"),
                    "/readside/vehicle/": fixture("encar_detail.json"),
                    "/record/vehicle/": fixture("encar_record.json"),
                }
            ),
        ),
        "dongchedi": DongchediSource(settings, mock_client({"/sh_sku_list": lambda r: dongchedi_payload})),
    }


@pytest.fixture
def app_env(settings, monkeypatch):
    monkeypatch.setenv("ENCAR_QUERIES", "(And.Hidden.N._.CarType.Y.)")
    payload = fixture("dongchedi_list.json")
    app = create_app(settings, make_sources(settings, payload))
    with TestClient(app) as client:
        yield client, app, payload


def test_poll_warmup_then_events_and_vin_report(app_env):
    client, app, payload = app_env
    # Первый опрос — прогрев базы без событий
    assert client.post("/api/poll/encar").json()["events"] == 0
    assert client.post("/api/poll/dongchedi").json()["events"] == 0
    assert len(client.get("/api/listings").json()) == 4
    assert len(client.get("/api/listings", params={"country": "CN"}).json()) == 2

    # Карточка Encar подгружена при прогреве: есть VIN
    kr = client.get("/api/listings/encar/38912345").json()["listing"]
    assert kr["vin"] == "KMHLM41C6MU123457"

    # Фильтр + новое объявление + снижение цены
    f = client.post("/api/filters", json={"name": "BYD до $25k", "make": "比亚迪", "price_usd_max": 25000}).json()
    items = payload["data"]["search_sh_sku_info_list"]
    items.insert(0, {**items[0], "sku_id": 17799999, "sh_price": "14.9"})
    items[1]["sh_price"] = "14.5"
    received = []
    app.state.hub.publish = received.append  # перехватываем события шины
    assert client.post("/api/poll/dongchedi").json()["events"] == 2
    types = sorted(e.type for e in received)
    assert types == ["new", "price_changed"]
    assert all(f["id"] in e.matched_filters for e in received)

    report = client.get("/api/listings/encar/38912345/vin-report").json()
    assert report["decoded"]["manufacturer"] == "Hyundai"
    assert report["history"]["owner_changes"] == 2
    assert report["verdict"] == "danger"  # крупные выплаты по ДТП

    missing = client.get("/api/listings/dongchedi/17712346/vin-report")
    assert missing.status_code == 404


def test_vin_endpoints(app_env):
    client, _, _ = app_env
    r = client.get("/api/vin/LGXCE4CB0N0012345").json()
    assert r["verdict"] == "danger"
    d = client.get("/api/vin/LGXCE4CB8N0012345/decode").json()
    assert d["manufacturer"] == "BYD" and d["model_year"] == 2022
    assert client.get("/health").json()["ok"] is True
    assert client.get("/").status_code == 200


@pytest.mark.asyncio
async def test_event_hub_delivers():
    from renalauto.events import EventHub
    from renalauto.models import Listing

    hub = EventHub()
    listing = Listing(source="x", external_id="1", country="KR", url="u", title="t", currency="KRW")
    async with hub.subscribe() as q:
        hub.publish(ListingEvent(type="new", listing=listing))
        event = await asyncio.wait_for(q.get(), 1)
    assert event.listing.external_id == "1"
    assert hub.subscribers == 0
