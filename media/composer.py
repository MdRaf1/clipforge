import argparse
import json
import math
import numpy as np
import pysrt
import re
import shutil
from pathlib import Path
from typing import Any, cast

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoClip,
    VideoFileClip,
    concatenate_videoclips,
)


DEFAULT_BG_PATH = Path("assets/sliced_bg.mp4")
DEFAULT_AUDIO_PATH = Path("assets/voiceover.mp3")
DEFAULT_SCRIPT_PATH = Path("assets/script.json")
DEFAULT_OUTPUT_PATH = Path("assets/final_output.mp4")
DEFAULT_SFX_DIR = Path("assets/sfx")
DEFAULT_TARGET_DURATION = 58.0
DEFAULT_SUBTITLE_DELAY = 0.0
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 60
PROGRESS_BAR_HEIGHT = 22
PROGRESS_BAR_COLOR = (0, 255, 0)
DEFAULT_CHANNEL_HANDLE = "@MdRaf1"
WATERMARK_FONT_SIZE = 32
WATERMARK_OPACITY = 0.40
CTA_DURATION_SECONDS = 2.0
MARKER_MIN_DURATION = 0.9
SFX_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def check_imagemagick() -> None:
    if not shutil.which("magick") and not shutil.which("convert"):
        raise RuntimeError(
            "ImageMagick is required for robust TextClip rendering. Install it and ensure it is in PATH."
        )


def load_script(script_path: Path) -> dict[str, Any]:
    with script_path.open("r", encoding="utf-8") as file_handle:
        payload = json.load(file_handle)

    if not isinstance(payload, dict):
        raise ValueError("Script JSON must be an object")

    return payload


def parse_marker_time(marker: dict[str, Any], fallback: float) -> float:
    raw_value = marker.get("t", fallback)
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return fallback


def normalize_markers(payload: dict[str, Any], video_duration: float) -> list[dict[str, Any]]:
    raw_markers = payload.get("markers", [])
    if not isinstance(raw_markers, list):
        return []

    normalized: list[dict[str, Any]] = []
    for idx, raw_marker in enumerate(raw_markers):
        if not isinstance(raw_marker, dict):
            continue

        text = str(raw_marker.get("on_screen_text", "")).strip()
        if not text:
            continue

        cue = str(raw_marker.get("visual_cue", "")).strip()
        time_value = parse_marker_time(raw_marker, fallback=float(idx))
        start = max(0.0, min(round(time_value, 3), video_duration))
        normalized.append({"start": start, "text": text, "cue": cue})

    normalized.sort(key=lambda marker: marker["start"])
    return normalized


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", value.lower())


def build_keyword_token_set(payload: dict[str, Any]) -> set[str]:
    raw_keywords = payload.get("keywords", [])
    if not isinstance(raw_keywords, list):
        return set()

    tokens: set[str] = set()
    for keyword in raw_keywords:
        keyword_text = str(keyword).strip().lower()
        if not keyword_text:
            continue
        for part in re.split(r"\s+", keyword_text):
            token = normalize_token(part)
            if token:
                tokens.add(token)
    return tokens


def resolve_word_timing_path(audio_path: Path, word_timing_path: Path | None = None) -> Path:
    if word_timing_path is not None:
        return word_timing_path
    return audio_path.with_suffix(".words.json")


def resolve_subtitle_path(audio_path: Path, subtitle_path: Path | None = None) -> Path:
    if subtitle_path is not None:
        return subtitle_path
    return audio_path.with_suffix(".srt")


def load_word_timings(word_timing_path: Path, video_duration: float) -> list[dict[str, Any]]:
    with word_timing_path.open("r", encoding="utf-8") as file_handle:
        payload = json.load(file_handle)

    raw_words: Any
    if isinstance(payload, dict):
        raw_words = payload.get("words", [])
    else:
        raw_words = payload

    if not isinstance(raw_words, list):
        return []

    normalized: list[dict[str, Any]] = []
    for raw_word in raw_words:
        if not isinstance(raw_word, dict):
            continue
        word = str(raw_word.get("word", "")).strip()
        if not word:
            continue

        try:
            start = float(raw_word.get("start", 0.0))
            end = float(raw_word.get("end", start + 0.12))
        except (TypeError, ValueError):
            continue

        start = max(0.0, min(round(start, 3), video_duration))
        end = max(start + 0.04, min(round(end, 3), video_duration))
        if end <= start:
            continue

        normalized.append(
            {
                "word": word,
                "start": start,
                "end": end,
            }
        )

    normalized.sort(key=lambda item: item["start"])
    return normalized


