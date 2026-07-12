"""Magpie's cross-app summary PROVIDER (federated awareness Link D): RS256-only auth (no SSO-audience
replay), income/spend/net + grocery aggregation, and the range cap."""

import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User

TODAY = datetime.date.today()
START = (TODAY - datetime.timedelta(days=13)).isoformat()
END = TODAY.isoformat()


async def _seed(email: str):
    async with AsyncSessionLocal() as db:
        user = User(name="Owner", email=email)
        db.add(user)
        await db.flush()
        acct = Account(user_id=user.id, name="Checking", institution="T", type="depository")
        groceries = Category(user_id=user.id, name="Groceries")
        db.add_all([acct, groceries])
        await db.flush()

        def txn(cents, kind, cat=None, days=1):
            return Transaction(
                account_id=acct.id,
                amount=cents,
                date=TODAY - datetime.timedelta(days=days),
                status="posted",
                kind=kind,
                source="csv",
                merchant_raw="X",
                merchant_norm="X",
                category_id=cat.id if cat else None,
            )

        db.add_all(
            [
                txn(500000, "income"),  # $5000 in
                txn(-30000, "spend", groceries),  # $300 groceries
                txn(-20000, "spend"),  # $200 other spend
                txn(-99999, "transfer"),  # excluded (internal movement)
            ]
        )
        await db.commit()
        return user.id


async def test_summary_requires_cross_app_token(client, suite_enabled):
    resp = await client.get("/cross-app/summary", params={"start": START, "end": END})
    assert resp.status_code == 401


async def test_summary_rejects_suite_audience(client, suite_enabled, make_suite_token):
    email = f"owner_{uuid.uuid4().hex[:8]}@magpie.test"
    await _seed(email)
    # A normal SSO token (aud="suite") must not work on the cross-app surface.
    resp = await client.get(
        "/cross-app/summary",
        params={"start": START, "end": END},
        headers={"Authorization": f"Bearer {make_suite_token(email, aud='suite')}"},
    )
    assert resp.status_code == 401


async def test_summary_aggregates_income_spend_grocery(client, suite_enabled, make_suite_token):
    email = f"owner_{uuid.uuid4().hex[:8]}@magpie.test"
    await _seed(email)
    resp = await client.get(
        "/cross-app/summary",
        params={"start": START, "end": END},
        headers={"Authorization": f"Bearer {make_suite_token(email, aud='cross-app')}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["income"] == 5000
    assert body["spend"] == 500  # 300 groceries + 200 other; transfer excluded
    assert body["grocery_spend"] == 300
    assert body["net"] == 4500
    assert body["savings_goal"] is None  # no goal set


async def test_summary_includes_goal_when_set(client, suite_enabled, make_suite_token):
    email = f"owner_{uuid.uuid4().hex[:8]}@magpie.test"
    user_id = await _seed(email)
    from app.models.goal import Goal

    async with AsyncSessionLocal() as db:
        db.add(Goal(user_id=user_id, kind="monthly_savings", amount_cents=50000, active=True))
        await db.commit()
    resp = await client.get(
        "/cross-app/summary",
        params={"start": START, "end": END},
        headers={"Authorization": f"Bearer {make_suite_token(email, aud='cross-app')}"},
    )
    assert resp.json()["savings_goal"] == {"monthly_target": 500}


async def test_summary_range_cap(client, suite_enabled, make_suite_token):
    email = f"owner_{uuid.uuid4().hex[:8]}@magpie.test"
    await _seed(email)
    resp = await client.get(
        "/cross-app/summary",
        params={"start": (TODAY - datetime.timedelta(days=100)).isoformat(), "end": END},
        headers={"Authorization": f"Bearer {make_suite_token(email, aud='cross-app')}"},
    )
    assert resp.status_code == 422
