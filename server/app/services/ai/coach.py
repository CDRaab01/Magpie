"""Budget-coach narration (owner-requested 2026-07-11) — the one AI surface allowed to be
prescriptive, under the §6 amendment.

Scope of the allowance, exactly: the model may coach the household about its OWN spending
measured against its OWN budgets and stated savings goal ("dining is on pace for $180 against
your $150 budget — tailor it back"), grounded strictly in the aggregates handed to it. Investment,
tax, and legal advice remain banned; product recommendations remain banned; and nothing the model
says changes a budget — every change is a draft the owner confirms in the app (§1 unchanged).

Same mechanical contract as `insight.py`: DB-derived aggregates in, Pydantic-validated JSON out,
any failure yields None and the deterministic figures stand on their own.
"""

import json

from pydantic import BaseModel

from app.services.ai.categorize import _extract_json_object
from app.services.ai.llm_client import LlmClient


class CoachNarrative(BaseModel):
    headline: str  # <= 10 words
    coaching: str  # 2-3 sentences; prescriptive about the owner's own budgets/goal is allowed


def build_coach_prompt(payload: dict) -> str:
    """`payload` is the deterministic coach aggregate (full budget table / plan / one category —
    see `coach_service`). The model's job is to phrase where the month stands and what would bring
    it back on plan; it never computes and never invents a figure."""
    return (
        "You are Magpie's budget coach, speaking to the household about its OWN budgets and "
        "savings goal, from the figures below.\n\n"
        "Rules:\n"
        "- Use ONLY the figures given. Never invent a number.\n"
        "- You MAY give practical budget coaching: say which categories are over pace against "
        "their own budgets and by how much, and what daily spend would bring them back on "
        "budget — e.g. 'Dining is on pace for $180 against $150; tailor it back.'\n"
        "- Never give investment, tax, or legal advice; never recommend financial products.\n"
        "- Any budget change you mention is a suggestion the owner confirms in the app — phrase "
        "it as an option, not a done deal.\n"
        "- If `uncategorized_mtd` is meaningful, note that some spend is uncategorized and the "
        "picture sharpens once it's reviewed.\n\n"
        f"Figures (JSON):\n{json.dumps(payload, indent=1, default=str)}\n\n"
        'Respond with only JSON: {"headline": "<=10 words", "coaching": "2-3 sentences"}.'
    )


async def narrate_coach(client: LlmClient, payload: dict) -> CoachNarrative | None:
    """Best-effort coaching prose. Any failure — unreachable model, HTTP error, unparseable or
    oddly-shaped reply — yields None; the deterministic pace/plan figures carry the surface."""
    try:
        raw = await client.complete(build_coach_prompt(payload))
        return CoachNarrative.model_validate_json(_extract_json_object(raw))
    except Exception:  # noqa: BLE001 — coaching prose is strictly best-effort
        return None
