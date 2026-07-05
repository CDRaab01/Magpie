import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.budget import BudgetCreate
from app.services.budget_service import actual_spend_by_category, create_budget


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
