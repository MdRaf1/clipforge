import asyncio
import json


async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {stderr.decode()}")
    return stdout.decode()


async def get_duration(input_path: str) -> float:
    out = await _run(
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        input_path,
    )
    data = json.loads(out)
    return float(data["format"]["duration"])


async def cut_footage(input_path: str, output_path: str, start: float, duration: float) -> None:
    await _run(
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-c", "copy",
        output_path,
    )


async def assemble_video(video_path: str, audio_path: str, output_path: str) -> None:
    await _run(
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "48000",
        "-shortest",
        output_path,
    )


async def burn_subtitles(input_path: str, srt_path: str, output_path: str) -> None:
    subtitle_filter = (
        f"subtitles={srt_path}:force_style='FontName=Arial,Bold=1,"
        f"FontSize=18,PrimaryColour=&Hffffff,OutlineColour=&H000000,"
        f"Outline=2,Alignment=2,MarginV=80'"
    )
    await _run(
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", subtitle_filter,
        "-c:v", "libx264",
        "-c:a", "copy",
        output_path,
    )


async def apply_rainbow_border(input_path: str, output_path: str, thickness: int = 8) -> None:
    # pad adds border space; geq fills it with a hue-cycling spatial gradient
    pad_filter = f"pad=iw+{thickness*2}:ih+{thickness*2}:{thickness}:{thickness}"
    geq_filter = (
        f"geq=r='128+128*sin(2*PI*(X/{thickness}+T*0.5))':"
        f"g='128+128*sin(2*PI*(X/{thickness}+T*0.5)+2*PI/3)':"
        f"b='128+128*sin(2*PI*(X/{thickness}+T*0.5)+4*PI/3)'"
    )
    await _run(
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"{pad_filter},{geq_filter}",
        "-c:v", "libx264",
        "-c:a", "copy",
        output_path,
    )


async def extract_frame(input_path: str, timestamp: float, output_path: str) -> None:
    await _run(
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", input_path,
        "-frames:v", "1",
        output_path,
    )


async def detect_peak_motion_timestamp(input_path: str) -> float:
    # Use scene change detection to find the most visually active moment
    out = await _run(
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_frames",
        "-select_streams", "v",
        "-read_intervals", "%+60",
        "-show_entries", "frame=pkt_pts_time,pict_type",
        input_path,
    )
    data = json.loads(out)
    frames = data.get("frames", [])

    # Find the first I-frame (scene change) after the 20% mark
    duration = await get_duration(input_path)
    min_ts = duration * 0.2
    for frame in frames:
        ts = float(frame.get("pkt_pts_time", 0))
        if ts >= min_ts and frame.get("pict_type") == "I":
            return ts

    return duration * 0.2
