import asyncio
import os
from db.queries.settings import get_setting
from utils.logger import get_logger

logger = get_logger(__name__)


async def run_voiceover_step(
    job_id: int,
    script_full: str,
    script_short: str,
    output_dir: str,
    manual_override_voiceover: bool = False,
) -> dict:
    """Returns dict with voiceover_full_path and voiceover_short_path."""
    os.makedirs(output_dir, exist_ok=True)

    cloud_voice = get_setting("cloud_tts_voice") or "en-US-Neural2-D"
    local_voice = get_setting("local_tts_voice") or "af_heart"

    full_path = os.path.join(output_dir, "voiceover_full.mp3")
    short_path = os.path.join(output_dir, "voiceover_short.mp3")

    for script, out_path, label in [
        (script_full, full_path, "full"),
        (script_short, short_path, "short"),
    ]:
        audio_bytes = await _synthesize(
            script,
            cloud_voice=cloud_voice,
            local_voice=local_voice,
            force_local=manual_override_voiceover,
        )
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        logger.info("voiceover_%s written: %s (%d bytes)", label, out_path, len(audio_bytes))

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
            logger.warning("Cloud TTS failed (%s), falling back to Kokoro", e)

    # Kokoro is CPU-bound — run in process executor to avoid blocking asyncio loop
    loop = asyncio.get_running_loop()
    from tts.local import synthesize as local_synth
    return await loop.run_in_executor(None, local_synth, text, local_voice)
