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
    generation_mode: str = "full_ai"
    topic: str | None = None
    raw_script: str | None = None
    manual_override_script: bool = False
    manual_override_voiceover: bool = False


class ReviewChoiceRequest(BaseModel):
    action: str  # continue | stop | edit_resubmit | force_accept
    edited_script: str | None = None


@router.post("/api/jobs")
async def post_jobs(req: CreateJobRequest):
    job_id = create_job(
        footage_id=req.footage_id,
        platform_flags=req.platform_flags,
        series_type=req.series_type,
        series_id=req.series_id,
        episode_number=req.episode_number,
    )
    # Store extra job params in DB for the runner to read
    from db.queries.jobs import update_job_status
    # We piggyback extra fields via a settings-style note — instead, store on job row
    # by updating with kwargs (update_job_status supports **kwargs)
    update_job_status(
        job_id,
        "pending",
        generation_mode=req.generation_mode,
        topic=req.topic,
        raw_script=req.raw_script,
        manual_override_script=int(req.manual_override_script),
        manual_override_voiceover=int(req.manual_override_voiceover),
    )
    from pipeline.runner import run
    asyncio.create_task(run(job_id))
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
    from pipeline.runner import run
    asyncio.create_task(run(job_id))
    return {"job_id": job_id, "status": "pending"}


@router.post("/api/jobs/{job_id}/review")
async def submit_review_choice(job_id: int, req: ReviewChoiceRequest):
    """User submits their choice at a human-in-the-loop review pause."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    from pipeline.runner import get_review_queue
    q = get_review_queue(job_id)
    q.put_nowait({"action": req.action, "edited_script": req.edited_script})
    return {"ok": True}
