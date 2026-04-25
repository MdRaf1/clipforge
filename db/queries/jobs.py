import json
from datetime import datetime, timezone
from db.connection import get_db
from db.models import STEP_NAMES


def create_job(
    footage_id: int,
    platform_flags: list[str],
    series_type: str = "standalone",
    series_id: int | None = None,
    episode_number: int | None = None,
) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO jobs
               (footage_id, platform_flags, series_type, series_id, episode_number, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (
                footage_id,
                json.dumps(platform_flags),
                series_type,
                series_id,
                episode_number,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        job_id = cur.lastrowid
        for step_name in STEP_NAMES:
            conn.execute(
                "INSERT INTO job_steps (job_id, step_name, status) VALUES (?, ?, 'pending')",
                (job_id, step_name),
            )
        return job_id


def get_job(job_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        job = dict(row)
        steps = conn.execute(
            "SELECT * FROM job_steps WHERE job_id = ? ORDER BY id ASC", (job_id,)
        ).fetchall()
        job["steps"] = [dict(s) for s in steps]
        return job


def update_job_status(job_id: int, status: str, **kwargs) -> None:
    fields = ["status = ?"]
    values = [status]
    for k, v in kwargs.items():
        fields.append(f"{k} = ?")
        values.append(v)
    values.append(job_id)
    with get_db() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)


def update_job_step(job_id: int, step_name: str, status: str, output_json: dict | None = None) -> None:
    completed_at = datetime.now(timezone.utc).isoformat() if status == "done" else None
    with get_db() as conn:
        conn.execute(
            """UPDATE job_steps SET status = ?, output_json = ?, completed_at = ?
               WHERE job_id = ? AND step_name = ?""",
            (status, json.dumps(output_json) if output_json else None, completed_at, job_id, step_name),
        )


def list_jobs() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def delete_job(job_id: int) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM job_steps WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
