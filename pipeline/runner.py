import asyncio
import json
import os

from config import OUTPUTS_DIR
from db.queries.jobs import get_job, update_job_status, update_job_step
from db.queries.footage import get_footage
from db.queries.settings import get_setting
from pipeline.checkpoint import save_step, load_checkpoint, get_resume_step
from pipeline.steps.script import run_script_step, HumanInTheLoopPause
from pipeline.steps.voiceover import run_voiceover_step
from pipeline.steps.cutting import run_cutting_step
from pipeline.steps.subtitles import run_subtitles_step
from pipeline.steps.render import run_render_step
from pipeline.steps.thumbnail import run_thumbnail_step
from pipeline.steps.metadata import run_metadata_step
from api.ws import push_event
from utils.logger import get_logger

logger = get_logger(__name__)

# Per-job queues for human-in-the-loop resume responses.
# The API layer puts a user choice dict here; the runner awaits it.
_review_queues: dict[int, asyncio.Queue] = {}


def get_review_queue(job_id: int) -> asyncio.Queue:
    if job_id not in _review_queues:
        _review_queues[job_id] = asyncio.Queue()
    return _review_queues[job_id]


async def run(job_id: int) -> None:
    job = get_job(job_id)
    if not job:
        logger.error("runner.run: job %d not found", job_id)
        return

    footage = get_footage(job["footage_id"])
    if not footage:
        logger.error("runner.run: footage %d not found", job["footage_id"])
        update_job_status(job_id, "failed")
        return

    output_dir = os.path.join(OUTPUTS_DIR, str(job_id))
    os.makedirs(output_dir, exist_ok=True)

    update_job_status(job_id, "in_progress")
    resume_from = get_resume_step(job_id)
    checkpoints = load_checkpoint(job_id)

    platform_flags = json.loads(job["platform_flags"])
    series_type = job.get("series_type") or "standalone"

    max_retries = int(get_setting("max_retries") or 3)

    # ---- Step: script ----
    if _should_run("script", resume_from, checkpoints):
        script_result = await _run_step(job_id, "script", max_retries, _exec_script, job, output_dir)
        if script_result is None:
            return
        checkpoints["script"] = script_result

    script_data = checkpoints["script"]
    script_full = script_data["full"]
    script_short = script_data["short"]

    # ---- Step: voiceover_full ----
    if _should_run("voiceover_full", resume_from, checkpoints):
        manual_vo = job.get("manual_override_voiceover", False)
        result = await _run_step(
            job_id, "voiceover_full", max_retries,
            _exec_voiceover, job_id, script_full, script_short, output_dir, manual_vo,
        )
        if result is None:
            return
        checkpoints["voiceover_full"] = result

    # voiceover_short is included in the voiceover_full step output
    if "voiceover_short" not in checkpoints and "voiceover_full" in checkpoints:
        save_step(job_id, "voiceover_short", checkpoints["voiceover_full"])
        checkpoints["voiceover_short"] = checkpoints["voiceover_full"]
        _mark_step_done_in_db(job_id, "voiceover_short", checkpoints["voiceover_full"])

    vo_data = checkpoints["voiceover_full"]
    voiceover_full_path = vo_data["voiceover_full_path"]
    voiceover_short_path = vo_data["voiceover_short_path"]

    # ---- Step: cutting_full ----
    if _should_run("cutting_full", resume_from, checkpoints):
        result = await _run_step(
            job_id, "cutting_full", max_retries,
            _exec_cutting, job_id, footage["path"], output_dir,
        )
        if result is None:
            return
        checkpoints["cutting_full"] = result

    # cutting_short shares the same step output
    if "cutting_short" not in checkpoints and "cutting_full" in checkpoints:
        save_step(job_id, "cutting_short", checkpoints["cutting_full"])
        checkpoints["cutting_short"] = checkpoints["cutting_full"]
        _mark_step_done_in_db(job_id, "cutting_short", checkpoints["cutting_full"])

    cut_data = checkpoints["cutting_full"]
    footage_full_path = cut_data["footage_full_path"]
    footage_short_path = cut_data["footage_short_path"]

    # ---- Step: subtitles_full ----
    if _should_run("subtitles_full", resume_from, checkpoints):
        result = await _run_step(
            job_id, "subtitles_full", max_retries,
            _exec_subtitles, job_id, voiceover_full_path, voiceover_short_path, output_dir,
        )
        if result is None:
            return
        checkpoints["subtitles_full"] = result

    if "subtitles_short" not in checkpoints and "subtitles_full" in checkpoints:
        save_step(job_id, "subtitles_short", checkpoints["subtitles_full"])
        checkpoints["subtitles_short"] = checkpoints["subtitles_full"]
        _mark_step_done_in_db(job_id, "subtitles_short", checkpoints["subtitles_full"])

    srt_data = checkpoints["subtitles_full"]
    srt_full_path = srt_data["srt_full_path"]
    srt_short_path = srt_data["srt_short_path"]

    # ---- Step: render_full ----
    if _should_run("render_full", resume_from, checkpoints):
        result = await _run_step(
            job_id, "render_full", max_retries,
            _exec_render, job_id,
            footage_full_path, footage_short_path,
            voiceover_full_path, voiceover_short_path,
            srt_full_path, srt_short_path,
            output_dir,
        )
        if result is None:
            return
        checkpoints["render_full"] = result

    if "render_short" not in checkpoints and "render_full" in checkpoints:
        save_step(job_id, "render_short", checkpoints["render_full"])
        checkpoints["render_short"] = checkpoints["render_full"]
        _mark_step_done_in_db(job_id, "render_short", checkpoints["render_full"])

    render_data = checkpoints["render_full"]
    video_full_path = render_data["video_full_path"]
    video_short_path = render_data["video_short_path"]

    # ---- Step: thumbnail ----
    if _should_run("thumbnail", resume_from, checkpoints):
        result = await _run_step(
            job_id, "thumbnail", max_retries,
            _exec_thumbnail, job_id, footage_full_path, script_full, output_dir,
        )
        if result is None:
            return
        checkpoints["thumbnail"] = result

    thumbnail_path = checkpoints["thumbnail"]["thumbnail_path"]

    # ---- Step: metadata ----
    if _should_run("metadata", resume_from, checkpoints):
        result = await _run_step(
            job_id, "metadata", max_retries,
            _exec_metadata, job_id, script_full, script_short, platform_flags, output_dir,
            series_type, job,
        )
        if result is None:
            return
        checkpoints["metadata"] = result

    metadata_path = checkpoints["metadata"]["metadata_path"]

    # ---- Pipeline complete ----
    update_job_status(
        job_id, "complete",
        output_video_full_path=video_full_path,
        output_video_short_path=video_short_path,
        output_thumbnail_path=thumbnail_path,
        title=checkpoints["metadata"].get("metadata", {}).get("tiktok", {}).get("title", ""),
    )
    push_event(job_id, {
        "type": "complete",
        "video_full": video_full_path,
        "video_short": video_short_path,
        "thumbnail": thumbnail_path,
        "metadata": metadata_path,
    })
    logger.info("runner: job %d complete", job_id)


