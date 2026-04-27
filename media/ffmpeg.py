import asyncio
import json

TARGET_W = 1080
TARGET_H = 1920
BORDER = 16
INNER_W = TARGET_W - BORDER * 2   # 1048
INNER_H = TARGET_H - BORDER * 2   # 1888
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
    """Trim footage and centre-crop to 9:16 portrait (1080x1920)."""
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
    """Mux footage video track with voiceover audio track."""
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
    """Burn MrBeast-style subtitles: large white caps, thick outline, lower-third, no box."""
    safe_path = srt_path.replace("\\", "/").replace(":", "\\:")
    subtitle_filter = (
        f"subtitles={safe_path}:force_style='"
        f"FontName=Arial,"
        f"Bold=1,"
        f"FontSize=36,"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"BackColour=&H00000000,"
        f"Outline=4,"
        f"Shadow=2,"
        f"Alignment=2,"
        f"MarginV=180,"
        f"BorderStyle=1,"
        f"Uppercase=1"
        f"'"
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


async def apply_rainbow_border(input_path: str, output_path: str, duration: float | None = None) -> None:
    """
    Shrink inner frame to INNER_W x INNER_H, pad back to TARGET_W x TARGET_H,
    then paint the 16px border with a rainbow hue that travels clockwise around
    the perimeter, completing exactly one full loop over the video duration.

    Perimeter mapping (clockwise from top-left):
      Top    (Y < 16):        p = X
      Right  (X >= 1064):     p = 1080 + Y
      Bottom (Y >= 1904):     p = 3000 + (1079 - X)
      Left   (X < 16):        p = 4080 + (1919 - Y)
    """
    if duration is None:
        duration = await get_duration(input_path)

    W, H, B = TARGET_W, TARGET_H, BORDER
    iw, ih = INNER_W, INNER_H
    right_x = W - B    # 1064
    bottom_y = H - B   # 1904
    perim = float(PERIMETER)  # 6000.0

    # p_expr: perimeter position of each border pixel (0..6000)
    p_expr = (
        f"if(lt(Y,{B}),X,"
        f"if(gte(X,{right_x}),{W}+Y,"
        f"if(gte(Y,{bottom_y}),{3*W - B}+({W}-1-X),"
        f"{4*W - 2*B + H - B}+({H}-1-Y))))"
    )
    # phase = p/perimeter - T/duration  → value in ~[-1,1] cycling range
    phase = f"({p_expr}/{perim}-T/{duration:.6f})"
    in_border = f"(lt(X,{B})+gte(X,{right_x})+lt(Y,{B})+gte(Y,{bottom_y}))"

    r_expr = f"if({in_border},128+127*sin(2*PI*{phase}),0)"
    g_expr = f"if({in_border},128+127*sin(2*PI*{phase}+2.094),0)"
    b_expr = f"if({in_border},128+127*sin(2*PI*{phase}+4.189),0)"

    filter_complex = (
        f"[0:v]scale={iw}:{ih}:flags=lanczos,pad={W}:{H}:{B}:{B}[inner];"
        f"color=black:s={W}x{H}:r=60,"
        f"geq=r='{r_expr}':g='{g_expr}':b='{b_expr}'[border];"
        f"[border][inner]overlay={B}:{B}[out]"
    )

    await _run(
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    )


async def extract_frame(input_path: str, timestamp: float, output_path: str) -> None:
    """Extract a single frame at 1080x1920 (portrait thumbnail)."""
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
