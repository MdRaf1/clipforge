import os

from db.queries.settings import get_setting
from media.ffmpeg import assemble_video, burn_subtitles, apply_rainbow_border
from utils.logger import get_logger

logger = get_logger(__name__)


async def _render_track(
    footage_path: str,
    audio_path: str,
    srt_path: str,
    output_path: str,
    rainbow_border: bool,
    tmp_dir: str,
    suffix: str,
) -> None:
    assembled = os.path.join(tmp_dir, f"assembled_{suffix}.mp4")
    subtitled = os.path.join(tmp_dir, f"subtitled_{suffix}.mp4")

    logger.info("render: assembling %s", suffix)
    await assemble_video(footage_path, audio_path, assembled)

    logger.info("render: burning subtitles %s", suffix)
    await burn_subtitles(assembled, srt_path, subtitled)

    if rainbow_border:
        logger.info("render: applying rainbow border %s", suffix)
        await apply_rainbow_border(subtitled, output_path)
    else:
        os.rename(subtitled, output_path)


async def run_render_step(
    job_id: int,
    footage_full_path: str,
    footage_short_path: str,
    voiceover_full_path: str,
    voiceover_short_path: str,
    srt_full_path: str,
    srt_short_path: str,
    output_dir: str,
) -> dict:
    rainbow_enabled = (get_setting("rainbow_border_enabled") or "true").lower() == "true"

    video_full_path = os.path.join(output_dir, "video_full.mp4")
    video_short_path = os.path.join(output_dir, "video_short.mp4")
    tmp_dir = output_dir

    await _render_track(
        footage_full_path, voiceover_full_path, srt_full_path,
        video_full_path, rainbow_enabled, tmp_dir, "full",
    )
    await _render_track(
        footage_short_path, voiceover_short_path, srt_short_path,
        video_short_path, rainbow_enabled, tmp_dir, "short",
    )

    return {
        "video_full_path": video_full_path,
        "video_short_path": video_short_path,
    }
