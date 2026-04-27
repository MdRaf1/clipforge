from db.connection import get_db


CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    setting_key   TEXT PRIMARY KEY,
    setting_value TEXT
);
"""

CREATE_FOOTAGE = """
CREATE TABLE IF NOT EXISTS footage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL,
    path        TEXT NOT NULL,
    duration    REAL,
    created_at  TEXT NOT NULL
);
"""

CREATE_SERIES = """
CREATE TABLE IF NOT EXISTS series (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
);
"""

CREATE_SERIES_ENTRIES = """
CREATE TABLE IF NOT EXISTS series_entries (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id             INTEGER NOT NULL REFERENCES series(id),
    part_number           INTEGER NOT NULL,
    script_json           TEXT NOT NULL,
    unprocessed_remainder TEXT
);
"""

CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id                  INTEGER REFERENCES series(id),
    footage_id                 INTEGER REFERENCES footage(id),
    platform_flags             TEXT NOT NULL,
    series_type                TEXT,
    episode_number             INTEGER,
    status                     TEXT NOT NULL DEFAULT 'pending',
    title                      TEXT,
    created_at                 TEXT NOT NULL,
    output_video_full_path     TEXT,
    output_video_short_path    TEXT,
    output_thumbnail_path      TEXT,
    generation_mode            TEXT DEFAULT 'full_ai',
    topic                      TEXT,
    raw_script                 TEXT,
    manual_override_script     INTEGER DEFAULT 0,
    manual_override_voiceover  INTEGER DEFAULT 0
);
"""

# Columns added after initial schema — applied via ALTER TABLE for existing DBs
_JOBS_MIGRATIONS = [
    "ALTER TABLE jobs ADD COLUMN generation_mode TEXT DEFAULT 'full_ai'",
    "ALTER TABLE jobs ADD COLUMN topic TEXT",
    "ALTER TABLE jobs ADD COLUMN raw_script TEXT",
    "ALTER TABLE jobs ADD COLUMN manual_override_script INTEGER DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN manual_override_voiceover INTEGER DEFAULT 0",
]

CREATE_JOB_STEPS = """
CREATE TABLE IF NOT EXISTS job_steps (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       INTEGER NOT NULL REFERENCES jobs(id),
    step_name    TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    output_json  TEXT,
    completed_at TEXT
);
"""

DEFAULT_SETTINGS = [
    ("wizard_completed", "false"),
    ("approval_threshold", "90"),
    ("max_reviewer_iterations", "2"),
    ("whisper_model", "small"),
    ("rainbow_border_enabled", "true"),
    ("max_retries", "3"),
    ("default_platforms", '["youtube_shorts", "tiktok"]'),
    ("cloud_tts_voice", "en-US-Neural2-D"),
    ("local_tts_voice", "af_heart"),
    ("available_cloud_voices", "[]"),
]

STEP_NAMES = [
    "script",
    "voiceover_full",
    "voiceover_short",
    "cutting_full",
    "cutting_short",
    "subtitles_full",
    "subtitles_short",
    "render_full",
    "render_short",
    "thumbnail",
    "metadata",
]


def init_db():
    with get_db() as conn:
        conn.execute(CREATE_SETTINGS)
        conn.execute(CREATE_FOOTAGE)
        conn.execute(CREATE_SERIES)
        conn.execute(CREATE_SERIES_ENTRIES)
        conn.execute(CREATE_JOBS)
        conn.execute(CREATE_JOB_STEPS)

        for key, value in DEFAULT_SETTINGS:
            conn.execute(
                "INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)",
                (key, value),
            )

        # Apply migrations for existing DBs (ALTER TABLE IF NOT EXISTS is not SQLite syntax,
        # so we swallow "duplicate column" errors)
        for migration in _JOBS_MIGRATIONS:
            try:
                conn.execute(migration)
            except Exception:
                pass
