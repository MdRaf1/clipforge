import asyncio
import json
import os

TARGET_W = 1080
TARGET_H = 1920
TARGET_FPS = 30
BORDER = 16
PERIMETER = 2 * (TARGET_W + TARGET_H)  # 6000


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


async def stretch_audio_to_duration(input_path: str, output_path: str, target_duration: float) -> None:
    """
    Time-stretch audio to hit EXACTLY target_duration using FFmpeg atempo.
    atempo supports 0.5–2.0 per filter; we allow 0.85–1.30 for acceptable speech quality.
    Ratios outside that range fall back to the boundary (distorted but still in range).
    After stretch we apply `-t target_duration` to clamp to exact duration.
    """
    actual = await get_duration(input_path)
    if actual <= 0:
        raise ValueError("Audio has zero duration")
    ratio = actual / target_duration
    # Clamp to quality-safe range; 0.85 = slow-down 15%, 1.30 = speed-up 30%
    ratio = max(0.85, min(1.30, ratio))
    if abs(ratio - 1.0) < 0.002:
        # Close enough — just copy-encode without atempo
        await _run(
            "ffmpeg", "-y", "-i", input_path,
            "-t", f"{target_duration:.6f}",
            "-ar", "48000", "-b:a", "128k",
            output_path,
        )
        return
    await _run(
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter:a", f"atempo={ratio:.6f}",
        "-t", f"{target_duration:.6f}",
        "-ar", "48000", "-b:a", "128k",
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


def _render_progress_bar_frames(duration: float, out_dir: str, fps: int = TARGET_FPS) -> int:
    """
    Render a PNG sequence of the progress bar at each frame.

    Each PNG is a 1080×1920 transparent image with green border pixels filled
    from top-center clockwise, reaching 100% at the final frame. Uses PIL.

    FFmpeg drawbox expressions don't re-evaluate dynamic w/h per frame reliably,
    so we pre-generate frames and overlay them as an image sequence.
    Returns the total number of frames rendered.
    """
    from PIL import Image, ImageDraw
    import os as _os
    _os.makedirs(out_dir, exist_ok=True)

    W, H = TARGET_W, TARGET_H
    B = BORDER
    half_w = W // 2
    total_frames = max(1, int(round(duration * fps)))

    for i in range(total_frames):
        progress = (i + 1) / total_frames  # fill by end of interval
        filled = int(progress * PERIMETER)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        remaining = filled

        # A: top from x=540 to x=1080 (540px)
        if remaining > 0:
            px = min(remaining, half_w)
            draw.rectangle([(half_w, 0), (half_w + px - 1, B - 1)], fill=(0, 255, 0, 255))
            remaining -= px
        # B: right edge top-down (1920px)
        if remaining > 0:
            px = min(remaining, H)
            draw.rectangle([(W - B, 0), (W - 1, px - 1)], fill=(0, 255, 0, 255))
            remaining -= px
        # C: bottom right-to-left (1080px)
        if remaining > 0:
            px = min(remaining, W)
            draw.rectangle([(W - px, H - B), (W - 1, H - 1)], fill=(0, 255, 0, 255))
            remaining -= px
        # D: left edge bottom-to-top (1920px)
        if remaining > 0:
            px = min(remaining, H)
            draw.rectangle([(0, H - px), (B - 1, H - 1)], fill=(0, 255, 0, 255))
            remaining -= px
        # E: top-left half (540px)
        if remaining > 0:
            px = min(remaining, half_w)
            draw.rectangle([(0, 0), (px - 1, B - 1)], fill=(0, 255, 0, 255))

        img.save(_os.path.join(out_dir, f"f{i:05d}.png"))

    return total_frames


async def apply_progress_bar(input_path: str, output_path: str, duration: float | None = None) -> None:
    """
    Perimeter-traveling green progress bar. Starts at top-center, travels clockwise
    around the frame, and completes a full loop exactly when the video ends.

    Implementation: PIL pre-renders an RGBA frame sequence (transparent background
    + green border pixels filled up to the current perimeter progress), then FFmpeg
    overlays that sequence onto the video. This avoids FFmpeg `drawbox` limitations
    where dynamic `w`/`h` expressions only evaluate once at init.
    """
    import tempfile
    import shutil

    if duration is None:
        duration = await get_duration(input_path)

    tmp_dir = tempfile.mkdtemp(prefix="progbar_")
    try:
        loop = asyncio.get_event_loop()
        total_frames = await loop.run_in_executor(
            None, _render_progress_bar_frames, duration, tmp_dir, TARGET_FPS
        )
        pattern = os.path.join(tmp_dir, "f%05d.png")

        await _run(
            "ffmpeg", "-y",
            "-i", input_path,
            "-framerate", str(TARGET_FPS), "-i", pattern,
            "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1",
            "-map", "0:a?",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-t", str(duration),
            output_path,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# Backwards-compatible alias — pipeline code calls apply_rainbow_border
apply_rainbow_border = apply_progress_bar


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
