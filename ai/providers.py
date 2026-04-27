from ai.client import generate as _generate


class GeminiClient:
    async def generate(self, prompt: str, response_schema: dict | None = None) -> str | dict:
        return await _generate(prompt, response_schema)


_instance: GeminiClient | None = None


def get_ai_client() -> GeminiClient:
    global _instance
    if _instance is None:
        _instance = GeminiClient()
    return _instance
