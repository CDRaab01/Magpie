import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.budget import BudgetCreate
from app.services.budget_service import (
    actual_spend_by_category,
    create_budget,
    list_budgets,
)


def _unique_email() -> str:
    return f"budget-test-{uuid.uuid4().hex[:8]}@magpie.test"


async def _make_user_account_category() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        user = User(name="Budget Test", email=_unique_email())
        db.add(user)
        await db.flush()
        account = Account(user_id=user.id, name="Amex", institution="Test Bank", type="card")
        category = Category(user_id=user.id, name="Groceries")
        db.add_all([account, category])
        await db.commit()
        return user.id, account.id, category.id


async def test_actual_spend_sums_the_months_transactions_for_that_category():
    user_id, account_id, category_id = await _make_user_account_category()
    async with AsyncSessionLocal() as db:
        db.add_all(
            [
                Transaction(
                    account_id=account_id,
                    amount=-4500,
                    date=datetime.date(2026, 7, 5),
                    status="posted",
                    category_id=category_id,
                    kind="spend",
                    review_state="confirmed",
                    source="manual",
                ),
                Transaction(
                    account_id=account_id,
                    amount=-2000,
                    date=datetime.date(2026, 7, 20),
                    status="posted",
                    category_id=category_id,
                    kind="spend",
                    review_state="confirmed",
                    source="manual",
                ),
                # Outside July - must not count.
                Transaction(
                    account_id=account_id,
                    amount=-9999,
                    date=datetime.date(2026, 6, 30),
                    status="posted",
                    category_id=category_id,
                    kind="spend",
                    review_state="confirmed",
                    source="manual",
                ),
            ]
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        actual = await actual_spend_by_category(db, user_id, datetime.date(2026, 7, 1))
    assert actual[category_id] == -6500


async def test_create_budget_and_read_actual_via_router_helper():
    user_id, account_id, category_id = await _make_user_account_category()
    async with AsyncSessionLocal() as db:
        budget = await create_budget(
            db,
            user_id,
            BudgetCreate(category_id=category_id, month=datetime.date(2026, 7, 1), amount=10000),
        )
    assert budget.category_id == category_id
    assert budget.amount == 10000


async def test_budgets_are_scoped_to_their_owner():
    # F10: before user_id scoping, list_budgets(month) returned every user's rows for the month.
    a_user, _, a_cat = await _make_user_account_category()
    b_user, _, b_cat = await _make_user_account_category()
    month = datetime.date(2026, 7, 1)
    async with AsyncSessionLocal() as db:
        await create_budget(db, a_user, BudgetCreate(category_id=a_cat, month=month, amount=10000))
        await create_budget(db, b_user, BudgetCreate(category_id=b_cat, month=month, amount=20000))

    async with AsyncSessionLocal() as db:
        a_budgets = await list_budgets(db, a_user, month)
        b_budgets = await list_budgets(db, b_user, month)
    assert [b.amount for b in a_budgets] == [10000]
    assert [b.amount for b in b_budgets] == [20000]  # A's budget is not visible to B


# --- auto-budget proposals (#20) ----------------------------------------------------------

import datetime as _dt  # noqa: E402

from app.services.budget_service import propose_budgets  # noqa: E402


async def _cat(user_id, name):
    async with AsyncSessionLocal() as db:
        c = Category(name=name, user_id=user_id)
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return c.id


async def _spend_row(account_id, amount, date, cat_id):
    async with AsyncSessionLocal() as db:
        db.add(
            Transaction(
                account_id=account_id,
                amount=amount,
                date=date,
                status="posted",
                kind="spend",
                source="csv",
                category_id=cat_id,
            )
        )
        await db.commit()


async def test_proposal_is_the_trailing_three_month_median():
    user_id, account_id, dining = await _make_user_account_category()
    # April $300, May $500, June $400 → median $400. July is the target month (excluded).
    await _spend_row(account_id, -30000, _dt.date(2026, 4, 10), dining)
    await _spend_row(account_id, -50000, _dt.date(2026, 5, 10), dining)
    await _spend_row(account_id, -40000, _dt.date(2026, 6, 10), dining)
    await _spend_row(account_id, -99999, _dt.date(2026, 7, 10), dining)  # target month, ignored

    async with AsyncSessionLocal() as db:
        proposals = await propose_budgets(db, user_id, _dt.date(2026, 7, 1))

    dining_prop = next(p for p in proposals if p[0] == dining)
    assert dining_prop[2] == 40000


async def test_a_category_with_a_budget_already_is_not_proposed():
    user_id, account_id, dining = await _make_user_account_category()
    await _spend_row(account_id, -30000, _dt.date(2026, 6, 10), dining)
    async with AsyncSessionLocal() as db:
        db.add(
            Budget(user_id=user_id, category_id=dining, month=_dt.date(2026, 7, 1), amount=50000)
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        proposals = await propose_budgets(db, user_id, _dt.date(2026, 7, 1))
    assert all(p[0] != dining for p in proposals)


async def test_endpoint_returns_proposals(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Chk", "institution": "T", "type": "depository"}
    )
    account_id = r.json()["id"]
    async with AsyncSessionLocal() as db:
        acct = await db.get(Account, uuid.UUID(account_id))
        cat = Category(name="Groceries", user_id=acct.user_id)
        db.add(cat)
        await db.commit()
        cat_id = cat.id
    await _spend_row(uuid.UUID(account_id), -20000, _dt.date(2026, 6, 5), cat_id)

    r = await auth_client.get("/budgets/proposals?month=2026-07-01")
    assert r.status_code == 200, r.text
    assert any(
        p["category_name"] == "Groceries" and p["suggested_amount_cents"] == 20000 for p in r.json()
    )
