import json
from db.connection import get_db
from db.models import STEP_NAMES


def save_step(job_id: int, step_name: str, output: dict) -> None:
    with get_db() as conn:
        conn.execute(
            """UPDATE job_steps SET status = 'done', output_json = ?, completed_at = datetime('now')
               WHERE job_id = ? AND step_name = ?""",
            (json.dumps(output), job_id, step_name),
        )


def load_checkpoint(job_id: int) -> dict:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT step_name, output_json FROM job_steps WHERE job_id = ? AND status = 'done'",
            (job_id,),
        ).fetchall()
    return {
        row["step_name"]: json.loads(row["output_json"])
        for row in rows
        if row["output_json"]
    }


def get_resume_step(job_id: int) -> str | None:
    with get_db() as conn:
        row = conn.execute(
            """SELECT step_name FROM job_steps
               WHERE job_id = ? AND status != 'done'
               ORDER BY id ASC LIMIT 1""",
            (job_id,),
        ).fetchone()
    if row:
        return row["step_name"]
    return None
