PLATFORM_RULES = {
    "youtube_shorts": {
        "max_duration": 180,
        "target_duration_range": (50, 58),
        "resolution": (1080, 1920),
        "format": "mp4",
        "codec": "h264",
        "audio_codec": "aac",
        "audio_bitrate": "128k",
        "sample_rate": 48000,
        "title_limit": 100,
        "description_limit": 5000,
        "script_variant": "short",
    },
    "tiktok": {
        "max_duration": 600,
        "target_duration_range": (65, 75),
        "resolution": (1080, 1920),
        "format": "mp4",
        "codec": "h264",
        "audio_codec": "aac",
        "audio_bitrate": "128k",
        "sample_rate": 48000,
        "caption_limit": 2200,
        "script_variant": "full",
    },
    "instagram_reels": {
        "max_duration": 900,
        "target_duration_range": (50, 58),
        "resolution": (1080, 1920),
        "format": "mp4",
        "codec": "h264",
        "audio_codec": "aac",
        "audio_bitrate": "128k",
        "sample_rate": 48000,
        "caption_limit": 2200,
        "script_variant": "short",
    },
    "facebook_reels": {
        "max_duration": 90,
        "target_duration_range": (65, 75),
        "resolution": (1080, 1920),
        "format": "mp4",
        "codec": "h264",
        "audio_codec": "aac",
        "audio_bitrate": "128k",
        "script_variant": "full",
    },
}


def get_required_variants(platform_flags: list[str]) -> set[str]:
    """Return the set of script variants ('full', 'short') needed for the selected platforms."""
    return {PLATFORM_RULES[p]["script_variant"] for p in platform_flags if p in PLATFORM_RULES}


def check_facebook_duration_warning(platform_flags: list[str], full_video_duration: float) -> str | None:
    if "facebook_reels" in platform_flags and full_video_duration > 90:
        return (
            f"Warning: Facebook Reels has a 90s hard limit. "
            f"Your full video is {full_video_duration:.1f}s and may be non-compliant."
        )
    return None
