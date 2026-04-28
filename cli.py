"""ClipForge CLI — interactive terminal interface.

Usage:
    python cli.py run

Walks the user through every decision the web UI exposes, then calls the
pipeline runner directly (no HTTP layer). Live progress is streamed from the
same in-memory event queue the WebSocket endpoint uses, so the human-in-the-
loop review pause works end-to-end from the terminal.
"""

import asyncio
import json
import os
import shutil
import sys

import questionary
import typer

from config import FOOTAGE_DIR, OUTPUTS_DIR
from db.models import init_db
from db.queries.footage import add_footage, list_footage
from db.queries.jobs import create_job, update_job_status
from db.queries.series import create_series, get_series_entries, list_series
from db.queries.settings import get_setting, set_setting
from media.platform_rules import PLATFORM_RULES
from tts.local import EDGE_TTS_VOICES

app = typer.Typer(help="ClipForge — automated viral gaming video pipeline (CLI).")


@app.callback()
def _root() -> None:
    """Force Typer to expose subcommands (e.g. `run`) rather than flattening."""


STEP_LABELS = {
    "script": "Generating script",
    "voiceover_full": "Creating voiceover (full)",
    "voiceover_short": "Creating voiceover (short)",
    "cutting_full": "Cutting footage (full)",
    "cutting_short": "Cutting footage (short)",
    "subtitles_full": "Generating subtitles (full)",
    "subtitles_short": "Generating subtitles (short)",
    "render_full": "Rendering video (full)",
    "render_short": "Rendering video (short)",
    "thumbnail": "Creating thumbnail",
    "metadata": "Generating metadata",
}

PLATFORM_LABELS = {
    "youtube_shorts": "YouTube Shorts",
    "tiktok": "TikTok",
    "instagram_reels": "Instagram Reels",
    "facebook_reels": "Facebook Reels",
}


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

def _print_header() -> None:
    bar = "=" * 60
    typer.echo(bar)
    typer.echo("ClipForge — automated viral gaming video pipeline")
    typer.echo(bar)


def _ensure_wizard() -> None:
    """Run a first-use terminal walkthrough if not yet completed."""
    if get_setting("wizard_completed") == "true":
        return

    typer.echo("")
    typer.echo("First time using ClipForge — quick tour before we start.")
    typer.echo("")

    tour = [
        (
            "Footage library",
            "Pick a gameplay file (MP4/MKV). Uploads persist across runs so "
            "you can reuse the same footage later.",
        ),
        (
            "Generation modes",
            "Full AI picks a topic and writes the script. Topic-guided takes "
            "your topic and writes the script. Manual lets you paste a script.",
        ),
        (
            "AI review loop",
            "By default every script runs through a Reviewer/Modifier loop "
            "until the score clears the approval threshold. In Manual mode "
            "you can opt out of the loop.",
        ),
        (
            "Overrides",
            "Voiceover override uses a local TTS voice (edge-tts) — no API "
            "key and works offline.",
        ),
        (
            "Platforms",
            "Pick any of YouTube Shorts, TikTok, Instagram Reels, Facebook "
            "Reels. Two videos are generated (full 65-75s + short 50-58s) "
            "and shared across platforms that want the same duration.",
        ),
        (
            "Series",
            "Standalone is a one-off. First Episode starts a new series. "
            "Continuation picks up an existing one with an auto-generated "
            "'Last time on...' intro.",
        ),
        (
            "Outputs",
            "Final files land in data/outputs/<job_id>/. The CLI prints the "
            "path when the pipeline finishes.",
        ),
    ]
    for title, body in tour:
        typer.echo(f"- {title}: {body}")
        go = questionary.confirm("Got it?", default=True).ask()
        if not go:
            typer.echo("Tour exited. Re-run with `python cli.py run --wizard` any time.")
            return

    set_setting("wizard_completed", "true")
    typer.echo("")
    typer.echo("Tour done. Let's build.")
    typer.echo("")


