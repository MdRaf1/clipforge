import asyncio
import os

import whisper

from db.queries.settings import get_setting
from utils.logger import get_logger

logger = get_logger(__name__)

_whisper_model: dict[str, whisper.Whisper] = {}


def _load_model(model_size: str) -> whisper.Whisper:
    if model_size not in _whisper_model:
        logger.info("Loading Whisper model: %s", model_size)
        _whisper_model[model_size] = whisper.load_model(model_size)
    return _whisper_model[model_size]


def _transcribe_to_srt(audio_path: str, model_size: str) -> str:
    """Run Whisper synchronously; returns SRT string."""
    model = _load_model(model_size)
    result = model.transcribe(audio_path, word_timestamps=True)

    lines = []
    idx = 1
    for segment in result["segments"]:
        words = segment.get("words", [])
        if not words:
            # Fall back to segment-level timestamps
            start = segment["start"]
            end = segment["end"]
            text = segment["text"].strip()
            lines.append(f"{idx}")
            lines.append(f"{_fmt(start)} --> {_fmt(end)}")
            lines.append(text)
            lines.append("")
            idx += 1
            continue
        for word in words:
            start = word["start"]
            end = word["end"]
            text = word["word"].strip()
            if not text:
                continue
            lines.append(f"{idx}")
            lines.append(f"{_fmt(start)} --> {_fmt(end)}")
            lines.append(text)
            lines.append("")
            idx += 1

    return "\n".join(lines)


def _fmt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


async def run_subtitles_step(job_id: int, voiceover_full_path: str, voiceover_short_path: str, output_dir: str) -> dict:
    model_size = get_setting("whisper_model") or "small"

    srt_full_path = os.path.join(output_dir, "subtitles_full.srt")
    srt_short_path = os.path.join(output_dir, "subtitles_short.srt")

    loop = asyncio.get_event_loop()

    logger.info("Whisper transcribing full voiceover (model=%s)", model_size)
    srt_full = await loop.run_in_executor(None, _transcribe_to_srt, voiceover_full_path, model_size)
    with open(srt_full_path, "w", encoding="utf-8") as f:
        f.write(srt_full)

    logger.info("Whisper transcribing short voiceover (model=%s)", model_size)
    srt_short = await loop.run_in_executor(None, _transcribe_to_srt, voiceover_short_path, model_size)
    with open(srt_short_path, "w", encoding="utf-8") as f:
        f.write(srt_short)

    return {
        "srt_full_path": srt_full_path,
        "srt_short_path": srt_short_path,
    }
