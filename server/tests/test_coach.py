"""AI budget coach endpoints + service (Stage 1): goal CRUD, full-table status, per-category
analysis, savings plan, PATCH /budgets, carry-forward proposals."""

import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.rule import Rule
from app.models.transaction import Transaction

TODAY = datetime.date.today()
THIS_MONTH = TODAY.replace(day=1)


async def _account(auth_client) -> str:
    r = await auth_client.post(
        "/accounts", json={"name": "Checking", "institution": "US Bank", "type": "depository"}
    )
    return r.json()["id"]


async def _category(auth_client, name) -> str:
    return (await auth_client.post("/categories", json={"name": name})).json()["id"]


async def _spend(account_id, category_id, date, cents, merchant="SHOP"):
    """One spend transaction (cents positive magnitude -> stored negative)."""
    async with AsyncSessionLocal() as db:
        db.add(
            Transaction(
                account_id=uuid.UUID(account_id),
                amount=-cents,
                date=date,
                status="posted",
                kind="spend",
                source="csv",
                merchant_raw=merchant,
                merchant_norm=merchant,
                category_id=uuid.UUID(category_id) if category_id else None,
            )
        )
        await db.commit()


async def _income(account_id, date, cents):
    async with AsyncSessionLocal() as db:
        db.add(
            Transaction(
                account_id=uuid.UUID(account_id),
                amount=cents,
                date=date,
                status="posted",
                kind="income",
                source="csv",
                merchant_raw="EMPLOYER",
                merchant_norm="EMPLOYER",
            )
        )
        await db.commit()