def _validate_footage_path(text: str) -> bool | str:
    path = os.path.expanduser((text or "").strip())
    if not path:
        return "Enter a path."
    if not os.path.isfile(path):
        return "File does not exist."
    if os.path.splitext(path)[1].lower() not in {".mp4", ".mkv"}:
        return "Only MP4 and MKV files are supported."
    return True


def _upload_footage_interactive() -> dict:
    src = questionary.path("Path to MP4/MKV file:", validate=_validate_footage_path).ask()
    if src is None:
        raise typer.Exit()
    src = os.path.expanduser(src.strip())

    basename = os.path.basename(src)
    dest = os.path.join(FOOTAGE_DIR, basename)
    if os.path.exists(dest):
        base, ext = os.path.splitext(basename)
        i = 1
        while os.path.exists(dest):
            dest = os.path.join(FOOTAGE_DIR, f"{base}_{i}{ext}")
            i += 1
    shutil.copyfile(src, dest)

    footage_id = add_footage(filename=os.path.basename(dest), path=dest)
    typer.echo(f"Saved {os.path.basename(dest)} (id={footage_id}).")
    return {"id": footage_id, "filename": os.path.basename(dest), "path": dest}


def _select_footage() -> dict:
    items = list_footage()
    if not items:
        typer.echo("No footage on record yet — upload one first.")
        return _upload_footage_interactive()

    choices = [
        questionary.Choice(title=f'{f["filename"]} (id={f["id"]})', value=f)
        for f in items
    ]
    choices.append(questionary.Choice(title="Upload new footage...", value="__upload__"))

    picked = questionary.select("Pick a footage file:", choices=choices).ask()
    if picked is None:
        raise typer.Exit()
    if picked == "__upload__":
        return _upload_footage_interactive()
    return picked


def _read_pasted_script(label: str) -> str:
    typer.echo(
        f"Paste {label}. End with a blank line + Ctrl-D "
        "(Unix) or Ctrl-Z + Enter (Windows)."
    )
    raw = sys.stdin.read().strip()
    if not raw:
        typer.echo("Empty input — aborting.")
        raise typer.Exit()
    return raw


def _select_generation_mode() -> tuple[str, str | None, str | None]:
    mode = questionary.select(
        "Generation mode:",
        choices=[
            questionary.Choice("Full AI — AI picks topic and writes script", "full_ai"),
            questionary.Choice("Topic-guided — you give the topic, AI writes the script", "topic_guided"),
            questionary.Choice("Manual — paste a finished script", "manual"),
        ],
    ).ask()
    if mode is None:
        raise typer.Exit()

    topic = None
    raw_script = None
    if mode == "topic_guided":
        topic = questionary.text("Topic:").ask()
        if not topic:
            raise typer.Exit()
        topic = topic.strip()
    elif mode == "manual":
        raw_script = _read_pasted_script("your script")

    return mode, topic, raw_script


def _select_overrides(mode: str) -> tuple[bool, bool, str | None]:
    script_override = False
    if mode == "manual":
        script_override = bool(
            questionary.confirm(
                "Skip the AI review loop for your manual script?", default=False
            ).ask()
        )

    voiceover_override = bool(
        questionary.confirm(
            "Use local TTS (edge-tts) instead of Google Cloud TTS?",
            default=False,
        ).ask()
    )

    local_voice = None
    if voiceover_override:
        default_voice = get_setting("local_tts_voice")
        if default_voice not in EDGE_TTS_VOICES:
            default_voice = EDGE_TTS_VOICES[0]
        local_voice = questionary.select(
            "Pick a local TTS voice:",
            choices=EDGE_TTS_VOICES,
            default=default_voice,
        ).ask()
        if local_voice is None:
            raise typer.Exit()
        set_setting("local_tts_voice", local_voice)

    return script_override, voiceover_override, local_voice


