from google.cloud import texttospeech

_client: texttospeech.TextToSpeechAsyncClient | None = None


def _get_client() -> texttospeech.TextToSpeechAsyncClient:
    global _client
    if _client is None:
        _client = texttospeech.TextToSpeechAsyncClient()
    return _client


def _lang_code(voice_name: str) -> str:
    # voice_name format: "en-US-Neural2-A" → "en-US"
    parts = voice_name.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return "en-US"


async def synthesize(text: str, voice_name: str) -> bytes:
    client = _get_client()

    response = await client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(
            name=voice_name,
            language_code=_lang_code(voice_name),
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
        ),
    )
    return response.audio_content