# ---------------------------------------------------------------------------
# Step executors
# ---------------------------------------------------------------------------

async def _exec_script(job: dict, output_dir: str) -> dict:
    """Run the script step; handles HumanInTheLoopPause internally."""
    job_id = job["id"]
    platform_flags = json.loads(job["platform_flags"])

    mode = job.get("generation_mode") or "full_ai"
    topic = job.get("topic")
    raw_script = job.get("raw_script")
    manual_override_script = bool(job.get("manual_override_script"))

    while True:
        try:
            result = await run_script_step(
                job_id=job_id,
                mode=mode,
                topic=topic,
                raw_script=raw_script,
                manual_override_script=manual_override_script,
            )
            return {"full": result.full, "short": result.short, "score": result.score}

        except HumanInTheLoopPause as pause:
            # Tell frontend to show review UI
            push_event(job_id, {
                "type": "review_pause",
                "script": pause.script,
                "score": pause.score,
                "user_summary": pause.user_summary,
            })
            update_job_status(job_id, "paused")

            # Wait for user response via POST /api/jobs/{id}/review
            q = get_review_queue(job_id)
            choice = await q.get()  # dict: {action, edited_script?}

            action = choice.get("action")
            if action == "stop":
                raise RuntimeError("User stopped pipeline at review pause")
            elif action == "force_accept":
                return {"full": pause.script, "short": pause.script, "score": pause.score}
            elif action == "edit_resubmit":
                raw_script = choice.get("edited_script", pause.script)
                manual_override_script = False
                mode = "manual"
            elif action == "continue":
                pass  # loop back to retry
            else:
                raise RuntimeError(f"Unknown review action: {action}")

            update_job_status(job_id, "in_progress")


async def _exec_voiceover(
    job_id: int,
    script_full: str,
    script_short: str,
    output_dir: str,
    manual_override_voiceover: bool,
) -> dict:
    return await run_voiceover_step(
        job_id=job_id,
        script_full=script_full,
        script_short=script_short,
        output_dir=output_dir,
        manual_override_voiceover=manual_override_voiceover,
    )


