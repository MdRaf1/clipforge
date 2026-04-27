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
    mode: str,
    topic: str | None = None,
    raw_script: str | None = None,
    manual_override_script: bool = False,
    series_context: str | None = None,
) -> ScriptOutput:
    client = get_ai_client()

    approval_threshold = int(get_setting("approval_threshold") or 90)
    max_iterations = int(get_setting("max_reviewer_iterations") or 2)

    # Generate initial script
    if manual_override_script and raw_script:
        return ScriptOutput(full=raw_script, short=raw_script, score=None)

    if mode == "manual" and raw_script:
        initial_script = raw_script
    elif mode == "topic_guided" and topic:
        prompt = TOPIC_GUIDED_PROMPT.format(topic=topic)
        if series_context:
            prompt += f"\n\nSeries context (previous episodes):\n{series_context}"
        initial_script = await client.generate(prompt)
    else:
        prompt = FULL_AI_PROMPT
        if series_context:
            prompt += f"\n\nSeries context (previous episodes):\n{series_context}"
        initial_script = await client.generate(prompt)

    # Reviewer→Modifier loop
    current_script = initial_script
    iteration = 0

    while True:
        reviewer_prompt = REVIEWER_PROMPT.format(script=current_script)
        reviewer_result = await client.generate(reviewer_prompt, response_schema=REVIEWER_SCHEMA)

        score = reviewer_result["score"]
        user_summary = reviewer_result["user_summary"]

        if score >= approval_threshold:
            break

        if iteration >= max_iterations:
            raise HumanInTheLoopPause(current_script, score, user_summary)

        rewrite_directives = "\n".join(
            f"- {d}" for d in reviewer_result["rewrite_directives"]
        )
        modifier_prompt = MODIFIER_PROMPT.format(
            script=current_script,
            score=score,
            user_summary=user_summary,
            rewrite_directives=rewrite_directives,
        )
        current_script = await client.generate(modifier_prompt)
        iteration += 1

    # Tighten to short variant
    tightener_prompt = TIGHTENER_PROMPT.format(script=current_script)
    short_script = await client.generate(tightener_prompt)

    return ScriptOutput(full=current_script, short=short_script, score=score)
