"""Хранилище на SQLite: объявления, история цен/пробега и сохранённые фильтры."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Literal

from .models import Listing, SavedFilter

UpsertStatus = Literal["new", "price_changed", "updated", "unchanged"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    country TEXT NOT NULL,
    make TEXT,
    model TEXT,
    year INTEGER,
    mileage_km INTEGER,
    price REAL,
    currency TEXT,
    price_usd REAL,
    vin TEXT,
    data TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (source, external_id)
);
CREATE INDEX IF NOT EXISTS ix_listings_vin ON listings (vin);
CREATE INDEX IF NOT EXISTS ix_listings_first_seen ON listings (first_seen);

-- Каждое изменение цены/пробега/VIN фиксируется: по этой таблице ловим скрутку пробега
-- и перевыставление одной машины под разными объявлениями.
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    vin TEXT,
    mileage_km INTEGER,
    price REAL,
    currency TEXT,
    seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_observations_vin ON observations (vin);
CREATE INDEX IF NOT EXISTS ix_observations_listing ON observations (source, external_id);

CREATE TABLE IF NOT EXISTS filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._conn.close()

    # --- объявления -------------------------------------------------------

    def get(self, source: str, external_id: str) -> Listing | None:
        row = self._conn.execute(
            "SELECT data FROM listings WHERE source = ? AND external_id = ?", (source, external_id)
        ).fetchone()
        return Listing.model_validate_json(row["data"]) if row else None

    def upsert(self, listing: Listing) -> tuple[UpsertStatus, Listing, float | None]:
        """Сохраняет объявление. Возвращает (статус, итоговое объявление, старая цена)."""
        with self._lock:
            now = _now()
            existing = self.get(*listing.key)
            if existing is None:
                merged = listing
                status: UpsertStatus = "new"
                old_price = None
            else:
                # Выдача поиска беднее карточки: не затираем VIN/номер и прочее пустыми значениями.
                update = {k: v for k, v in listing.model_dump().items() if v not in (None, {}, "")}
                update["extra"] = {**existing.extra, **listing.extra}
                merged = existing.model_copy(update=update)
                old_price = existing.price
                if merged.price != existing.price:
                    status = "price_changed"
                elif (merged.mileage_km, merged.vin, merged.plate) != (
                    existing.mileage_km,
                    existing.vin,
                    existing.plate,
                ):
                    status = "updated"
                else:
                    status = "unchanged"

            self._conn.execute(
                """
                INSERT INTO listings (source, external_id, country, make, model, year, mileage_km,
                                      price, currency, price_usd, vin, data, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source, external_id) DO UPDATE SET
                    country = excluded.country, make = excluded.make, model = excluded.model,
                    year = excluded.year, mileage_km = excluded.mileage_km, price = excluded.price,
                    currency = excluded.currency, price_usd = excluded.price_usd, vin = excluded.vin,
                    data = excluded.data, last_seen = excluded.last_seen
                """,
                (
                    merged.source,
                    merged.external_id,
                    merged.country,
                    merged.make,
                    merged.model,
                    merged.year,
                    merged.mileage_km,
                    merged.price,
                    merged.currency,
                    merged.price_usd,
                    merged.vin,
                    merged.model_dump_json(),
                    now,
                    now,
                ),
            )
            if status != "unchanged":
                self._conn.execute(
                    "INSERT INTO observations (source, external_id, vin, mileage_km, price, currency, seen_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        merged.source,
                        merged.external_id,
                        merged.vin,
                        merged.mileage_km,
                        merged.price,
                        merged.currency,
                        now,
                    ),
                )
                if merged.vin:
                    # VIN мог появиться только после загрузки карточки — проставляем его
                    # в ранних наблюдениях этого же объявления.
                    self._conn.execute(
                        "UPDATE observations SET vin = ? WHERE source = ? AND external_id = ? AND vin IS NULL",
                        (merged.vin, merged.source, merged.external_id),
                    )
            self._conn.commit()
            return status, merged, old_price

    def count(self, source: str | None = None) -> int:
        if source:
            row = self._conn.execute("SELECT COUNT(*) FROM listings WHERE source = ?", (source,)).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM listings").fetchone()
        return row[0]

    def search(
        self,
        *,
        source: str | None = None,
        country: str | None = None,
        make: str | None = None,
        model: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        mileage_max: int | None = None,
        price_usd_max: float | None = None,
        vin: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Listing]:
        where, params = [], []
        for column, value in (("source", source), ("country", country), ("vin", vin)):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        for column, value in (("make", make), ("model", model)):
            if value:
                where.append(f"{column} LIKE ?")
                params.append(f"%{value}%")
        for clause, value in (
            ("year >= ?", year_from),
            ("year <= ?", year_to),
            ("mileage_km <= ?", mileage_max),
            ("price_usd <= ?", price_usd_max),
        ):
            if value is not None:
                where.append(clause)
                params.append(value)
        sql = "SELECT data FROM listings"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY first_seen DESC, rowid DESC LIMIT ? OFFSET ?"
        rows = self._conn.execute(sql, (*params, limit, offset)).fetchall()
        return [Listing.model_validate_json(r["data"]) for r in rows]

    def observations_for_vin(self, vin: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT source, external_id, mileage_km, price, currency, seen_at FROM observations"
            " WHERE vin = ? ORDER BY seen_at, id",
            (vin,),
        ).fetchall()
        return [dict(r) for r in rows]

    def history(self, source: str, external_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT mileage_km, price, currency, seen_at FROM observations"
            " WHERE source = ? AND external_id = ? ORDER BY seen_at, id",
            (source, external_id),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- фильтры ----------------------------------------------------------

    def add_filter(self, flt: SavedFilter) -> SavedFilter:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO filters (data) VALUES (?)", (flt.model_dump_json(exclude={"id"}),)
            )
            self._conn.commit()
            return flt.model_copy(update={"id": cur.lastrowid})

    def list_filters(self) -> list[SavedFilter]:
        rows = self._conn.execute("SELECT id, data FROM filters ORDER BY id").fetchall()
        return [SavedFilter.model_validate_json(r["data"]).model_copy(update={"id": r["id"]}) for r in rows]

    def delete_filter(self, filter_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM filters WHERE id = ?", (filter_id,))
            self._conn.commit()
            return cur.rowcount > 0
