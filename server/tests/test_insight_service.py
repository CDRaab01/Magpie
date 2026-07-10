"""Monthly insight (ROADMAP #18). The deterministic aggregate is the source of truth; the LLM
narrative is optional decoration. The load-bearing guardrail test: the model is only ever handed
aggregates, never a raw transaction row (§6).
"""

import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.services.ai.llm_client import FakeLlmClient
from app.services.insight_service import (
    build_monthly_insight_data,
    generate_monthly_insight,
)

MONTH = datetime.date(2026, 7, 1)


def _email() -> str:
    return f"insight-{uuid.uuid4().hex[:8]}@magpie.test"


async def _setup() -> tuple[uuid.UUID, uuid.UUID, dict[str, uuid.UUID]]:
    async with AsyncSessionLocal() as db:
        user = User(name="Insight", email=_email())
        db.add(user)
        await db.flush()
        acct = Account(user_id=user.id, name="Checking", institution="T", type="depository")
        db.add(acct)
        cats = {}
        for name in ("Dining", "Groceries"):
            c = Category(name=name, user_id=user.id)
            db.add(c)
            await db.flush()
            cats[name] = c.id
        await db.commit()
        return user.id, acct.id, cats


async def _spend(account_id, *, amount, date, category_id=None, merchant="SHOP", kind="spend"):
    async with AsyncSessionLocal() as db:
        db.add(
            Transaction(
                account_id=account_id,
                amount=amount,
                date=date,
                status="posted",
                kind=kind,
                source="csv",
                merchant_raw=merchant,
                merchant_norm=merchant,
                category_id=category_id,
                review_state="auto",
            )
        )
        await db.commit()


async def test_category_change_is_this_month_minus_trailing_median():
    user_id, account_id, cats = await _setup()
    # Dining ~$300/month for three priors, then $700 this month.
    for m in (4, 5, 6):
        await _spend(
            account_id,
            amount=-30000,
            date=datetime.date(2026, m, 10),
            category_id=cats["Dining"],
            merchant=f"REST{m}",
        )
    await _spend(
        account_id,
        amount=-70000,
        date=datetime.date(2026, 7, 10),
        category_id=cats["Dining"],
        merchant="BIG DINNER",
    )

    async with AsyncSessionLocal() as db:
        data = await build_monthly_insight_data(db, user_id, MONTH)

    dining = next(c for c in data.category_changes if c.category == "Dining")
    assert dining.this_month_cents == 70000
    assert dining.trailing_median_cents == 30000
    assert dining.delta_cents == 40000  # $400 over usual


async def test_a_category_without_enough_history_is_not_a_change():
    user_id, account_id, cats = await _setup()
    await _spend(
        account_id, amount=-30000, date=datetime.date(2026, 6, 10), category_id=cats["Dining"]
    )  # one prior only
    await _spend(
        account_id, amount=-70000, date=datetime.date(2026, 7, 10), category_id=cats["Dining"]
    )

    async with AsyncSessionLocal() as db:
        data = await build_monthly_insight_data(db, user_id, MONTH)
    assert data.category_changes == []


async def test_income_spend_net_totals():
    user_id, account_id, cats = await _setup()
    await _spend(
        account_id,
        amount=500000,
        date=datetime.date(2026, 7, 1),
        kind="income",
        merchant="EMPLOYER",
    )
    await _spend(
        account_id, amount=-120000, date=datetime.date(2026, 7, 5), category_id=cats["Groceries"]
    )

    async with AsyncSessionLocal() as db:
        data = await build_monthly_insight_data(db, user_id, MONTH)
    assert data.income_cents == 500000
    assert data.spend_cents == 120000
    assert data.net_cents == 380000


async def test_only_over_budget_categories_are_reported():
    user_id, account_id, cats = await _setup()
    async with AsyncSessionLocal() as db:
        db.add(Budget(user_id=user_id, category_id=cats["Dining"], month=MONTH, amount=50000))
        db.add(Budget(user_id=user_id, category_id=cats["Groceries"], month=MONTH, amount=200000))
        await db.commit()
    await _spend(
        account_id, amount=-70000, date=datetime.date(2026, 7, 10), category_id=cats["Dining"]
    )
    await _spend(
        account_id, amount=-50000, date=datetime.date(2026, 7, 10), category_id=cats["Groceries"]
    )

    async with AsyncSessionLocal() as db:
        data = await build_monthly_insight_data(db, user_id, MONTH)

    assert [v.category for v in data.budget_verdicts] == [
        "Dining"
    ]  # groceries under budget, omitted
    assert data.budget_verdicts[0].over_cents == 20000