def _subrip_time_to_seconds(value: pysrt.SubRipTime) -> float:
    return (
        float(value.hours * 3600)
        + float(value.minutes * 60)
        + float(value.seconds)
        + float(value.milliseconds) / 1000.0
    )


def load_srt_entries(
    subtitle_path: Path,
    video_duration: float,
    audio_delay: float = DEFAULT_SUBTITLE_DELAY,
) -> list[dict[str, Any]]:
    if not subtitle_path.exists():
        return []

    subs = pysrt.open(str(subtitle_path), encoding="utf-8")
    entries: list[dict[str, Any]] = []
    for item in subs:
        text = str(item.text or "").replace("\n", " ").strip()
        if not text:
            continue

        start = round(_subrip_time_to_seconds(item.start) + audio_delay, 3)
        end = round(_subrip_time_to_seconds(item.end) + audio_delay, 3)
        if end <= start:
            end = round(start + 0.08, 3)

        start = max(0.0, min(start, video_duration))
        end = max(start + 0.04, min(end, video_duration))
        if end <= start:
            continue

        entries.append({"text": text, "start": start, "end": end})

    entries.sort(key=lambda entry: entry["start"])
    return entries


def choose_word_color(word: str, keyword_tokens: set[str]) -> str:
    _ = word, keyword_tokens
    return "#FFFFFF"


def create_word_text_clip(
    word: str,
    font_size: int,
    color: str,
    frame_width: int,
    frame_height: int,
    start: float,
    duration: float,
) -> TextClip:
    txt = TextClip(
        text=word,
        font_size=font_size,
        color=color,
        stroke_color="black",
        stroke_width=8,
        method="label",
        size=(int(frame_width * 0.92), int(frame_height * 0.28)),
        text_align="center",
        horizontal_align="center",
        vertical_align="center",
    )
    return txt.with_start(start).with_duration(duration).with_position(("center", int(frame_height * 0.69)))


def create_subtitle_text_clip(
    text: str,
    font_size: int,
    frame_width: int,
    frame_height: int,
    start: float,
    duration: float,
) -> TextClip:
    txt = TextClip(
        text=text,
        font_size=font_size,
        color="#FFE500",
        stroke_color="black",
        stroke_width=4,
        method="caption",
        size=(int(frame_width * 0.9), int(frame_height * 0.30)),
        text_align="center",
        horizontal_align="center",
        vertical_align="center",
    )
    return txt.with_start(start).with_duration(duration).with_position(("center", int(frame_height * 0.69)))


def build_word_overlay_clips(
    words: list[dict[str, Any]],
    video_duration: float,
    frame_width: int,
    frame_height: int,
    keyword_tokens: set[str],
) -> list[TextClip]:
    overlays: list[TextClip] = []
    base_font_size = max(74, int(frame_height * 0.056))
    pop_font_size = int(base_font_size * 1.15)

    for word_entry in words:
        start = float(word_entry["start"])
        if start >= video_duration:
            continue

        end = min(video_duration, float(word_entry["end"]))
        duration = round(max(0.0, end - start), 3)
        if duration <= 0:
            continue

        color = choose_word_color(str(word_entry["word"]), keyword_tokens)
        pop_duration = min(0.12, duration)
        pop_clip = create_word_text_clip(
            word=str(word_entry["word"]),
            font_size=pop_font_size,
            color=color,
            frame_width=frame_width,
            frame_height=frame_height,
            start=start,
            duration=pop_duration,
        )
        overlays.append(pop_clip)

        remaining_duration = round(duration - pop_duration, 3)
        if remaining_duration > 0:
            steady_clip = create_word_text_clip(
                word=str(word_entry["word"]),
                font_size=base_font_size,
                color=color,
                frame_width=frame_width,
                frame_height=frame_height,
                start=round(start + pop_duration, 3),
                duration=remaining_duration,
            )
            overlays.append(steady_clip)

    return overlays


