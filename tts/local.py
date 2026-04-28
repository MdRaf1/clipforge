import asyncio
import tempfile
import os

# edge-tts voices — English selection covering common use cases
# Full list: run `edge-tts --list-voices` in the terminal
EDGE_TTS_VOICES = [
    "en-US-AndrewNeural",
    "en-US-AndrewMultilingualNeural",
    "en-US-AriaNeural",
    "en-US-AvaNeural",
    "en-US-AvaMultilingualNeural",
    "en-US-BrianNeural",
    "en-US-BrianMultilingualNeural",
    "en-US-ChristopherNeural",
    "en-US-EmmaNeural",
    "en-US-EmmaMultilingualNeural",
    "en-US-EricNeural",
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-US-MichelleNeural",
    "en-US-RogerNeural",
    "en-US-SteffanNeural",
    "en-GB-LibbyNeural",
    "en-GB-MaisieNeural",
    "en-GB-RyanNeural",
    "en-GB-SoniaNeural",
    "en-GB-ThomasNeural",
    "en-AU-NatashaNeural",
    "en-AU-WilliamNeural",
    "en-CA-ClaraNeural",
    "en-CA-LiamNeural",
]

DEFAULT_VOICE = "en-US-GuyNeural"


async def synthesize_async(text: str, voice: str) -> bytes:
    """Async edge-tts synthesis — returns MP3 bytes."""
    import edge_tts

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name

    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def synthesize(text: str, voice: str) -> bytes:
    """Sync wrapper — for use with run_in_executor."""
    return asyncio.run(synthesize_async(text, voice))
