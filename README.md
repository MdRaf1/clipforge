<div align="center">

# ClipForge

**One story in. Four platform-ready viral videos out. One click.**

An automated pipeline for content creators and story writers that turns a topic or script — paired with any looping background footage for retention — into platform-compliant short-form video packages. Script, voiceover, cuts, subtitles, thumbnail, and per-platform metadata for YouTube Shorts, TikTok, Instagram Reels, and Facebook Reels.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-green.svg)](https://fastapi.tiangolo.com/)
[![Built with](https://img.shields.io/badge/Built%20with-FFmpeg%20%7C%20Gemini%20%7C%20Whisper-orange.svg)]()

</div>

---

## Why

Content creators and story writers who want to post viral short-form video spend hours per piece on manual editing — scripting, voiceover, cutting, subtitles, thumbnail, metadata, and then reformatting for every platform. The loop of "write a story → turn it into four platform-ready videos" has no good end-to-end tool. Gameplay footage is the retention layer that keeps eyes on the screen while the story plays.

ClipForge closes that gap. You bring the story. It does the rest.

## What it does

Give it looping background footage (MP4/MKV) and a generation mode. It produces:

- **Two videos** — `video_full.mp4` (65-75 s, for TikTok + Facebook Reels) and `video_short.mp4` (50-58 s, for YouTube Shorts + Instagram Reels)
- **One thumbnail** with AI-generated hook text overlay
- **Per-platform metadata** — title + description respecting each platform's character limits
- **Burned-in subtitles** synced to the voiceover via Whisper
- **A green progress bar** that travels the perimeter of the frame and completes exactly when the video ends

All four platforms are served by exactly two video files — platform rules are deduplicated so we don't re-encode identical output. Only metadata is generated per-platform.

## Generation modes

| Mode | What you provide | What ClipForge does |
|---|---|---|
| **Full AI** | Nothing — just click the dice | Generates topic + script, then reviews + revises in an agent loop |
| **Topic-guided** | A topic string | Generates script from your topic, then reviews + revises |
| **Manual** | Your own script | Reviews + polishes (or skips review entirely if you opt out) |

Any feature can be overridden independently — run with manual voiceover while keeping AI script generation, or vice versa.

## Multi-agent script pipeline

```
Generator ─▶ Reviewer ─▶ [score ≥ threshold?] ─▶ Approved
                │              │
                │              └─▶ Modifier ─▶ Reviewer (loop)
                │
                └─▶ Tightener ─▶ Short variant (50-58 s)
```

- **Generator** writes the script from a topic (or from scratch, if you pick Full AI)
- **Reviewer** scores it (0-100 composite: hook strength, pacing, retention risk) and emits structured rewrite directives as JSON
- **Modifier** rewrites based on the directives
- **Tightener** produces the shorter platform variant after approval
- **Human-in-the-loop pause** — if the score stalls, the UI shows the current script, score, and reviewer summary, with four options: continue iterating, stop, edit and resubmit, or force-accept

All four agents are the same underlying model. They're differentiated only by prompt.

## Stack

| Layer | Tool |
|---|---|
| Language | Python 3.11+ |
| Web framework | FastAPI (async + WebSocket) |
| Frontend | Alpine.js + Tailwind CSS via CDN — zero build step |
| CLI | Typer + Questionary (interactive prompts, not flags) |
| AI | Google Gemma / Gemini via `google-genai` SDK |
| Cloud TTS | Google Cloud TTS (Neural2 voices, 4 M chars/month free) |
| Local TTS | Microsoft edge-tts — streaming, no local model download |
| Subtitle sync | OpenAI Whisper (`small` model, near-realtime on CPU) |
| Video processing | FFmpeg (all operations via async subprocess) |
| Image processing | Pillow, run in `ProcessPoolExecutor` to keep the event loop free |
| Database | SQLite with WAL mode |

## Quickstart

### Prerequisites
- Python **3.11 or newer**
- **FFmpeg** installed and on `PATH` (both `ffmpeg` and `ffprobe` commands)
- A **Google Gemini API key** (free at [aistudio.google.com](https://aistudio.google.com/app/apikey))
- *(Optional)* A **Google Cloud service account JSON** if you want Google Cloud TTS. Without it, ClipForge falls back to free edge-tts.

### Install

```bash
git clone https://github.com/MdRaf1/clipforge.git
cd clipforge
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Then edit .env and add your GEMINI_API_KEY
```

The `.env` file supports:

```ini
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json  # optional — for cloud TTS
CLIPFORGE_MODEL=gemini-pro-latest                             # optional — override AI model
```

### Run — Web UI

```bash
uvicorn main:app --reload
```

Open `http://localhost:8000`. The first-run spotlight wizard walks you through every section.

### Run — CLI

```bash
python cli.py run
```

Interactive terminal walkthrough — arrow-key pickers for footage, mode, platforms, and series. All features in the web UI are available here.

## Project structure

```
clipforge/
├── main.py                  FastAPI entry; lifespan event + router mounting
├── cli.py                   Typer + Questionary interactive CLI
├── config.py                Data-dir paths
│
├── api/                     FastAPI route handlers
│   ├── jobs.py              POST/GET /api/jobs, resume, review
│   ├── footage.py           Upload + list
│   ├── settings.py          Key-value settings CRUD
│   ├── series.py            Series tracking
│   ├── history.py           List, detail, delete (with file cleanup)
│   └── ws.py                WebSocket + state_sync + event relay
│
├── pipeline/
│   ├── runner.py            Orchestrator: sequencing, retry, checkpoints
│   ├── checkpoint.py        save_step / load_checkpoint / get_resume_step
│   └── steps/
│       ├── script.py        Generator → Reviewer → Modifier → Tightener
│       ├── voiceover.py     TTS + time-stretch to target duration
│       ├── cutting.py       Scene-detect + trim + portrait crop
│       ├── subtitles.py     Whisper → SRT (×2 tracks)
│       ├── render.py        Assemble + burn subs + progress bar
│       ├── thumbnail.py     Frame extract + Pillow text overlay
│       └── metadata.py      Per-platform title + description
│
├── ai/
│   ├── client.py            google-genai client + retry logic
│   ├── providers.py         get_ai_client() abstraction
│   └── prompts/             Generator / Reviewer / Modifier / Tightener / Thumbnail / Metadata
│
├── tts/
│   ├── cloud.py             Google Cloud TTS async wrapper
│   └── local.py             Microsoft edge-tts wrapper (25 voices)
│
├── media/
│   ├── ffmpeg.py            Async subprocess wrappers for all FFmpeg ops
│   ├── pillow.py            Thumbnail text overlay (ProcessPoolExecutor)
│   └── platform_rules.py    PLATFORM_RULES dict + dedup helpers
│
├── db/
│   ├── connection.py        SQLite + WAL pragma
│   ├── models.py            6 table schemas + default settings seed
│   └── queries/             jobs / series / footage / settings helpers
│
├── frontend/
│   ├── index.html           Single-page Alpine.js shell
│   ├── css/main.css         Spotlight wizard overlay + custom styles
│   └── js/
│       ├── app.js           Main state + UI controls
│       ├── wizard.js        First-run spotlight tour
│       ├── pipeline.js      WebSocket client + output reveal
│       └── history.js       History panel + delete flow
│
└── data/                    gitignored — runtime database + outputs + footage
```

## Roadmap

Things that are out of scope for v1 but naturally follow:

- **Multi-language support** — additional TTS voices + Whisper languages
- **Batch generation** — multiple videos from one footage dump
- **AI video cutting tuning** — adjustable highlight-selection aggression
- **Export preset profiles** — save full configuration as a named preset
- **SaaS packaging** — user accounts, cloud storage, hosted version
- **Subtitle customization** — font, size, color, position, animation style

## License

This project is licensed under the **GNU Affero General Public License v3.0** — see [LICENSE](LICENSE) for the full text.

---

<div align="center">

Built by <a href="https://github.com/MdRaf1">Rafi</a> · Submit an issue on the <a href="https://github.com/MdRaf1/clipforge/issues">tracker</a>

</div>