def build_srt_overlay_clips(
    entries: list[dict[str, Any]],
    video_duration: float,
    frame_width: int,
    frame_height: int,
) -> list[TextClip]:
    overlays: list[TextClip] = []
    base_font_size = max(74, int(frame_height * 0.056))

    for entry in entries:
        start = float(entry["start"])
        end = min(video_duration, float(entry["end"]))
        duration = round(max(0.0, end - start), 3)
        if duration <= 0:
            continue

        overlays.append(
            create_subtitle_text_clip(
                text=str(entry["text"]),
                font_size=base_font_size,
                frame_width=frame_width,
                frame_height=frame_height,
                start=start,
                duration=duration,
            )
        )

    return overlays


def build_marker_overlay_clips(
    markers: list[dict[str, Any]],
    video_duration: float,
    frame_width: int,
    frame_height: int,
) -> list[TextClip]:
    overlays: list[TextClip] = []
    if not markers:
        return overlays

    for index, marker in enumerate(markers):
        start = float(marker["start"])
        if start >= video_duration:
            continue

        if index + 1 < len(markers):
            next_start = float(markers[index + 1]["start"])
            duration = max(MARKER_MIN_DURATION, next_start - start)
        else:
            duration = MARKER_MIN_DURATION

        duration = min(duration, max(0.0, video_duration - start))
        if duration <= 0:
            continue

        text = str(marker.get("text", "")).strip()
        if not text:
            continue

        clip = (
            TextClip(
                text=text,
                font_size=max(52, int(frame_height * 0.040)),
                color="yellow",
                stroke_color="black",
                stroke_width=4,
                method="caption",
                size=(int(frame_width * 0.86), int(frame_height * 0.22)),
                text_align="center",
                horizontal_align="center",
                vertical_align="center",
                duration=duration,
            )
            .with_start(start)
            .with_position(("center", int(frame_height * 0.72)))
        )
        overlays.append(clip)

    return overlays


def list_sfx_files(sfx_dir: Path) -> list[Path]:
    if not sfx_dir.exists():
        return []
    return sorted(path for path in sfx_dir.iterdir() if path.is_file() and path.suffix.lower() in SFX_EXTENSIONS)


def choose_sfx_file(marker: dict[str, Any], sfx_files: list[Path]) -> Path | None:
    if not sfx_files:
        return None

    cue_text = f"{marker.get('text', '')} {marker.get('cue', '')}".lower()
    cue_tokens = {normalize_token(token) for token in cue_text.split()}
    cue_tokens.discard("")

    for sfx_file in sfx_files:
        stem_token = normalize_token(sfx_file.stem)
        if stem_token and stem_token in cue_tokens:
            return sfx_file

    return sfx_files[0]


def build_sfx_audio_clips(
    markers: list[dict[str, Any]],
    video_duration: float,
    sfx_files: list[Path],
    timeline_offset: float = 0.0,
) -> list[AudioFileClip]:
    clips: list[AudioFileClip] = []
    for marker in markers:
        start = max(0.0, min(float(marker["start"]) + timeline_offset, video_duration))
        selected_sfx = choose_sfx_file(marker, sfx_files)
        if selected_sfx is None:
            continue

        sfx_clip = AudioFileClip(str(selected_sfx))
        max_duration = min(1.0, video_duration - start)
        if max_duration <= 0:
            sfx_clip.close()
            continue
        if float(sfx_clip.duration or 0.0) > max_duration:
            sfx_clip = sfx_clip.subclipped(0, max_duration)
        clips.append(sfx_clip.with_start(start))

    return clips