def _months_ago(n: int) -> datetime.date:
    total = THIS_MONTH.year * 12 + (THIS_MONTH.month - 1) - n
    return datetime.date(total // 12, total % 12 + 1, 15)


# --- goal CRUD ------------------------------------------------------------------------------


async def test_goal_crud_round_trip(auth_client):
    assert (await auth_client.get("/coach/goal")).json() is None

    r = await auth_client.put("/coach/goal", json={"amount_cents": 50000})
    assert r.status_code == 200
    assert r.json()["amount_cents"] == 50000

    # Upsert: setting again updates in place, no second active goal.
    r = await auth_client.put("/coach/goal", json={"amount_cents": 75000})
    assert r.json()["amount_cents"] == 75000
    assert (await auth_client.get("/coach/goal")).json()["amount_cents"] == 75000

    assert (await auth_client.delete("/coach/goal")).status_code == 204
    assert (await auth_client.get("/coach/goal")).json() is None


async def test_goal_rejects_nonpositive(auth_client):
    assert (await auth_client.put("/coach/goal", json={"amount_cents": 0})).status_code == 422


# --- status ---------------------------------------------------------------------------------


async def test_status_covers_every_budgeted_category_with_median_context(auth_client):
    acct = await _account(auth_client)
    dining = await _category(auth_client, "Dining")
    fun = await _category(auth_client, "Fun")
    # 3 prior months of history for dining ($200/mo), this month $50.
    for n in (1, 2, 3):
        await _spend(acct, dining, _months_ago(n), 20000)
    await _spend(acct, dining, THIS_MONTH, 5000)
    for cat, amount in ((dining, 25000), (fun, 10000)):
        await auth_client.post(
            "/budgets", json={"category_id": cat, "month": str(THIS_MONTH), "amount": amount}
        )

    body = (await auth_client.get("/coach/status")).json()
    assert body["days_in_month"] >= 28
    assert len(body["budgets"]) == 2  # the FULL table — both categories, even the zero-spend one
    by_name = {b["category_name"]: b for b in body["budgets"]}
    assert by_name["Dining"]["spent_cents"] == 5000
    assert by_name["Dining"]["trailing_median_cents"] == 20000
    assert by_name["Fun"]["spent_cents"] == 0
    assert body["narrative_source"] == "unavailable"
    assert body["uncategorized_mtd_cents"] == 0


async def test_status_projects_net_and_goal_delta(auth_client):
    acct = await _account(auth_client)
    # 3 prior months: $4000 income, $3000 spend -> baseline net $1000.
    cat = await _category(auth_client, "Stuff")
    for n in (1, 2, 3):
        await _income(acct, _months_ago(n), 400000)
        await _spend(acct, cat, _months_ago(n), 300000)
    await auth_client.put("/coach/goal", json={"amount_cents": 50000})

    body = (await auth_client.get("/coach/status")).json()
    net = body["net"]
    assert net["projected_income_cents"] == 400000  # median (no MTD income seeded)
    assert net["goal_delta_cents"] == net["projected_net_cents"] - 50000
    assert body["goal"]["amount_cents"] == 50000


async def test_status_surfaces_uncategorized_blind_spot(auth_client):
    acct = await _account(auth_client)
    await _spend(acct, None, THIS_MONTH, 14000)  # spend with no category
    body = (await auth_client.get("/coach/status")).json()
    assert body["uncategorized_mtd_cents"] == 14000


# --- per-category analysis ------------------------------------------------------------------


async def test_category_analysis_budgeted(auth_client):
    acct = await _account(auth_client)
    dining = await _category(auth_client, "Dining")
    for n in (1, 2, 3):
        await _spend(acct, dining, _months_ago(n), 20000, merchant="DOORDASH")
    await _spend(acct, dining, THIS_MONTH, 9000, merchant="DOORDASH")
    await auth_client.post(
        "/budgets", json={"category_id": dining, "month": str(THIS_MONTH), "amount": 15000}
    )

    body = (await auth_client.get(f"/coach/category/{dining}")).json()
    assert body["category_name"] == "Dining"
    assert body["budget_cents"] == 15000
    assert body["spent_cents"] == 9000
    assert body["trailing_median_cents"] == 20000
    assert len(body["monthly_history"]) == 3
    assert body["top_merchants"][0]["merchant"] == "DOORDASH"
    assert body["pace"] is not None


async def test_category_analysis_unbudgeted_still_works(auth_client):
    acct = await _account(auth_client)
    gas = await _category(auth_client, "Gas")
    await _spend(acct, gas, _months_ago(1), 8000)
    body = (await auth_client.get(f"/coach/category/{gas}")).json()
    assert body["budget_cents"] is None and body["pace"] is None
    assert body["trailing_median_cents"] == 8000


async def test_category_analysis_not_yours_404s(auth_client):
    assert (await auth_client.get(f"/coach/category/{uuid.uuid4()}")).status_code == 404


# --- savings plan ---------------------------------------------------------------------------


async def test_plan_defaults_to_goal_and_400s_without_one(auth_client):
    assert (await auth_client.get("/coach/plan")).status_code == 400

    acct = await _account(auth_client)
    cat = await _category(auth_client, "Fun")
    for n in (1, 2, 3):
        await _income(acct, _months_ago(n), 100000)
        await _spend(acct, cat, _months_ago(n), 80000)
    await auth_client.put("/coach/goal", json={"amount_cents": 40000})

    body = (await auth_client.get("/coach/plan")).json()
    assert body["target_cents"] == 40000
    assert body["baseline_net_cents"] == 20000  # 1000 - 800
    assert body["needed_cents"] == 20000
    assert body["cuts"], "expected at least one cut proposal"
    assert body["cuts"][0]["category_name"] == "Fun"


async def test_plan_excludes_bill_dominated_category(auth_client):
    acct = await _account(auth_client)
    housing = await _category(auth_client, "Housing")
    fun = await _category(auth_client, "Fun")
    for n in (1, 2, 3):
        await _income(acct, _months_ago(n), 300000)
        await _spend(acct, housing, _months_ago(n), 150000, merchant="ROCKET MORTGAGE")
        await _spend(acct, fun, _months_ago(n), 50000, merchant="STEAM")
    # An enabled recurring_bill rule matching the housing merchant -> bill-share marks it fixed.
    async with AsyncSessionLocal() as db:
        acct_row = await db.get(Account, uuid.UUID(acct))
        db.add(
            Rule(
                user_id=acct_row.user_id,
                type="recurring_bill",
                account_id=acct_row.id,
                matcher="ROCKET MORTGAGE",
                cadence={"kind": "monthly"},
                enabled=True,
            )
        )
        await db.commit()

    body = (await auth_client.get("/coach/plan", params={"monthly_savings_cents": 200000})).json()
    assert all(c["category_name"] != "Housing" for c in body["cuts"])
    assert body["shortfall_cents"] > 0  # honest: fun alone can't fund $2000/mo


async def test_plan_already_on_target_has_no_cuts(auth_client):
    acct = await _account(auth_client)
    cat = await _category(auth_client, "Fun")
    for n in (1, 2, 3):
        await _income(acct, _months_ago(n), 500000)
        await _spend(acct, cat, _months_ago(n), 100000)
    body = (await auth_client.get("/coach/plan", params={"monthly_savings_cents": 100000})).json()
    assert body["needed_cents"] <= 0 and body["cuts"] == []


# --- PATCH /budgets + carry-forward ---------------------------------------------------------


async def test_patch_budget_changes_the_cap(auth_client):
    cat = await _category(auth_client, "Dining")
    created = (
        await auth_client.post(
            "/budgets", json={"category_id": cat, "month": str(THIS_MONTH), "amount": 15000}
        )
    ).json()
    r = await auth_client.patch(f"/budgets/{created['id']}", json={"amount": 9000})
    assert r.status_code == 200 and r.json()["amount"] == 9000


async def test_patch_someone_elses_budget_404s(
    client, auth_client, suite_enabled, make_suite_token
):
    cat = await _category(auth_client, "Dining")
    created = (
        await auth_client.post(
            "/budgets", json={"category_id": cat, "month": str(THIS_MONTH), "amount": 15000}
        )
    ).json()
    other = await client.post(
        "/auth/suite", json={"suite_token": make_suite_token("other-coach@example.com")}
    )
    client.headers["Authorization"] = f"Bearer {other.json()['access_token']}"
    assert (await client.patch(f"/budgets/{created['id']}", json={"amount": 1})).status_code == 404


async def test_new_month_carries_last_months_budgets_forward(auth_client):
    cat = await _category(auth_client, "Dining")
    prev = (THIS_MONTH - datetime.timedelta(days=1)).replace(day=1)
    await auth_client.post(
        "/budgets", json={"category_id": cat, "month": str(prev), "amount": 22000}
    )
    # This month has no budgets -> proposals are last month's plan, at prior amounts.
    body = (await auth_client.get("/budgets/proposals", params={"month": str(THIS_MONTH)})).json()
    assert body and body[0]["suggested_amount_cents"] == 22000
    # Once a budget exists this month, carry-forward stands down (median proposals resume).
    await auth_client.post(
        "/budgets", json={"category_id": cat, "month": str(THIS_MONTH), "amount": 20000}
    )
    body = (await auth_client.get("/budgets/proposals", params={"month": str(THIS_MONTH)})).json()
    assert all(p["category_id"] != cat for p in body)
