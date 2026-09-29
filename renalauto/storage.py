"""Хранилище на SQLite: объявления, история цен/пробега и сохранённые фильтры."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Literal

from . import i18n
from .models import Lead, LeadIn, Listing, SavedFilter

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

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_leads_created ON leads (created_at);

CREATE TABLE IF NOT EXISTS filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL
);
"""


def _passable(listing: Listing) -> int:
    from .eligibility import evaluate  # локальный импорт: eligibility зависит от models

    return 0 if evaluate(listing).verdict == "bad" else 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()
        self._migrate()

    def _migrate(self) -> None:
        columns = {r["name"] for r in self._conn.execute("PRAGMA table_info(listings)")}
        if "passable" not in columns:
            # 1 — можно привезти в РФ (или нужно уточнить), 0 — не проходит; такие на сайте не показываем
            self._conn.execute("ALTER TABLE listings ADD COLUMN passable INTEGER")
        self._conn.execute("CREATE INDEX IF NOT EXISTS ix_listings_passable ON listings (passable, first_seen)")
        rows = self._conn.execute(
            "SELECT source, external_id, data FROM listings WHERE passable IS NULL"
        ).fetchall()
        for r in rows:
            listing = Listing.model_validate_json(r["data"])
            self._conn.execute(
                "UPDATE listings SET passable = ? WHERE source = ? AND external_id = ?",
                (_passable(listing), r["source"], r["external_id"]),
            )
        self._conn.commit()

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
                                      price, currency, price_usd, vin, data, first_seen, last_seen, passable)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source, external_id) DO UPDATE SET
                    country = excluded.country, make = excluded.make, model = excluded.model,
                    year = excluded.year, mileage_km = excluded.mileage_km, price = excluded.price,
                    currency = excluded.currency, price_usd = excluded.price_usd, vin = excluded.vin,
                    data = excluded.data, last_seen = excluded.last_seen, passable = excluded.passable
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
                    _passable(merged),
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

    SORTS = {
        "new": "first_seen DESC, rowid DESC",
        "price_asc": "price_usd IS NULL, price_usd ASC",
        "price_desc": "price_usd DESC",
        "year_desc": "year IS NULL, year DESC, first_seen DESC",
        "mileage_asc": "mileage_km IS NULL, mileage_km ASC",
    }

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
        plate: str | None = None,
        fuels: list[str] | None = None,
        passable_only: bool = False,
        query: str | None = None,
        sort: str = "new",
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
                # «Hyundai» находит и «현대», и «现代»
                aliases = i18n.search_aliases(value)
                where.append("(" + " OR ".join(f"{column} LIKE ?" for _ in aliases) + ")")
                params.extend(f"%{a}%" for a in aliases)
        if passable_only:
            where.append("passable != 0")
        if plate:
            where.append("REPLACE(json_extract(data, '$.plate'), ' ', '') = ?")
            params.append(plate.replace(" ", ""))
        if query:
            aliases = i18n.search_aliases(query)
            where.append("(" + " OR ".join("json_extract(data, '$.title') LIKE ?" for _ in aliases) + ")")
            params.extend(f"%{a}%" for a in aliases)
        if fuels:
            where.append("(" + " OR ".join("json_extract(data, '$.fuel') LIKE ?" for _ in fuels) + ")")
            params.extend(f"%{f}%" for f in fuels)
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
        sql += f" ORDER BY {self.SORTS.get(sort, self.SORTS['new'])} LIMIT ? OFFSET ?"
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

    # --- заявки ------------------------------------------------------------

    def add_lead(self, lead: LeadIn, listing: Listing | None = None) -> Lead:
        with self._lock:
            now = _now()
            data = lead.model_dump(exclude={"website"})
            if listing:
                data["listing_title"] = listing.title
                data["listing_url"] = listing.url
                data["plate"] = listing.plate
                data["vin"] = listing.vin
            cur = self._conn.execute(
                "INSERT INTO leads (created_at, status, data) VALUES (?, 'new', ?)", (now, json.dumps(data, ensure_ascii=False))
            )
            self._conn.commit()
            return Lead(id=cur.lastrowid, created_at=now, **data)

    def _lead_from_row(self, row: sqlite3.Row) -> Lead:
        return Lead(id=row["id"], created_at=row["created_at"], status=row["status"], **json.loads(row["data"]))

    def list_leads(self, status: str | None = None, limit: int = 200) -> list[Lead]:
        sql, params = "SELECT id, created_at, status, data FROM leads", []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        rows = self._conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*params, limit)).fetchall()
        return [self._lead_from_row(r) for r in rows]

    def update_lead(self, lead_id: int, status: str | None = None, manager_note: str | None = None) -> Lead | None:
        with self._lock:
            row = self._conn.execute("SELECT id, created_at, status, data FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if row is None:
                return None
            data = json.loads(row["data"])
            if manager_note is not None:
                data["manager_note"] = manager_note
            new_status = status or row["status"]
            self._conn.execute(
                "UPDATE leads SET status = ?, data = ? WHERE id = ?",
                (new_status, json.dumps(data, ensure_ascii=False), lead_id),
            )
            self._conn.commit()
            return Lead(id=lead_id, created_at=row["created_at"], status=new_status, **data)

    def lead_stats(self) -> dict[str, int]:
        rows = self._conn.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status").fetchall()
        stats = {"new": 0, "in_work": 0, "deal": 0, "lost": 0}
        stats.update({r["status"]: r["n"] for r in rows})
        stats["total"] = sum(v for k, v in stats.items() if k != "total")
        return stats

    def recent_listing_keys(self, limit: int = 5000) -> list[tuple[str, str, str]]:
        rows = self._conn.execute(
            "SELECT source, external_id, last_seen FROM listings WHERE passable != 0 ORDER BY last_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [(r["source"], r["external_id"], r["last_seen"]) for r in rows]