def build_progress_bar_clip(video_duration: float, frame_width: int) -> VideoClip:
    """
    Perimeter-traveling progress bar that starts at top-center, travels clockwise
    around the frame border, and returns to top-center when the video ends.

    Perimeter segments (clockwise from top-center):
      A: top-center → top-right   (W/2 px)
      B: top-right  → bot-right   (H px)
      C: bot-right  → bot-left    (W px)
      D: bot-left   → top-left    (H px)
      E: top-left   → top-center  (W/2 px)
      Total perimeter = 2W + 2H
    """
    W = frame_width
    H = TARGET_HEIGHT
    B = PROGRESS_BAR_HEIGHT  # border thickness
    color = np.array(PROGRESS_BAR_COLOR, dtype=np.uint8)
    total_perim = 2 * W + 2 * H

    def make_frame(t: float) -> np.ndarray:
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        progress = max(0.0, min(float(t), video_duration)) / max(video_duration, 1e-9)
        filled = int(progress * total_perim)

        remaining = filled

        # A: top edge, left half → right  (top-center to top-right)
        seg_a = W // 2
        if remaining > 0:
            px = min(remaining, seg_a)
            # starts at x = W//2, goes right to W
            frame[0:B, W // 2 : W // 2 + px] = color
            remaining -= px

        # B: right edge, top → bottom
        seg_b = H
        if remaining > 0:
            px = min(remaining, seg_b)
            frame[0:px, W - B : W] = color
            remaining -= px

        # C: bottom edge, right → left
        seg_c = W
        if remaining > 0:
            px = min(remaining, seg_c)
            frame[H - B : H, W - px : W] = color
            remaining -= px

        # D: left edge, bottom → top
        seg_d = H
        if remaining > 0:
            px = min(remaining, seg_d)
            frame[H - px : H, 0:B] = color
            remaining -= px

        # E: top edge, left → top-center
        if remaining > 0:
            px = min(remaining, W // 2)
            frame[0:B, 0:px] = color

        return frame

    return VideoClip(make_frame, duration=video_duration).with_position((0, 0))


def build_watermark_clip(channel_handle: str, video_duration: float) -> TextClip:
    watermark = TextClip(
        text=channel_handle,
        font_size=WATERMARK_FONT_SIZE,
        color="white",
        method="label",
        margin=(20, 12),
        stroke_color="black",
        stroke_width=2,
        duration=video_duration,
    )
    return (
        watermark.with_position(lambda _t: (TARGET_WIDTH - int(getattr(watermark, "w", 220)) - 20, 80))
        .with_opacity(WATERMARK_OPACITY)
    )


def build_cta_clip(payload: dict[str, Any], video_duration: float, frame_width: int, frame_height: int) -> TextClip | None:
    raw_part = payload.get("part")
    raw_series_id = payload.get("series_id")

    if raw_part is None:
        return None

    try:
        part = int(raw_part)
    except (TypeError, ValueError):
        return None

    series_id = str(raw_series_id).strip()
    if not series_id or part <= 0 or video_duration <= 0:
        return None

    next_part = part + 1
    text = f"Like & Follow for Part {next_part}"
    cta_duration = min(CTA_DURATION_SECONDS, video_duration)
    cta_start = round(video_duration - cta_duration, 3)

    return (
        TextClip(
            text=text,
            font_size=max(56, int(frame_height * 0.05)),
            color="#FFF15C",
            stroke_color="black",
            stroke_width=6,
            method="caption",
            size=(int(frame_width * 0.92), int(frame_height * 0.32)),
            text_align="center",
            horizontal_align="center",
            vertical_align="center",
            duration=cta_duration,
        )
        .with_position(("center", "center"))
        .with_start(cta_start)
    )


def fit_to_vertical(clip: VideoClip) -> VideoClip:
    fitted = clip.resized(height=TARGET_HEIGHT)
    fitted_w = int(getattr(fitted, "w", TARGET_WIDTH))
    fitted_h = int(getattr(fitted, "h", TARGET_HEIGHT))

    if fitted_w < TARGET_WIDTH:
        fitted = clip.resized(width=TARGET_WIDTH)
        fitted_w = int(getattr(fitted, "w", TARGET_WIDTH))
        fitted_h = int(getattr(fitted, "h", TARGET_HEIGHT))

    if fitted_w != TARGET_WIDTH or fitted_h != TARGET_HEIGHT:
        fitted = cast(Any, fitted).cropped(
            x_center=int(fitted_w / 2),
            y_center=int(fitted_h / 2),
            width=TARGET_WIDTH,
            height=TARGET_HEIGHT,
        )
    return cast(VideoClip, fitted)


def extend_video_if_needed(clip: VideoFileClip, required_duration: float) -> VideoFileClip:
    base_duration = float(clip.duration or 0.0)
    if base_duration <= 0:
        raise ValueError("Background video has an invalid duration")

    if base_duration >= required_duration:
        return clip

    repeats = max(2, math.ceil(required_duration / base_duration))
    stitched = concatenate_videoclips([clip] + [clip.subclipped(0, base_duration) for _ in range(repeats - 1)])
    return stitched.subclipped(0, required_duration)


def compose_video(
    bg_path: Path,
    audio_path: Path,
    script_path: Path,
    output_path: Path,
    word_timing_path: Path | None = None,
    subtitle_path: Path | None = None,
    sfx_dir: Path = DEFAULT_SFX_DIR,
    channel_handle: str = DEFAULT_CHANNEL_HANDLE,
    subtitle_mode: str = "auto",
    audio_delay: float = DEFAULT_SUBTITLE_DELAY,
    target_duration: float = DEFAULT_TARGET_DURATION,
    dry_run: bool = False,
) -> Path:
    require_file(bg_path, "Background video")
    require_file(audio_path, "Voiceover audio")
    require_file(script_path, "Script JSON")
    check_imagemagick()

    payload = load_script(script_path)
    resolved_word_timing_path = resolve_word_timing_path(audio_path, word_timing_path)
    resolved_subtitle_path = resolve_subtitle_path(audio_path, subtitle_path)

    audio_clip = AudioFileClip(str(audio_path))
    raw_audio_duration = float(audio_clip.duration or 0.0)
    if raw_audio_duration <= 0:
        audio_clip.close()
        raise ValueError("Voiceover duration is invalid")

    target_duration = round(float(target_duration), 3)
    if target_duration <= 0:
        audio_clip.close()
        raise ValueError("Target duration must be positive")

    if audio_delay >= 0:
        timeline_duration = target_duration
        audio_timeline_clip: AudioFileClip | Any = audio_clip.with_start(audio_delay)
    else:
        trim_start = min(abs(audio_delay), max(0.0, raw_audio_duration - 0.08))
        audio_timeline_clip = audio_clip.subclipped(trim_start, raw_audio_duration)
        timeline_duration = target_duration
        if float(audio_timeline_clip.duration or 0.0) <= 0:
            audio_clip.close()
            raise ValueError("Audio delay trimmed all voiceover audio")

    base_video = VideoFileClip(str(bg_path))
    stitched_video = base_video
    vertical_video: VideoClip | None = None
    final_audio: CompositeAudioClip | None = None
    final_clip: CompositeVideoClip | None = None
    progress_bar: VideoClip | None = None
    watermark_clip: TextClip | None = None
    cta_clip: TextClip | None = None
    overlays: list[TextClip] = []
    marker_overlays: list[TextClip] = []
    sfx_audio_clips: list[AudioFileClip] = []

    try:
        stitched_video = extend_video_if_needed(base_video, timeline_duration)
        stitched_video = stitched_video.subclipped(0, timeline_duration)
        vertical_video = fit_to_vertical(stitched_video)
        if vertical_video is None:
            raise RuntimeError("Failed to produce vertical video clip")

        video_duration = float(vertical_video.duration or timeline_duration)
        keyword_tokens = build_keyword_token_set(payload)
        markers = normalize_markers(payload, video_duration)

        srt_entries = (
            load_srt_entries(resolved_subtitle_path, video_duration, audio_delay=audio_delay)
            if subtitle_mode in {"auto", "srt"}
            else []
        )
        words = (
            load_word_timings(resolved_word_timing_path, video_duration)
            if resolved_word_timing_path.exists() and subtitle_mode in {"auto", "words"}
            else []
        )

        if srt_entries:
            overlays = build_srt_overlay_clips(
                entries=srt_entries,
                video_duration=video_duration,
                frame_width=TARGET_WIDTH,
                frame_height=TARGET_HEIGHT,
            )
        else:
            overlays = build_word_overlay_clips(words, video_duration, TARGET_WIDTH, TARGET_HEIGHT, keyword_tokens)

        if not overlays:
            marker_overlays = build_marker_overlay_clips(
                markers=markers,
                video_duration=video_duration,
                frame_width=TARGET_WIDTH,
                frame_height=TARGET_HEIGHT,
            )

        sfx_files = list_sfx_files(sfx_dir)
        sfx_audio_clips = build_sfx_audio_clips(
            markers,
            video_duration,
            sfx_files,
            timeline_offset=audio_delay,
        )
        final_audio = (
            CompositeAudioClip([audio_timeline_clip, *sfx_audio_clips])
            if sfx_audio_clips
            else CompositeAudioClip([audio_timeline_clip])
        ).with_duration(timeline_duration)
        vertical_video = vertical_video.with_audio(final_audio)
        progress_bar = build_progress_bar_clip(video_duration=timeline_duration, frame_width=TARGET_WIDTH)
        watermark_clip = build_watermark_clip(channel_handle=channel_handle, video_duration=timeline_duration)
        cta_clip = build_cta_clip(
            payload=payload,
            video_duration=timeline_duration,
            frame_width=TARGET_WIDTH,
            frame_height=TARGET_HEIGHT,
        )

        composite_layers: list[Any] = [vertical_video, progress_bar, *marker_overlays, *overlays, watermark_clip]
        if cta_clip is not None:
            composite_layers.append(cta_clip)

        final_clip = CompositeVideoClip(
            composite_layers,
            size=(TARGET_WIDTH, TARGET_HEIGHT),
        ).with_duration(timeline_duration)
        if not dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if final_clip is None:
                raise RuntimeError("Final video clip was not created")
            final_video = final_clip.subclipped(0, timeline_duration).with_duration(timeline_duration)
            final_video.write_videofile(
                str(output_path),
                fps=TARGET_FPS,
                codec="libx264",
                audio_codec="aac",
                preset="veryfast",
                threads=4,
                logger=None,
            )
    finally:
        for overlay in overlays:
            overlay.close()
        for marker_overlay in marker_overlays:
            marker_overlay.close()
        for sfx_clip in sfx_audio_clips:
            sfx_clip.close()
        if final_clip is not None:
            final_clip.close()
        if progress_bar is not None:
            progress_bar.close()
        if watermark_clip is not None:
            watermark_clip.close()
        if cta_clip is not None:
            cta_clip.close()
        if final_audio is not None:
            final_audio.close()
        if vertical_video is not None:
            vertical_video.close()
        if stitched_video is not base_video:
            stitched_video.close()
        base_video.close()
        audio_clip.close()

    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compose final short-form video with voiceover and marker overlays")
    parser.add_argument("--background", type=Path, default=DEFAULT_BG_PATH, help="Path to sliced background MP4")
    parser.add_argument("--voiceover", type=Path, default=DEFAULT_AUDIO_PATH, help="Path to voiceover MP3")
    parser.add_argument("--script", type=Path, default=DEFAULT_SCRIPT_PATH, help="Path to script JSON")
    parser.add_argument(
        "--word-timings",
        type=Path,
        help="Optional word timing JSON path from Phase 2 (defaults to voiceover sidecar)",
    )
    parser.add_argument(
        "--subtitles",
        type=Path,
        help="Optional SRT subtitle path (defaults to voiceover sidecar)",
    )
    parser.add_argument(
        "--subtitle-mode",
        choices=["auto", "srt", "words"],
        default="auto",
        help="Choose subtitle source: auto prefers SRT, then word timings, then marker fallback",
    )
    parser.add_argument(
        "--audio-delay",
        type=float,
        default=DEFAULT_SUBTITLE_DELAY,
        help="Constant audio/subtitle delay in seconds; positive delays audio later",
    )
    parser.add_argument(
        "--sfx-dir",
        type=Path,
        default=DEFAULT_SFX_DIR,
        help="Optional SFX directory; clips are layered at marker timestamps",
    )
    parser.add_argument(
        "--channel-handle",
        default=DEFAULT_CHANNEL_HANDLE,
        help="Persistent watermark handle shown throughout the video",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Path for final output MP4")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = compose_video(
        bg_path=args.background,
        audio_path=args.voiceover,
        script_path=args.script,
        output_path=args.output,
        word_timing_path=args.word_timings,
        subtitle_path=args.subtitles,
        sfx_dir=args.sfx_dir,
        channel_handle=args.channel_handle,
        subtitle_mode=args.subtitle_mode,
        audio_delay=args.audio_delay,
    )
    print(f"Wrote final video to {output_path}")


if __name__ == "__main__":
    main()