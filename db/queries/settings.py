from db.connection import get_db


def get_setting(key: str) -> str | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT setting_value FROM settings WHERE setting_key = ?", (key,)
        ).fetchone()
        return row["setting_value"] if row else None


def set_setting(key: str, value: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (setting_key, setting_value) VALUES (?, ?)",
            (key, value),
        )


def get_all_settings() -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT setting_key, setting_value FROM settings").fetchall()
        return {row["setting_key"]: row["setting_value"] for row in rows}