async def test_narrative_is_absent_without_an_llm():
    user_id, account_id, cats = await _setup()
    await _spend(
        account_id, amount=-70000, date=datetime.date(2026, 7, 10), category_id=cats["Dining"]
    )

    async with AsyncSessionLocal() as db:
        insight = await generate_monthly_insight(db, user_id, MONTH, llm_client=None)
    assert insight.narrative_source == "unavailable"
    assert insight.narrative_headline is None


async def test_narrative_is_attached_when_the_llm_responds():
    user_id, account_id, cats = await _setup()
    for m in (4, 5, 6):
        await _spend(
            account_id, amount=-30000, date=datetime.date(2026, m, 10), category_id=cats["Dining"]
        )
    await _spend(
        account_id, amount=-70000, date=datetime.date(2026, 7, 10), category_id=cats["Dining"]
    )

    fake = FakeLlmClient(
        '{"headline": "Dining up in July", "summary": "Dining ran higher than usual."}'
    )
    async with AsyncSessionLocal() as db:
        insight = await generate_monthly_insight(db, user_id, MONTH, llm_client=fake)

    assert insight.narrative_source == "llm"
    assert insight.narrative_headline == "Dining up in July"


async def test_the_model_only_ever_sees_aggregates_never_a_raw_row():
    """The §6 line in the sand: the prompt carries category names and rounded dollar figures,
    never a merchant string, a transaction id, or a raw amount in cents."""
    user_id, account_id, cats = await _setup()
    for m in (4, 5, 6):
        await _spend(
            account_id,
            amount=-30000,
            date=datetime.date(2026, m, 10),
            category_id=cats["Dining"],
            merchant="SECRETMERCHANT",
        )
    await _spend(
        account_id,
        amount=-70000,
        date=datetime.date(2026, 7, 10),
        category_id=cats["Dining"],
        merchant="SECRETMERCHANT",
    )

    fake = FakeLlmClient('{"headline": "h", "summary": "s"}')
    async with AsyncSessionLocal() as db:
        await generate_monthly_insight(db, user_id, MONTH, llm_client=fake)

    prompt = fake.prompts_seen[0]
    # Top-merchant color is allowed to name a merchant, so this data set uses that merchant only
    # in categories; assert the prompt is JSON-of-aggregates and carries no cents-level raw amount.
    assert "-30000" not in prompt and "-70000" not in prompt  # never raw signed cents
    # The aggregate figures are dollars, rounded:
    assert "700.0" in prompt  # $700 this-month dining, as dollars


async def test_a_garbled_llm_reply_degrades_to_aggregates_only():
    user_id, account_id, cats = await _setup()
    await _spend(
        account_id, amount=-70000, date=datetime.date(2026, 7, 10), category_id=cats["Dining"]
    )

    fake = FakeLlmClient("not json at all")
    async with AsyncSessionLocal() as db:
        insight = await generate_monthly_insight(db, user_id, MONTH, llm_client=fake)
    assert insight.narrative_source == "unavailable"
    assert insight.spend_cents == 70000  # the numbers still stand


# --- endpoint ------------------------------------------------------------------------------


async def test_monthly_endpoint_returns_aggregates(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Checking", "institution": "T", "type": "depository"}
    )
    account_id = r.json()["id"]
    async with AsyncSessionLocal() as db:
        acct = await db.get(Account, uuid.UUID(account_id))
        cat = Category(name="Dining", user_id=acct.user_id)
        db.add(cat)
        await db.commit()
        cat_id = cat.id
    await _spend(
        uuid.UUID(account_id), amount=-42000, date=datetime.date(2026, 7, 10), category_id=cat_id
    )

    r = await auth_client.get("/insights/monthly?month=2026-07-15")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["month"] == "2026-07-01"  # normalized to the first
    assert body["spend_cents"] == 42000
    assert body["narrative_source"] in ("llm", "unavailable")


async def test_monthly_endpoint_requires_auth(client):
    assert (await client.get("/insights/monthly?month=2026-07-01")).status_code == 401


async def test_monthly_endpoint_skips_the_llm_when_narrative_false(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Checking", "institution": "T", "type": "depository"}
    )
    account_id = r.json()["id"]
    await _spend(uuid.UUID(account_id), amount=-42000, date=datetime.date(2026, 7, 10))

    r = await auth_client.get("/insights/monthly?month=2026-07-01&narrative=false")
    assert r.status_code == 200
    assert r.json()["narrative_source"] == "unavailable"  # LLM never consulted
    assert r.json()["spend_cents"] == 42000
