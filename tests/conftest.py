import json
from pathlib import Path

import httpx
import pytest

from renalauto.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def settings(tmp_path, monkeypatch):
    # старые тесты Encar проверяют режим API; режим web — в test_encar_web.py
    monkeypatch.setenv("ENCAR_MODE", "api")
    s = Settings()
    s.db_path = str(tmp_path / "test.db")
    s.poller_enabled = False
    s.vin_nhtsa = False
    s.telegram_bot_token = None
    s.admin_token = "secret"
    s.rates_live = False
    return s


ADMIN = {"X-Admin-Token": "secret"}


def mock_client(routes: dict[str, object]) -> httpx.AsyncClient:
    """routes: подстрока пути -> JSON-ответ (или callable(request) -> JSON)."""

    def handler(request: httpx.Request) -> httpx.Response:
        for needle, body in routes.items():
            if needle in request.url.path:
                payload = body(request) if callable(body) else body
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not mocked", "path": request.url.path})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
