import os
import shutil
from fastapi import APIRouter, HTTPException
from config import OUTPUTS_DIR
from db.queries.jobs import get_job, list_jobs, delete_job

router = APIRouter()


@router.get("/api/history")
async def get_history():
    jobs = list_jobs()
    return [
        {"id": j["id"], "title": j.get("title") or f"Job #{j['id']}", "created_at": j["created_at"]}
        for j in jobs
    ]


@router.get("/api/history/{job_id}")
async def get_history_detail(job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/api/history/{job_id}")
async def delete_history(job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Remove output files from disk
    output_dir = os.path.join(OUTPUTS_DIR, str(job_id))
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    delete_job(job_id)
    return {"deleted": job_id}
