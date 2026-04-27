import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set in .env")
        _client = genai.Client(api_key=api_key)
    return _client


async def generate(prompt: str, response_schema: dict | None = None) -> str | dict:
    client = _get_client()

    if response_schema:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
            ),
        )
        import json
        return json.loads(response.text)
    else:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text
