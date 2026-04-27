import os
from media.ffmpeg import get_duration, cut_footage, detect_peak_motion_timestamp
from utils.logger import get_logger

logger = get_logger(__name__)

# Target duration ranges per variant (seconds)
FULL_TARGET = 70.0   # midpoint of 65–75s
SHORT_TARGET = 54.0  # midpoint of 50–58s


async def run_cutting_step(
    job_id: int,
    footage_path: str,
    output_dir: str,
) -> dict:
    """Returns dict with footage_full_path and footage_short_path."""
    os.makedirs(output_dir, exist_ok=True)

    total_duration = await get_duration(footage_path)
    logger.info("Footage duration: %.2fs", total_duration)

    # Find the most visually active starting point for the cut
    peak_ts = await detect_peak_motion_timestamp(footage_path)
    logger.info("Peak motion at: %.2fs", peak_ts)

    full_path = os.path.join(output_dir, "footage_full.mp4")
    short_path = os.path.join(output_dir, "footage_short.mp4")

    # Cut from peak motion, clamped so we don't run past end of footage
    for target, out_path, label in [
        (FULL_TARGET, full_path, "full"),
        (SHORT_TARGET, short_path, "short"),
    ]:
        start = _clamp_start(peak_ts, target, total_duration)
        await cut_footage(footage_path, out_path, start, target)
        logger.info("footage_%s written: %s (start=%.2f, dur=%.2f)", label, out_path, start, target)

    return {
        "footage_full_path": full_path,
        "footage_short_path": short_path,
    }


def _clamp_start(peak_ts: float, target_duration: float, total_duration: float) -> float:
    """Ensure start + target_duration doesn't exceed total footage length."""
    max_start = max(0.0, total_duration - target_duration)
    return min(peak_ts, max_start)
