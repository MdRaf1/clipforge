from datetime import datetime, timezone
from db.connection import get_db


def add_footage(filename: str, path: str, duration: float | None = None) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO footage (filename, path, duration, created_at) VALUES (?, ?, ?, ?)",
            (filename, path, duration, datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def get_footage(footage_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM footage WHERE id = ?", (footage_id,)).fetchone()
        return dict(row) if row else None


def list_footage() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM footage ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def delete_footage(footage_id: int) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM footage WHERE id = ?", (footage_id,))
