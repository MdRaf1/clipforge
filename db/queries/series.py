import json
from datetime import datetime, timezone
from db.connection import get_db


def create_series(name: str) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO series (name, created_at) VALUES (?, ?)",
            (name, datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def get_series(series_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM series WHERE id = ?", (series_id,)).fetchone()
        return dict(row) if row else None


def list_series() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM series WHERE status = 'active' ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def append_series_entry(
    series_id: int,
    part_number: int,
    script_json: dict,
    unprocessed_remainder: str | None = None,
) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO series_entries (series_id, part_number, script_json, unprocessed_remainder) VALUES (?, ?, ?, ?)",
            (series_id, part_number, json.dumps(script_json), unprocessed_remainder),
        )
        return cur.lastrowid


def get_series_entries(series_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM series_entries WHERE series_id = ? ORDER BY part_number ASC",
            (series_id,),
        ).fetchall()
        return [dict(r) for r in rows]
