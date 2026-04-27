from dataclasses import dataclass
from ai.providers import get_ai_client
from ai.prompts.generator import FULL_AI_PROMPT, TOPIC_GUIDED_PROMPT, TIGHTENER_PROMPT
from ai.prompts.reviewer import REVIEWER_PROMPT, REVIEWER_SCHEMA
from ai.prompts.modifier import MODIFIER_PROMPT
from db.queries.settings import get_setting


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


async def run_script_step(
    job_id: int,
    mode: str,  # full_ai | topic_guided | manual
    topic: str | None = None,
    raw_script: str | None = None,
    series_context: str | None = None,
    manual_override_script: bool = False,
) -> ScriptOutput:
    client = get_ai_client()

    approval_threshold = int(get_setting("approval_threshold") or 90)
    max_iterations = int(get_setting("max_reviewer_iterations") or 2)

    # --- Generate initial script ---
    if mode == "manual" or manual_override_script:
        initial_script = raw_script or ""
    elif mode == "topic_guided":
        prompt = TOPIC_GUIDED_PROMPT.format(topic=topic or "")
        if series_context:
            prompt += f"\n\nPrevious episode context:\n{series_context}"
        initial_script = await client.generate(prompt)
    else:  # full_ai
        prompt = FULL_AI_PROMPT
        if series_context:
            prompt += f"\n\nPrevious episode context:\n{series_context}"
        initial_script = await client.generate(prompt)

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

    # --- Tightener: produce short variant ---
    tightener_prompt = TIGHTENER_PROMPT.format(script=current_script)
    short_script = await client.generate(tightener_prompt)

    return ScriptOutput(full=current_script, short=short_script, score=last_score)
