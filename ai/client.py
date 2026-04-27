import os
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client() -> genai.GenerativeModel:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set in .env")
        genai.configure(api_key=api_key)
        _client = genai.GenerativeModel("gemini-2.0-flash-latest")
    return _client


async def generate(prompt: str, response_schema: dict | None = None) -> str | dict:
    loop = asyncio.get_event_loop()

    def _call():
        model = _get_client()
        if response_schema:
            import json
            json_model = genai.GenerativeModel(
                "gemini-2.0-flash-latest",
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                ),
            )
            response = json_model.generate_content(prompt)
            return json.loads(response.text)
        else:
            response = model.generate_content(prompt)
            return response.text

    return await loop.run_in_executor(None, _call)
