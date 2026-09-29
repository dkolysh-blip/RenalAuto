from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import httpx

from ..config import Settings
from ..models import Listing


class SourceError(RuntimeError):
    pass


class Source(ABC):
    """Адаптер одной площадки.

    Чтобы подключить новую площадку (KB Chachacha, Che168, Guazi ...), достаточно
    унаследоваться, реализовать fetch_latest (и при возможности fetch_detail)
    и зарегистрировать класс в renalauto.sources.REGISTRY.
    """

    name: ClassVar[str]
    country: ClassVar[str]
    currency: ClassVar[str]

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client
        self._owns_client = client is None

    @property
    def proxy(self) -> str | None:
        return self.settings.proxy_kr if self.country == "KR" else self.settings.proxy_cn

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.settings.http_timeout,
                headers={"User-Agent": self.settings.user_agent, "Accept": "application/json, */*"},
                proxy=self.proxy,
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    async def _get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self.client.get(url, **kwargs)
        return self._json(response)

    async def _post_json(self, url: str, **kwargs: Any) -> Any:
        response = await self.client.post(url, **kwargs)
        return self._json(response)

    def _json(self, response: httpx.Response) -> Any:
        if response.status_code >= 400:
            raise SourceError(f"{self.name}: HTTP {response.status_code} for {response.request.url}")
        try:
            return response.json()
        except ValueError as exc:
            raise SourceError(f"{self.name}: non-JSON response from {response.request.url}") from exc

    @abstractmethod
    async def fetch_latest(self, limit: int = 50, **filters: Any) -> list[Listing]:
        """Свежие объявления, новые — первыми."""

    async def fetch_detail(self, listing: Listing) -> Listing:
        """Дополняет объявление данными из карточки (VIN, госномер). По умолчанию — ничего."""
        return listing

    async def fetch_history(self, listing: Listing) -> dict[str, Any] | None:
        """История авто от площадки (ДТП, владельцы). None, если площадка её не отдаёт."""
        return None


_NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _NUM_RE.search(str(value).replace(" ", ""))
    return float(match.group().replace(",", ".")) if match else None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    return int(round(number)) if number is not None else None
