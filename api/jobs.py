import asyncio
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.queries.jobs import create_job, get_job, update_job_status
from db.models import STEP_NAMES

router = APIRouter()


class CreateJobRequest(BaseModel):
    footage_id: int
    platform_flags: list[str]
    series_type: str = "standalone"
    series_id: int | None = None
    episode_number: int | None = None


@router.post("/api/jobs")
async def post_jobs(req: CreateJobRequest):
    job_id = create_job(
        footage_id=req.footage_id,
        platform_flags=req.platform_flags,
        series_type=req.series_type,
        series_id=req.series_id,
        episode_number=req.episode_number,
    )
    # Placeholder — real runner wired in step 6
    asyncio.create_task(asyncio.sleep(0))
    return {"job_id": job_id}


@router.get("/api/jobs/{job_id}")
async def get_job_route(job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/jobs/{job_id}/resume")
async def resume_job(job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "interrupted":
        raise HTTPException(status_code=400, detail="Job is not in interrupted state")
    update_job_status(job_id, "pending")
    # Placeholder — real runner wired in step 6
    asyncio.create_task(asyncio.sleep(0))
    return {"job_id": job_id, "status": "pending"}
