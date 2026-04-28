import asyncio
import json
import os

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

MODEL = "gemma-4-31b-it"

# Retry config for transient 503/429 errors
_MAX_API_RETRIES = 6
_BASE_BACKOFF = 2.0  # seconds; doubles each attempt (2, 4, 8, 16, 32, 64)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set in .env")
        _client = genai.Client(api_key=api_key)
    return _client


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc)
    return (
        "503" in msg or "500" in msg or "429" in msg
        or "UNAVAILABLE" in msg or "RESOURCE_EXHAUSTED" in msg or "INTERNAL" in msg
    )


async def generate(prompt: str, response_schema: dict | None = None) -> str | dict:
    client = _get_client()
    last_exc = None

    for attempt in range(_MAX_API_RETRIES):
        try:
            if response_schema:
                response = await client.aio.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=response_schema,
                    ),
                )
                return json.loads(response.text)
            else:
                response = await client.aio.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                )
                return response.text

        except Exception as exc:
            last_exc = exc
            if _is_retryable(exc) and attempt < _MAX_API_RETRIES - 1:
                wait = _BASE_BACKOFF * (2 ** attempt)
                await asyncio.sleep(wait)
            else:
                raise

    raise last_exc
