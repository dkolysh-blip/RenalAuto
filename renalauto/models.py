from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import i18n


class Listing(BaseModel):
    """Объявление, приведённое к единому виду независимо от площадки."""

    source: str
    external_id: str
    country: Literal["KR", "CN"]
    url: str
    title: str
    make: str | None = None
    model: str | None = None
    trim: str | None = None
    year: int | None = None
    mileage_km: int | None = None
    price: float | None = None  # в валюте площадки, в полных единицах (вон, юань)
    currency: str
    price_usd: float | None = None
    fuel: str | None = None
    transmission: str | None = None
    location: str | None = None
    photo: str | None = None
    vin: str | None = None
    plate: str | None = None
    listed_at: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        return self.source, self.external_id


class SavedFilter(BaseModel):
    """Сохранённый поиск: новые объявления, попавшие под него, уходят в поток и Telegram."""

    id: int | None = None
    name: str
    source: str | None = None
    country: Literal["KR", "CN"] | None = None
    make: str | None = None
    model: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    mileage_max: int | None = None
    price_usd_max: float | None = None
    query: str | None = None
    telegram_chat_id: str | None = None

    def matches(self, listing: Listing) -> bool:
        def contains(needle: str | None, *haystack: str | None) -> bool:
            if not needle:
                return True
            # «Hyundai» совпадает и с «현대», и с «现代»
            needles = [n.lower() for n in i18n.search_aliases(needle)]
            return any(n in h.lower() for h in haystack if h for n in needles)

        if self.source and listing.source != self.source:
            return False
        if self.country and listing.country != self.country:
            return False
        if not contains(self.make, listing.make, listing.title):
            return False
        if not contains(self.model, listing.model, listing.title):
            return False
        if not contains(self.query, listing.title, listing.trim, listing.location):
            return False
        if self.year_from and (listing.year is None or listing.year < self.year_from):
            return False
        if self.year_to and (listing.year is None or listing.year > self.year_to):
            return False
        if self.mileage_max and (listing.mileage_km is None or listing.mileage_km > self.mileage_max):
            return False
        if self.price_usd_max and (listing.price_usd is None or listing.price_usd > self.price_usd_max):
            return False
        return True


class ListingEvent(BaseModel):
    type: Literal["new", "price_changed", "updated"]
    listing: Listing
    old_price: float | None = None
    matched_filters: list[int] = Field(default_factory=list)


LeadStatus = Literal["new", "in_work", "deal", "lost"]


class LeadIn(BaseModel):
    """Заявка с сайта: расчёт доставки конкретной машины или подбор под бюджет."""

    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=40)
    telegram: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=2000)
    city: str | None = Field(default=None, max_length=100)
    budget_rub: int | None = Field(default=None, ge=0, le=1_000_000_000)
    source: str | None = Field(default=None, max_length=32)
    external_id: str | None = Field(default=None, max_length=64)
    page: str | None = Field(default=None, max_length=500)
    website: str | None = None  # ловушка для ботов: поле скрыто, люди его не заполняют


class Lead(LeadIn):
    id: int
    created_at: str
    status: LeadStatus = "new"
    listing_title: str | None = None
    listing_url: str | None = None
    manager_note: str | None = None
