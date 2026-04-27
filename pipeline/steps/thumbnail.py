import os

from ai.providers import get_ai_client
from ai.prompts.thumbnail import THUMBNAIL_HOOK_PROMPT
from media.ffmpeg import detect_peak_motion_timestamp, extract_frame
from media.pillow import add_text_overlay
from utils.logger import get_logger

logger = get_logger(__name__)


async def run_thumbnail_step(
    job_id: int,
    footage_full_path: str,
    script_full: str,
    output_dir: str,
    thumbnail_mode: str = "auto",
    pick_timestamp: float | None = None,
    upload_image_path: str | None = None,
) -> dict:
    thumbnail_path = os.path.join(output_dir, "thumbnail.jpg")
    raw_frame_path = os.path.join(output_dir, "thumbnail_raw.jpg")

    # Generate hook text via Gemini
    logger.info("thumbnail: generating hook text via Gemini")
    client = get_ai_client()
    hook_text = await client.generate(THUMBNAIL_HOOK_PROMPT.format(script=script_full[:1000]))
    hook_text = str(hook_text).strip().strip('"')

    if thumbnail_mode == "upload_own" and upload_image_path:
        logger.info("thumbnail: using user-uploaded image")
        raw_frame_path = upload_image_path
    elif thumbnail_mode == "pick_frame" and pick_timestamp is not None:
        logger.info("thumbnail: extracting frame at ts=%.2f", pick_timestamp)
        await extract_frame(footage_full_path, pick_timestamp, raw_frame_path)
    else:
        # Auto: pick peak motion frame
        logger.info("thumbnail: detecting peak motion frame")
        ts = await detect_peak_motion_timestamp(footage_full_path)
        logger.info("thumbnail: extracting frame at ts=%.2f", ts)
        await extract_frame(footage_full_path, ts, raw_frame_path)

    logger.info("thumbnail: adding text overlay: %r", hook_text)
    await add_text_overlay(raw_frame_path, hook_text, thumbnail_path)

    return {
        "thumbnail_path": thumbnail_path,
        "hook_text": hook_text,
    }
