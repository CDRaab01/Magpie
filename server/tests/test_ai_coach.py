"""Coach narration (Stage 3, §6 amendment): prompt scope, best-effort parsing, offline fallback,
and the chat context gaining the full budget table + goal."""

import datetime

from app.services.ai.coach import CoachNarrative, build_coach_prompt, narrate_coach
from app.services.ai.llm_client import FakeLlmClient

PAYLOAD = {
    "month": "2026-07-01",
    "day": "15 of 31",
    "budgets": [
        {
            "category": "Dining out",
            "budget": 150.0,
            "spent": 100.0,
            "projected": 180.0,
            "status": "over_pace",
            "usual_monthly_median": 140.0,
            "delta_vs_usual": 40.0,
        }
    ],
    "net": {"projected_net": 320.0},
    "savings_goal": {"monthly_target": 500.0, "projected_delta": -180.0},
    "uncategorized_mtd": 12.0,
}


async def test_valid_json_parses_to_narrative():
    client = FakeLlmClient(
        '{"headline": "Dining running hot", "coaching": "Dining is on pace for $180 against'
        ' $150. About $3.12/day keeps it on budget."}'
    )
    narrative = await narrate_coach(client, PAYLOAD)
    assert isinstance(narrative, CoachNarrative)
    assert "Dining" in narrative.coaching


async def test_garbage_reply_yields_none_not_a_raise():
    assert await narrate_coach(FakeLlmClient("I refuse to answer in JSON"), PAYLOAD) is None


async def test_model_exception_yields_none():
    class ExplodingClient:
        async def complete(self, prompt):
            raise TimeoutError("model busy")

    assert await narrate_coach(ExplodingClient(), PAYLOAD) is None


def test_prompt_carries_the_figures_and_the_guardrails():
    prompt = build_coach_prompt(PAYLOAD)
    # The figures the prose is allowed to use are embedded verbatim...
    assert "Dining out" in prompt and "180.0" in prompt
    # ...the coaching allowance is explicit and bounded...
    assert "MAY give practical budget coaching" in prompt
    assert "Never give investment, tax, or legal advice" in prompt
    # ...and every change is a draft the owner confirms.
    assert "the owner confirms in the app" in prompt
    assert "Never invent a number" in prompt


async def test_endpoint_narrative_unavailable_without_llm(auth_client):
    """With llm_base_url unset (the test env), narrative=true must degrade to the deterministic
    figures — never an error, never a fake narrative."""
    body = (await auth_client.get("/coach/status", params={"narrative": "true"})).json()
    assert body["narrative_source"] == "unavailable"
    assert body["narrative_headline"] is None


async def test_chat_context_carries_full_budget_table_and_goal(auth_client):
    """§6 amendment grounding: chat sees the same full per-category table the coach sees."""
    import uuid as _uuid

    from app.database import AsyncSessionLocal
    from app.models.account import Account
    from app.services.chat_service import build_ledger_context

    cat = (await auth_client.post("/categories", json={"name": "Dining"})).json()["id"]
    month = datetime.date.today().replace(day=1)
    await auth_client.post(
        "/budgets", json={"category_id": cat, "month": str(month), "amount": 15000}
    )
    await auth_client.put("/coach/goal", json={"amount_cents": 50000})
    acct = (
        await auth_client.post(
            "/accounts", json={"name": "Chk", "institution": "T", "type": "depository"}
        )
    ).json()["id"]

    async with AsyncSessionLocal() as db:
        acct_row = await db.get(Account, _uuid.UUID(acct))
        context = await build_ledger_context(
            db, acct_row.user_id, now=datetime.datetime.now(datetime.timezone.utc)
        )
    assert context["budgets_this_month"][0]["category"] == "Dining"
    assert context["budgets_this_month"][0]["budget"] == 150.0
    assert context["savings_goal"]["monthly_target"] == 500.0
    assert "uncategorized_mtd" in context and "net_projection" in context