def _select_platforms() -> list[str]:
    default_raw = get_setting("default_platforms") or '["youtube_shorts", "tiktok"]'
    try:
        defaults = json.loads(default_raw)
    except Exception:
        defaults = ["youtube_shorts", "tiktok"]

    choices = [
        questionary.Choice(title=PLATFORM_LABELS[k], value=k, checked=(k in defaults))
        for k in PLATFORM_RULES
    ]
    picked = questionary.checkbox(
        "Which platforms to target? (space to toggle, enter to confirm)",
        choices=choices,
    ).ask()
    if not picked:
        typer.echo("You must pick at least one platform.")
        raise typer.Exit()

    set_setting("default_platforms", json.dumps(picked))
    return picked


def _select_series() -> tuple[str, int | None, int | None]:
    series_type = questionary.select(
        "Series type:",
        choices=[
            questionary.Choice("Standalone (one-off)", "standalone"),
            questionary.Choice("First Episode (start a new series)", "first_episode"),
            questionary.Choice("Continuation (next part of an existing series)", "continuation"),
        ],
    ).ask()
    if series_type is None:
        raise typer.Exit()

    series_id = None
    episode_number = None

    if series_type == "first_episode":
        name = questionary.text("Series name:").ask()
        if not name or not name.strip():
            raise typer.Exit()
        series_id = create_series(name.strip())
        episode_number = 1

    elif series_type == "continuation":
        all_series = list_series()
        if not all_series:
            typer.echo("No existing series — falling back to Standalone.")
            series_type = "standalone"
        else:
            choices = [
                questionary.Choice(f'{s["name"]} (id={s["id"]})', s["id"])
                for s in all_series
            ]
            series_id = questionary.select("Which series?", choices=choices).ask()
            if series_id is None:
                raise typer.Exit()
            entries = get_series_entries(series_id)
            episode_number = len(entries) + 1

    return series_type, series_id, episode_number


def _confirm_summary(
    footage: dict,
    mode: str,
    topic: str | None,
    script_override: bool,
    voiceover_override: bool,
    local_voice: str | None,
    platforms: list[str],
    series_type: str,
    series_id: int | None,
    episode_number: int | None,
) -> bool:
    typer.echo("")
    typer.echo("Summary:")
    typer.echo(f"  Footage:         {footage['filename']} (id={footage['id']})")
    typer.echo(f"  Mode:            {mode}" + (f" — topic: {topic!r}" if topic else ""))
    typer.echo(f"  Script override: {script_override}")
    typer.echo(
        f"  Voiceover:       {'local (' + (local_voice or '?') + ')' if voiceover_override else 'cloud'}"
    )
    typer.echo(f"  Platforms:       {', '.join(PLATFORM_LABELS[p] for p in platforms)}")
    series_desc = series_type
    if series_type in ("first_episode", "continuation"):
        series_desc += f" (series_id={series_id}, episode={episode_number})"
    typer.echo(f"  Series:          {series_desc}")
    typer.echo("")
    return bool(questionary.confirm("Start the pipeline with these settings?", default=True).ask())


# ---------------------------------------------------------------------------
# Live pipeline progress
# ---------------------------------------------------------------------------

async def _watch_and_run(job_id: int) -> None:
    """Run the pipeline and stream its events to the terminal."""
    from api.ws import _queues
    from pipeline.runner import run

    q: asyncio.Queue = asyncio.Queue()
    _queues.setdefault(job_id, []).append(q)

    runner_task = asyncio.create_task(run(job_id))

    typer.echo("")
    typer.echo("Pipeline started. Live progress:")
    typer.echo("-" * 60)

    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                event = None

            if event is not None:
                await _handle_event(event, job_id)
                if event.get("type") == "complete":
                    break

            if runner_task.done():
                while not q.empty():
                    await _handle_event(q.get_nowait(), job_id)
                break
    finally:
        try:
            _queues[job_id].remove(q)
            if not _queues[job_id]:
                del _queues[job_id]
        except (KeyError, ValueError):
            pass

        if not runner_task.done():
            await runner_task
        elif runner_task.exception() is not None:
            raise runner_task.exception()


