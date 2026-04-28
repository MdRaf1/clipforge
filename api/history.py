import io
import os
import shutil
import zipfile
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from config import OUTPUTS_DIR
from db.queries.jobs import get_job, list_jobs, delete_job

router = APIRouter()


@router.get("/api/history")
async def get_history():
    jobs = list_jobs()
    return [
        {
            "id": j["id"],
            "title": j.get("title") or f"Job #{j['id']}",
            "created_at": j["created_at"],
            "status": j.get("status"),
        }
        for j in jobs
    ]


@router.get("/api/history/{job_id}")
async def get_history_detail(job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/history/{job_id}/open-folder")
async def open_output_folder(job_id: int):
    """Open the job's output directory in the host OS file explorer (localhost only)."""
    import subprocess
    import sys
    output_dir = os.path.join(OUTPUTS_DIR, str(job_id))
    if not os.path.isdir(output_dir):
        raise HTTPException(status_code=404, detail="No outputs on disk for this job")
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", output_dir])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", output_dir])
        else:
            subprocess.Popen(["xdg-open", output_dir])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {e}")
    return {"ok": True, "path": output_dir}


@router.get("/api/history/{job_id}/zip")
async def download_job_zip(job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output_dir = os.path.join(OUTPUTS_DIR, str(job_id))
    if not os.path.isdir(output_dir):
        raise HTTPException(status_code=404, detail="No outputs on disk for this job")

    buf = io.BytesIO()
    # ZIP_STORED avoids re-encoding — spec requires lossless bundle.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for name in os.listdir(output_dir):
            full = os.path.join(output_dir, name)
            if os.path.isfile(full):
                zf.write(full, arcname=name)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="clipforge-job-{job_id}.zip"'},
    )


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
