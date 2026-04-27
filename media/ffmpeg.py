import asyncio
import json
import math
import os

TARGET_W = 1080
TARGET_H = 1920
TARGET_FPS = 30
BORDER = 16
INNER_W = TARGET_W - BORDER * 2   # 1048
INNER_H = TARGET_H - BORDER * 2   # 1888
PERIMETER = 2 * (TARGET_W + TARGET_H)  # 6000

# Pre-generated rainbow strip path — built once, reused for all jobs
_RAINBOW_STRIP = os.path.join(os.path.dirname(__file__), "_rainbow_strip.png")


def _ensure_rainbow_strip() -> str:
    """Generate a 6000x16 full-saturation rainbow PNG if it doesn't exist yet."""
    if os.path.exists(_RAINBOW_STRIP):
        return _RAINBOW_STRIP
    from PIL import Image
    img = Image.new("RGB", (PERIMETER, BORDER))
    for x in range(PERIMETER):
        h = x / PERIMETER
        i = int(h * 6)
        f = h * 6 - i
        q, t_v = 1 - f, f
        r, g, b = [(1, t_v, 0), (q, 1, 0), (0, 1, t_v), (0, q, 1), (t_v, 0, 1), (1, 0, q)][i % 6]
        rgb = (int(r * 255), int(g * 255), int(b * 255))
        for y in range(BORDER):
            img.putpixel((x, y), rgb)
    img.save(_RAINBOW_STRIP)
    return _RAINBOW_STRIP


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
    """Trim and centre-crop to 1080x1920 portrait at 30fps."""
    vf = (
        f"crop=ih*{TARGET_W}/{TARGET_H}:ih,"
        f"scale={TARGET_W}:{TARGET_H}:flags=lanczos,"
        f"fps={TARGET_FPS},"
        f"setsar=1"
    )
    await _run(
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        output_path,
    )


async def assemble_video(video_path: str, audio_path: str, output_path: str) -> None:
    """Mux footage video + voiceover audio."""
    await _run(
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        "-shortest",
        output_path,
    )


async def burn_subtitles(input_path: str, srt_path: str, output_path: str) -> None:
    """MrBeast-style subtitles: large white caps, thick outline, no box."""
    safe_path = srt_path.replace("\\", "/").replace(":", "\\:")
    subtitle_filter = (
        f"subtitles={safe_path}:force_style='"
        f"FontName=Arial,Bold=1,FontSize=36,"
        f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        f"BackColour=&H00000000,Outline=4,Shadow=2,"
        f"Alignment=2,MarginV=180,BorderStyle=1,Uppercase=1'"
    )
    await _run(
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", subtitle_filter,
        "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    )


async def apply_rainbow_border(input_path: str, output_path: str, duration: float | None = None) -> None:
    """
    Fast rainbow border using a pre-rendered strip + crop/scroll.
    Shrinks inner frame to 1048x1888, pads to 1080x1920, then overlays
    4 border strips cropped from a scrolling 6000px rainbow PNG.
    Each frame the crop offset advances so the rainbow completes one
    full loop over the video duration. Runs ~2.5x realtime on CPU.

    Perimeter offsets per side (clockwise from top-left):
      top=0, right=1080, bottom=3000, left=4080
    """
    if duration is None:
        duration = await get_duration(input_path)

    strip = _ensure_rainbow_strip()
    fps = TARGET_FPS
    total_frames = duration * fps
    # pixels per frame so one full loop = PERIMETER pixels over total_frames
    step = f"{PERIMETER}.0/{total_frames:.6f}"
    W, H, B = TARGET_W, TARGET_H, BORDER
    iw, ih = INNER_W, INNER_H
    P = PERIMETER

    # crop x for each side: base_offset + frame_advance, wrapped to strip width
    def cx(offset: int) -> str:
        return f"mod(trunc(n*({step}))+{offset},{P - W})"

    top_cx  = cx(0)
    bot_cx  = cx(P // 2)          # opposite side starts halfway around
    lft_cx  = cx(W)               # right side of top corner
    rgt_cx  = cx(W + H - B + W)   # bottom corner

    filter_complex = (
        f"[1:v]scale={iw}:{ih}:flags=lanczos,pad={W}:{H}:{B}:{B}:black[base];"
        f"[0:v]crop={W}:{B}:x='{top_cx}':y=0[top];"
        f"[0:v]crop={W}:{B}:x='{bot_cx}':y=0[bot];"
        f"[0:v]crop={B}:1:x='{lft_cx}':y=0,scale={B}:{ih}[lft];"
        f"[0:v]crop={B}:1:x='{rgt_cx}':y=0,scale={B}:{ih}[rgt];"
        f"[base][top]overlay=0:0[v1];"
        f"[v1][bot]overlay=0:{H - B}[v2];"
        f"[v2][lft]overlay=0:{B}[v3];"
        f"[v3][rgt]overlay={W - B}:{B}[out]"
    )

    await _run(
        "ffmpeg", "-y",
        "-r", str(fps), "-loop", "1", "-i", strip,
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "1:a?",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-t", str(duration),
        output_path,
    )


async def extract_frame(input_path: str, timestamp: float, output_path: str) -> None:
    """Extract a single frame at 1080x1920 portrait."""
    await _run(
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", input_path,
        "-frames:v", "1",
        "-vf", f"scale={TARGET_W}:{TARGET_H}:flags=lanczos",
        "-update", "1",
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