async def _handle_event(event: dict, job_id: int) -> None:
    etype = event.get("type")
    if etype == "step_update":
        step = event.get("step", "")
        status = event.get("status", "")
        label = STEP_LABELS.get(step, step)
        if status == "in_progress":
            typer.echo(f"  > {label}...")
        elif status == "done":
            typer.echo(f"  v {label}")
        elif status == "failed":
            msg = event.get("message") or ""
            typer.echo(f"  x {label} — FAILED: {msg}", err=True)
    elif etype == "review_pause":
        await _handle_review_pause(event, job_id)
    elif etype == "complete":
        typer.echo("-" * 60)
        typer.echo("Pipeline complete.")


async def _handle_review_pause(event: dict, job_id: int) -> None:
    from pipeline.runner import get_review_queue

    typer.echo("")
    typer.echo("=" * 60)
    typer.echo("Script review stalled — your call.")
    typer.echo("=" * 60)
    typer.echo(f"Score: {event.get('score')}")
    typer.echo(f"Reviewer note: {event.get('user_summary')}")
    typer.echo("")
    typer.echo("Current script:")
    typer.echo("-" * 60)
    typer.echo(event.get("script") or "")
    typer.echo("-" * 60)
    typer.echo("")

    action = await asyncio.to_thread(
        lambda: questionary.select(
            "What do you want to do?",
            choices=[
                questionary.Choice("Continue iterating", "continue"),
                questionary.Choice("Stop the pipeline", "stop"),
                questionary.Choice("Edit the script and resubmit", "edit_resubmit"),
                questionary.Choice("Force-accept the current script", "force_accept"),
            ],
        ).ask()
    )
    if action is None:
        action = "stop"

    edited_script = None
    if action == "edit_resubmit":
        edited_script = await asyncio.to_thread(_read_pasted_script, "your edited script")

    get_review_queue(job_id).put_nowait(
        {"action": action, "edited_script": edited_script}
    )


# ---------------------------------------------------------------------------
# Typer command
# ---------------------------------------------------------------------------

@app.command()
def run(
    wizard: bool = typer.Option(
        False, "--wizard", help="Re-run the first-use terminal walkthrough."
    ),
):
    """Run ClipForge interactively: pick footage, mode, platforms, series, go."""
    init_db()
    _print_header()

    if wizard:
        set_setting("wizard_completed", "false")

    _ensure_wizard()

    footage = _select_footage()
    mode, topic, raw_script = _select_generation_mode()
    script_override, voiceover_override, local_voice = _select_overrides(mode)
    platforms = _select_platforms()
    series_type, series_id, episode_number = _select_series()

    if not _confirm_summary(
        footage, mode, topic, script_override, voiceover_override, local_voice,
        platforms, series_type, series_id, episode_number,
    ):
        typer.echo("Cancelled.")
        raise typer.Exit()

    job_id = create_job(
        footage_id=footage["id"],
        platform_flags=platforms,
        series_type=series_type,
        series_id=series_id,
        episode_number=episode_number,
    )
    update_job_status(
        job_id,
        "pending",
        generation_mode=mode,
        topic=topic,
        raw_script=raw_script,
        manual_override_script=int(script_override),
        manual_override_voiceover=int(voiceover_override),
    )

    try:
        asyncio.run(_watch_and_run(job_id))
    except KeyboardInterrupt:
        update_job_status(job_id, "interrupted")
        typer.echo(
            "\nInterrupted. Job marked as `interrupted` — resume from the web UI.",
            err=True,
        )
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"\nPipeline errored: {e}", err=True)
        raise typer.Exit(code=1)

    output_dir = os.path.join(OUTPUTS_DIR, str(job_id))
    typer.echo("")
    typer.echo("=" * 60)
    typer.echo(f"Done. Output directory:\n  {output_dir}")
    typer.echo("=" * 60)


if __name__ == "__main__":
    app()
