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


# --- F13 guards, through the real service + DB --------------------------------------------


async def _add_txn(account_id: uuid.UUID, amount: int, day: int, kind: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        txn = Transaction(
            account_id=account_id,
            amount=amount,
            date=datetime.date(2026, 7, day),
            status="posted",
            kind=kind,
            source="csv",
        )
        db.add(txn)
        await db.commit()
        return txn.id


def _bill(account_id: uuid.UUID, amount_due: int, biller: str = "XCEL") -> BillStatementCreate:
    return BillStatementCreate(
        biller=biller,
        account_id=account_id,
        amount_due=amount_due,
        due_date=datetime.date(2026, 7, 15),
    )


async def test_a_same_magnitude_deposit_does_not_pay_the_bill():
    """The F13 bug in situ: a $150 paycheck landing near a $150 bill's due date used to mark it
    paid, silencing the missing-bill alert."""
    user_id, account_id = await _make_user_with_account()
    await _add_txn(account_id, 15000, 15, "income")

    async with AsyncSessionLocal() as db:
        bill = await create_bill(db, user_id, _bill(account_id, 15000), now=NOW)
    assert bill.matched_transaction_id is None


async def test_a_real_outflow_still_pays_the_bill():
    user_id, account_id = await _make_user_with_account()
    payment_id = await _add_txn(account_id, -15000, 16, "spend")

    async with AsyncSessionLocal() as db:
        bill = await create_bill(db, user_id, _bill(account_id, 15000), now=NOW)
    assert bill.matched_transaction_id == payment_id


async def test_two_same_amount_bills_do_not_both_claim_one_payment():
    user_id, account_id = await _make_user_with_account()
    payment_id = await _add_txn(account_id, -4500, 15, "spend")

    async with AsyncSessionLocal() as db:
        first = await create_bill(db, user_id, _bill(account_id, 4500, "XCEL"), now=NOW)
    async with AsyncSessionLocal() as db:
        second = await create_bill(db, user_id, _bill(account_id, 4500, "WATER"), now=NOW)

    assert first.matched_transaction_id == payment_id
    # The second bill finds the payment already claimed and stays unmatched — so it can still
    # page as "missing" rather than looking quietly settled.
    assert second.matched_transaction_id is None


async def test_rematch_will_not_steal_a_payment_another_bill_already_claimed():
    user_id, account_id = await _make_user_with_account()
    await _add_txn(account_id, -4500, 15, "spend")

    async with AsyncSessionLocal() as db:
        await create_bill(db, user_id, _bill(account_id, 4500, "XCEL"), now=NOW)
    async with AsyncSessionLocal() as db:
        second = await create_bill(db, user_id, _bill(account_id, 4500, "WATER"), now=NOW)
    async with AsyncSessionLocal() as db:
        rematched = await rematch_bill(db, user_id, second.id)

    assert rematched.matched_transaction_id is None


async def test_the_database_itself_refuses_two_bills_on_one_transaction():
    """The durable backstop behind the service-level filter: even a caller that bypasses
    `_find_payment` cannot violate one-bill-per-transaction (partial unique index, F13)."""
    import sqlalchemy.exc

    from app.models.bill_statement import BillStatement

    user_id, account_id = await _make_user_with_account()
    payment_id = await _add_txn(account_id, -4500, 15, "spend")

    async with AsyncSessionLocal() as db:
        db.add(
            BillStatement(
                biller="XCEL",
                account_id=account_id,
                amount_due=4500,
                due_date=datetime.date(2026, 7, 15),
                issued_at=NOW,
                matched_transaction_id=payment_id,
            )
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        db.add(
            BillStatement(
                biller="WATER",
                account_id=account_id,
                amount_due=4500,
                due_date=datetime.date(2026, 7, 15),
                issued_at=NOW,
                matched_transaction_id=payment_id,  # same payment — must be rejected
            )
        )
        try:
            await db.commit()
        except sqlalchemy.exc.IntegrityError:
            pass
        else:
            raise AssertionError("the partial unique index did not reject the duplicate claim")


async def test_many_unmatched_bills_coexist_despite_the_unique_index():
    """The index is partial for a reason: NULL matched_transaction_id is the normal state."""
    user_id, account_id = await _make_user_with_account()
    async with AsyncSessionLocal() as db:
        for biller in ("XCEL", "WATER", "GAS"):
            await create_bill(db, user_id, _bill(account_id, 4500, biller), now=NOW)

    async with AsyncSessionLocal() as db:
        from sqlalchemy import func, select

        from app.models.bill_statement import BillStatement

        n = await db.scalar(
            select(func.count())
            .select_from(BillStatement)
            .where(BillStatement.account_id == account_id)
        )
    assert n == 3
