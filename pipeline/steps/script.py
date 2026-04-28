from dataclasses import dataclass
from ai.providers import get_ai_client
from ai.prompts.generator import FULL_AI_PROMPT, TOPIC_GUIDED_PROMPT, TIGHTENER_PROMPT
from ai.prompts.reviewer import REVIEWER_PROMPT, REVIEWER_SCHEMA
from ai.prompts.modifier import MODIFIER_PROMPT
from db.queries.settings import get_setting

FULL_MIN_WORDS = 230
FULL_MAX_WORDS = 260
SHORT_MIN_WORDS = 180
SHORT_MAX_WORDS = 200
MAX_RETRIES = 3


@dataclass
class ScriptOutput:
    full: str
    short: str
    score: int | None


class HumanInTheLoopPause(Exception):
    def __init__(self, script: str, score: int, user_summary: str):
        self.script = script
        self.score = score
        self.user_summary = user_summary
        super().__init__(f"Script review stalled at score {score}: {user_summary}")


def _word_count(text: str) -> int:
    return len(text.split())


async def _generate_full_script(client, mode: str, topic: str | None, footage_context: str, series_context: str | None) -> str:
    """Generate initial full script. Retry up to MAX_RETRIES if word count is below FULL_MIN_WORDS."""
    def _build_prompt() -> str:
        if mode == "topic_guided":
            p = TOPIC_GUIDED_PROMPT.format(topic=topic or "")
        else:
            p = FULL_AI_PROMPT
        if series_context:
            p += f"\n\nPrevious episode context:\n{series_context}"
        return p

    last_script = ""
    for attempt in range(MAX_RETRIES):
        if attempt == 0:
            script = await client.generate(_build_prompt())
        else:
            wc = _word_count(last_script)
            expand_prompt = (
                _build_prompt()
                + f"\n\n⚠️ Your previous attempt was only {wc} words, which is too short. "
                f"The script MUST be at least {FULL_MIN_WORDS} words. "
                f"Rewrite it now, expanding with more vivid detail, additional tension beats, "
                f"or supporting dialogue. Keep the same story arc and tone. "
                f"Aim for {FULL_MIN_WORDS}-{FULL_MAX_WORDS} words."
            )
            script = await client.generate(expand_prompt)

        last_script = script
        if _word_count(script) >= FULL_MIN_WORDS:
            return script

    # Best effort after retries
    return last_script


async def _generate_short_script(client, full_script: str) -> str:
    """Run the Tightener, retrying if output is outside the target range."""
    last_script = ""
    for attempt in range(MAX_RETRIES):
        if attempt == 0:
            prompt = TIGHTENER_PROMPT.format(script=full_script)
        else:
            wc = _word_count(last_script)
            if wc < SHORT_MIN_WORDS:
                guidance = f"Your previous attempt was {wc} words which is too short. Add back critical detail to reach {SHORT_MIN_WORDS}-{SHORT_MAX_WORDS} words."
            else:
                guidance = f"Your previous attempt was {wc} words which is too long. Cut more to reach {SHORT_MIN_WORDS}-{SHORT_MAX_WORDS} words."
            prompt = TIGHTENER_PROMPT.format(script=full_script) + f"\n\n⚠️ {guidance}"

        script = await client.generate(prompt)
        last_script = script
        wc = _word_count(script)
        if SHORT_MIN_WORDS <= wc <= SHORT_MAX_WORDS:
            return script

    return last_script


async def run_script_step(
    job_id: int,
    mode: str,  # full_ai | topic_guided | manual
    topic: str | None = None,
    raw_script: str | None = None,
    series_context: str | None = None,
    manual_override_script: bool = False,
    footage_context: str | None = None,
) -> ScriptOutput:
    client = get_ai_client()

    approval_threshold = int(get_setting("approval_threshold") or 90)
    max_iterations = int(get_setting("max_reviewer_iterations") or 2)

    footage_context = footage_context or "Minecraft gameplay footage"

    # --- Generate initial script ---
    if mode == "manual" or manual_override_script:
        initial_script = raw_script or ""
    else:
        initial_script = await _generate_full_script(client, mode, topic, footage_context, series_context)

    # --- Manual override: skip review loop entirely ---
    if manual_override_script:
        return ScriptOutput(full=initial_script, short=initial_script, score=None)

    # --- Reviewer → Modifier loop ---
    current_script = initial_script
    last_score = 0
    last_summary = ""

    for iteration in range(max_iterations + 1):
        reviewer_prompt = REVIEWER_PROMPT.format(script=current_script)
        review = await client.generate(reviewer_prompt, response_schema=REVIEWER_SCHEMA)

        last_score = review["score"]
        last_summary = review["user_summary"]

        if last_score >= approval_threshold:
            break

        if iteration >= max_iterations:
            raise HumanInTheLoopPause(current_script, last_score, last_summary)

        directives_text = "\n".join(f"- {d}" for d in review["rewrite_directives"])
        modifier_prompt = MODIFIER_PROMPT.format(
            script=current_script,
            score=last_score,
            user_summary=last_summary,
            rewrite_directives=directives_text,
        )
        current_script = await client.generate(modifier_prompt)

    # --- Tightener: produce short variant with word-count retries ---
    short_script = await _generate_short_script(client, current_script)

    return ScriptOutput(full=current_script, short=short_script, score=last_score)
