import asyncio
import json

# Target: 1080x1920 vertical (9:16) for all short-form platforms
TARGET_W = 1080
TARGET_H = 1920


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
    # Re-encode while cutting so the output is already 9:16 portrait.
    # crop=1080:1920 takes a centre-crop of the landscape frame, then scales to
    # exact target in case the source isn't exactly 16:9.
    vf = (
        f"crop=ih*{TARGET_W}/{TARGET_H}:ih,"
        f"scale={TARGET_W}:{TARGET_H}:flags=lanczos,"
        f"setsar=1"
    )
    await _run(
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        output_path,
    )


async def assemble_video(video_path: str, audio_path: str, output_path: str) -> None:
    # Footage is already 9:16 from cut_footage; just mux audio.
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
    # FontSize 24 looks good on 1920-tall portrait frames.
    # Escape colons/backslashes in the path for the subtitles filter.
    safe_path = srt_path.replace("\\", "/").replace(":", "\\:")
    subtitle_filter = (
        f"subtitles={safe_path}:force_style='FontName=Arial,Bold=1,"
        f"FontSize=24,PrimaryColour=&H00ffffff,OutlineColour=&H00000000,"
        f"Outline=2,Shadow=1,Alignment=2,MarginV=120'"
    )
    await _run(
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", subtitle_filter,
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    )


async def apply_rainbow_border(input_path: str, output_path: str, thickness: int = 16) -> None:
    # pad adds border space around the 1080x1920 frame.
    # geq fills only the border pixels with a hue-cycling RGB gradient.
    # The geq expressions use lum() to detect border pixels and replace them.
    tw = TARGET_W + thickness * 2
    th = TARGET_H + thickness * 2
    pad_filter = f"pad={tw}:{th}:{thickness}:{thickness}:black"
    # Per-pixel: if in border zone, paint rainbow; else pass through original
    geq_filter = (
        f"geq="
        f"r='if(gt(X,{thickness})*lt(X,{tw-thickness})*gt(Y,{thickness})*lt(Y,{th-thickness}),r(X-{thickness},Y-{thickness}),128+128*sin(2*PI*(X*0.02+Y*0.005+T*0.7)))':"
        f"g='if(gt(X,{thickness})*lt(X,{tw-thickness})*gt(Y,{thickness})*lt(Y,{th-thickness}),g(X-{thickness},Y-{thickness}),128+128*sin(2*PI*(X*0.02+Y*0.005+T*0.7)+2*PI/3))':"
        f"b='if(gt(X,{thickness})*lt(X,{tw-thickness})*gt(Y,{thickness})*lt(Y,{th-thickness}),b(X-{thickness},Y-{thickness}),128+128*sin(2*PI*(X*0.02+Y*0.005+T*0.7)+4*PI/3))'"
    )
    await _run(
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"{pad_filter},{geq_filter}",
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    )


async def extract_frame(input_path: str, timestamp: float, output_path: str) -> None:
    # Extract at 1280x720 — standard thumbnail dimensions
    await _run(
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", input_path,
        "-frames:v", "1",
        "-vf", "scale=1280:720:flags=lanczos",
        output_path,
    )


async def detect_peak_motion_timestamp(input_path: str) -> float:
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

    duration = await get_duration(input_path)
    min_ts = duration * 0.2
    for frame in frames:
        ts = float(frame.get("pkt_pts_time", 0))
        if ts >= min_ts and frame.get("pict_type") == "I":
            return ts

    return duration * 0.2
