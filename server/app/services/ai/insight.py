"""Monthly-insight narration (ROADMAP #18) — the "what changed" note, under the §6 guardrail.

Same contract as `categorize.py`: the model sees DB-*derived aggregates only (category deltas,
budget verdicts, top merchants — never a raw transaction row and never an email), the output is
Pydantic-validated, and it is descriptive finance, never advice. A narrative that fails to parse
or comes back with the model unreachable yields None — the deterministic aggregates stand on
their own, and the note is the optional prose on top (insights may slip; category drafts may not).
"""

import json

from pydantic import BaseModel

from app.services.ai.categorize import _extract_json_object
from app.services.ai.llm_client import LlmClient


class InsightNarrative(BaseModel):
    headline: str
    summary: str


def build_insight_prompt(payload: dict) -> str:
    """`payload` is the deterministic aggregate (see `insight_service`), serialized. The model's
    only job is to turn these numbers into two or three plain sentences — it must not invent a
    figure, and it must stay descriptive (no advice, no moralising, no product suggestions)."""
    return (
        "You are writing a short factual note about a household's spending for the household "
        "itself, from the month's aggregate figures below.\n\n"
        "Rules:\n"
        "- Use ONLY the figures given. Never invent a number.\n"
        "- Be descriptive, not advisory. No investment, tax, or budgeting advice; no telling them "
        "to cut back.\n"
        "- Note the biggest changes from their usual, and any budget that was exceeded.\n"
        '- "Other" is a catch-all where no better category exists.\n\n'
        f"Figures (JSON):\n{json.dumps(payload, indent=1, default=str)}\n\n"
        'Respond with only JSON: {"headline": "<=8 words", "summary": "2-3 sentences"}.'
    )


async def narrate_month(client: LlmClient, payload: dict) -> InsightNarrative | None:
    """Best-effort narrative. Any failure — unreachable model, HTTP error, unparseable or
    oddly-shaped reply — yields None rather than raising into the caller (the insight endpoint
    and the digest sweep both treat prose as optional, per §6)."""
    try:
        raw = await client.complete(build_insight_prompt(payload))
        return InsightNarrative.model_validate_json(_extract_json_object(raw))
    except Exception:  # noqa: BLE001 — descriptive prose is strictly best-effort
        return None
