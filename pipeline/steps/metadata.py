import json
import os

from ai.providers import get_ai_client
from ai.prompts.metadata import METADATA_PROMPT
from media.platform_rules import PLATFORM_RULES
from utils.logger import get_logger

logger = get_logger(__name__)

# Schema for structured JSON output
_METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["title", "description"],
}

# Map each platform to a canonical title/description limit key
_PLATFORM_LIMITS = {
    "youtube_shorts": {"title_limit": 100, "description_limit": 5000},
    "tiktok": {"title_limit": 150, "description_limit": 2200},
    "instagram_reels": {"title_limit": 150, "description_limit": 2200},
    "facebook_reels": {"title_limit": 150, "description_limit": 500},
}

# Deduplicate: only one Gemini call per (script_variant) group
_VARIANT_PLATFORMS = {
    "full": ["tiktok", "facebook_reels"],
    "short": ["youtube_shorts", "instagram_reels"],
}


async def run_metadata_step(
    job_id: int,
    script_full: str,
    script_short: str,
    platform_flags: list[str],
    output_dir: str,
    series_type: str = "standalone",
    series_name: str | None = None,
    episode_number: int | None = None,
) -> dict:
    client = get_ai_client()

    series_context = ""
    if series_type in ("first_episode", "continuation") and series_name:
        ep = f" episode {episode_number}" if episode_number else ""
        series_context = f"Series: {series_name}{ep}. Reference the series name in the title and description."

    metadata: dict[str, dict] = {}

    scripts = {"full": script_full, "short": script_short}

    for variant, platforms in _VARIANT_PLATFORMS.items():
        active = [p for p in platforms if p in platform_flags]
        if not active:
            continue

        # Use the first active platform's limits for the call; they share the same
        # variant so copy quality will be similar.
        primary = active[0]
        limits = _PLATFORM_LIMITS.get(primary, {"title_limit": 150, "description_limit": 2200})

        prompt = METADATA_PROMPT.format(
            platform=", ".join(active),
            title_limit=limits["title_limit"],
            description_limit=limits["description_limit"],
            script_variant=variant,
            series_context=series_context,
            script=scripts[variant][:3000],
        )

        logger.info("metadata: generating for platforms %s", active)
        result = await client.generate(prompt, response_schema=_METADATA_SCHEMA)

        for platform in active:
            metadata[platform] = {
                "title": str(result.get("title", ""))[:limits["title_limit"]],
                "description": str(result.get("description", ""))[:limits["description_limit"]],
            }

    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return {
        "metadata_path": metadata_path,
        "metadata": metadata,
    }
