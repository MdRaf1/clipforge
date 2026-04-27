import io
import numpy as np

# fmt: off
KOKORO_VOICES = [
    "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jadzia",
    "af_jessica", "af_kore", "af_nicole", "af_nova", "af_river",
    "af_sarah", "af_sky", "af_star", "af_v0", "af_v0belle",
    "af_v0irulan", "af_v0nicola", "am_adam", "am_echo", "am_eric",
    "am_fenrir", "am_fable", "am_liam", "am_michael", "am_onyx",
    "am_orion", "am_puck", "am_santa", "am_v0adam", "am_v0gurney",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel",
    "bm_fable", "bm_george", "bm_lewis", "bm_liam", "bm_santa",
    "ef_dora", "em_alex", "em_santa", "ff_siwis", "hf_alpha",
    "hf_beta", "hm_omega", "hm_psi", "if_sara", "im_nicola",
    "jf_alpha", "jf_gongitsune", "jf_nezuko", "jm_kumo",
]
# fmt: on

_pipeline = None


def _get_pipeline(voice: str):
    global _pipeline
    if _pipeline is None:
        from kokoro import KPipeline

        lang = voice[:2] if len(voice) >= 2 else "a"
        _pipeline = KPipeline(lang_code=lang)
    return _pipeline


def synthesize(text: str, voice: str) -> bytes:
    pipeline = _get_pipeline(voice)
    audio_chunks = []
    for _, _, audio in pipeline(text, voice=voice):
        audio_chunks.append(audio)

    if not audio_chunks:
        return b""

    combined = np.concatenate(audio_chunks)
    buf = io.BytesIO()
    import soundfile as sf

    sf.write(buf, combined, 24000, format="MP3")
    return buf.getvalue()