async def _exec_cutting(job_id: int, footage_path: str, output_dir: str) -> dict:
    return await run_cutting_step(
        job_id=job_id,
        footage_path=footage_path,
        output_dir=output_dir,
    )


async def _exec_subtitles(
    job_id: int,
    voiceover_full_path: str,
    voiceover_short_path: str,
    output_dir: str,
) -> dict:
    return await run_subtitles_step(
        job_id=job_id,
        voiceover_full_path=voiceover_full_path,
        voiceover_short_path=voiceover_short_path,
        output_dir=output_dir,
    )


async def _exec_render(
    job_id: int,
    footage_full_path: str,
    footage_short_path: str,
    voiceover_full_path: str,
    voiceover_short_path: str,
    srt_full_path: str,
    srt_short_path: str,
    output_dir: str,
) -> dict:
    return await run_render_step(
        job_id=job_id,
        footage_full_path=footage_full_path,
        footage_short_path=footage_short_path,
        voiceover_full_path=voiceover_full_path,
        voiceover_short_path=voiceover_short_path,
        srt_full_path=srt_full_path,
        srt_short_path=srt_short_path,
        output_dir=output_dir,
    )


async def _exec_thumbnail(
    job_id: int,
    footage_full_path: str,
    script_full: str,
    output_dir: str,
) -> dict:
    return await run_thumbnail_step(
        job_id=job_id,
        footage_full_path=footage_full_path,
        script_full=script_full,
        output_dir=output_dir,
    )


async def _exec_metadata(
    job_id: int,
    script_full: str,
    script_short: str,
    platform_flags: list[str],
    output_dir: str,
    series_type: str,
    job: dict,
) -> dict:
    series_name = None
    episode_number = None
    if series_type in ("first_episode", "continuation") and job.get("series_id"):
        from db.queries.series import get_series
        series = get_series(job["series_id"])
        if series:
            series_name = series.get("name")
            episode_number = job.get("episode_number")

    return await run_metadata_step(
        job_id=job_id,
        script_full=script_full,
        script_short=script_short,
        platform_flags=platform_flags,
        output_dir=output_dir,
        series_type=series_type,
        series_name=series_name,
        episode_number=episode_number,
    )


# ---------------------------------------------------------------------------
# Runner helpers
# ---------------------------------------------------------------------------

def _should_run(step_name: str, resume_from: str | None, checkpoints: dict) -> bool:
    if step_name in checkpoints:
        return False
    if resume_from is None:
        return True
    from db.models import STEP_NAMES
    steps = STEP_NAMES
    if step_name not in steps or resume_from not in steps:
        return True
    return steps.index(step_name) >= steps.index(resume_from)


async def _run_step(job_id: int, step_name: str, max_retries: int, fn, *args) -> dict | None:
    """Run fn(*args), updating step status and WebSocket events. Returns output dict or None on terminal failure."""
    STEP_LABELS = {
        "script": "Generating script…",
        "voiceover_full": "Creating voiceover…",
        "voiceover_short": "Creating voiceover (short)…",
        "cutting_full": "Cutting footage…",
        "cutting_short": "Cutting footage (short)…",
        "subtitles_full": "Generating subtitles…",
        "subtitles_short": "Generating subtitles (short)…",
        "render_full": "Rendering video…",
        "render_short": "Rendering video (short)…",
        "thumbnail": "Creating thumbnail…",
        "metadata": "Generating metadata…",
    }

    update_job_step(job_id, step_name, "in_progress")
    push_event(job_id, {
        "type": "step_update",
        "step": step_name,
        "status": "in_progress",
        "message": STEP_LABELS.get(step_name, f"Running {step_name}…"),
    })

    last_error = None
    for attempt in range(max_retries):
        try:
            output = await fn(*args)
            save_step(job_id, step_name, output)
            update_job_step(job_id, step_name, "done", output)
            push_event(job_id, {"type": "step_update", "step": step_name, "status": "done"})
            return output
        except Exception as e:
            last_error = e
            logger.warning("Step %s attempt %d/%d failed: %s", step_name, attempt + 1, max_retries, e)

    # All retries exhausted
    logger.error("Step %s failed after %d retries: %s", step_name, max_retries, last_error)
    update_job_step(job_id, step_name, "failed")
    update_job_status(job_id, "paused")
    push_event(job_id, {
        "type": "step_update",
        "step": step_name,
        "status": "failed",
        "message": str(last_error),
    })
    return None


def _mark_step_done_in_db(job_id: int, step_name: str, output: dict) -> None:
    update_job_step(job_id, step_name, "done", output)
    push_event(job_id, {"type": "step_update", "step": step_name, "status": "done"})
