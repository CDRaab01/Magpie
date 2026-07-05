import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.bill import BillStatementCreate
from app.services.bill_service import create_bill, rematch_bill

NOW = datetime.datetime(2026, 7, 5, tzinfo=datetime.timezone.utc)


def _unique_email() -> str:
    return f"bill-test-{uuid.uuid4().hex[:8]}@magpie.test"


async def _make_user_with_account() -> tuple[uuid.UUID, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        user = User(name="Bill Test", email=_unique_email())
        db.add(user)
        await db.flush()
        account = Account(
            user_id=user.id, name="Checking", institution="Test Bank", type="depository"
        )
        db.add(account)
        await db.commit()
        return user.id, account.id


async def test_new_bill_with_no_payment_yet_is_unmatched():
    user_id, account_id = await _make_user_with_account()
    async with AsyncSessionLocal() as db:
        bill = await create_bill(
            db,
            user_id,
            BillStatementCreate(
                biller="XCEL",
                account_id=account_id,
                amount_due=4500,
                due_date=datetime.date(2026, 7, 15),
            ),
            now=NOW,
        )
    assert bill.matched_transaction_id is None


async def test_new_bill_matches_an_already_posted_payment():
    user_id, account_id = await _make_user_with_account()
    async with AsyncSessionLocal() as db:
        txn = Transaction(
            account_id=account_id,
            amount=-4500,
            date=datetime.date(2026, 7, 16),
            status="posted",
            kind="spend",
            review_state="confirmed",
            source="manual",
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)

    async with AsyncSessionLocal() as db:
        bill = await create_bill(
            db,
            user_id,
            BillStatementCreate(
                biller="XCEL",
                account_id=account_id,
                amount_due=4500,
                due_date=datetime.date(2026, 7, 15),
            ),
            now=NOW,
        )
    assert bill.matched_transaction_id == txn.id


async def test_rematch_finds_a_payment_that_arrived_later():
    user_id, account_id = await _make_user_with_account()
    async with AsyncSessionLocal() as db:
        bill = await create_bill(
            db,
            user_id,
            BillStatementCreate(
                biller="XCEL",
                account_id=account_id,
                amount_due=4500,
                due_date=datetime.date(2026, 7, 15),
            ),
            now=NOW,
        )
    assert bill.matched_transaction_id is None

    async with AsyncSessionLocal() as db:
        txn = Transaction(
            account_id=account_id,
            amount=-4500,
            date=datetime.date(2026, 7, 17),
            status="posted",
            kind="spend",
            review_state="confirmed",
            source="manual",
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)

    async with AsyncSessionLocal() as db:
        rematched = await rematch_bill(db, user_id, bill.id)
    assert rematched.matched_transaction_id == txn.id
