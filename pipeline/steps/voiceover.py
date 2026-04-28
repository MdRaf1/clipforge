import asyncio
import os
from db.queries.settings import get_setting
from media.ffmpeg import stretch_audio_to_duration, get_duration
from utils.logger import get_logger

logger = get_logger(__name__)

FULL_TARGET_DURATION = 70.0   # TikTok/Facebook — must exceed 60s for monetisation
SHORT_TARGET_DURATION = 54.0  # YouTube Shorts/Instagram Reels — 50-58s target


async def run_voiceover_step(
    job_id: int,
    script_full: str,
    script_short: str,
    output_dir: str,
    manual_override_voiceover: bool = False,
) -> dict:
    """Synthesise voiceover then stretch/compress each track to its target duration."""
    os.makedirs(output_dir, exist_ok=True)

    cloud_voice = get_setting("cloud_tts_voice") or "en-US-Neural2-D"
    local_voice = get_setting("local_tts_voice") or "en-US-GuyNeural"

    raw_full_path  = os.path.join(output_dir, "voiceover_full_raw.mp3")
    raw_short_path = os.path.join(output_dir, "voiceover_short_raw.mp3")
    full_path  = os.path.join(output_dir, "voiceover_full.mp3")
    short_path = os.path.join(output_dir, "voiceover_short.mp3")

    for script, raw_path, label in [
        (script_full,  raw_full_path,  "full"),
        (script_short, raw_short_path, "short"),
    ]:
        audio_bytes = await _synthesize(
            script,
            cloud_voice=cloud_voice,
            local_voice=local_voice,
            force_local=manual_override_voiceover,
        )
        with open(raw_path, "wb") as f:
            f.write(audio_bytes)
        raw_dur = await get_duration(raw_path)
        logger.info("voiceover_%s raw: %s (%.2fs, %d bytes)", label, raw_path, raw_dur, len(audio_bytes))

    # Stretch full track to FULL_TARGET_DURATION
    raw_full_dur = await get_duration(raw_full_path)
    logger.info("Stretching full voiceover %.2fs -> %.2fs", raw_full_dur, FULL_TARGET_DURATION)
    await stretch_audio_to_duration(raw_full_path, full_path, FULL_TARGET_DURATION)
    final_full_dur = await get_duration(full_path)
    logger.info("voiceover_full final: %.2fs", final_full_dur)

    # Stretch short track to SHORT_TARGET_DURATION
    raw_short_dur = await get_duration(raw_short_path)
    logger.info("Stretching short voiceover %.2fs -> %.2fs", raw_short_dur, SHORT_TARGET_DURATION)
    await stretch_audio_to_duration(raw_short_path, short_path, SHORT_TARGET_DURATION)
    final_short_dur = await get_duration(short_path)
    logger.info("voiceover_short final: %.2fs", final_short_dur)

    return {
        "voiceover_full_path": full_path,
        "voiceover_short_path": short_path,
    }


async def _synthesize(
    text: str,
    cloud_voice: str,
    local_voice: str,
    force_local: bool = False,
) -> bytes:
    if not force_local:
        try:
            from tts.cloud import synthesize as cloud_synth
            return await cloud_synth(text, cloud_voice)
        except Exception as e:
            logger.warning("Cloud TTS failed (%s), falling back to edge-tts", e)

    loop = asyncio.get_running_loop()
    from tts.local import synthesize as local_synth
    return await loop.run_in_executor(None, local_synth, text, local_voice)
