import datetime
import uuid

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.bill_statement import BillStatement
from app.models.ingest_event import IngestEvent
from app.models.transaction import Transaction
from app.models.user import User
from app.services.ntfy_client import FakeNtfyPublisher
from app.services.sweep_service import run_missing_bill_sweep, run_unparsed_backlog_sweep

UTC = datetime.timezone.utc
# 2026-08-01 12:00 UTC is still 2026-08-01 in US-Central; owner-local "today" = 2026-08-01,
# so the missing-bill cutoff (today - 3d grace) is 2026-07-29.
NOW = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def _unique_email() -> str:
    return f"sweep-test-{uuid.uuid4().hex[:8]}@magpie.test"


async def _make_user() -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        user = User(name="Sweep Test", email=_unique_email())
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.id


async def _add_unparsed_event(user_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            IngestEvent(
                user_id=user_id,
                account_id=None,
                message_id=f"<{uuid.uuid4().hex}@test.invalid>",
                received_at=datetime.datetime.now(UTC),
                parser="unknown",
                parse_version="0",
                payload_hash=uuid.uuid4().hex,
                outcome="unparsed",
                raw_payload="irrelevant",
            )
        )
        await db.commit()


async def _make_account(user_id: uuid.UUID) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        acct = Account(
            user_id=user_id, name="Checking", institution="US Bank", type="depository", active=True
        )
        db.add(acct)
        await db.commit()
        await db.refresh(acct)
        return acct.id


async def _make_transaction(account_id) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        txn = Transaction(
            account_id=account_id,
            amount=-4500,
            currency="USD",
            date=datetime.date(2026, 7, 20),
            status="posted",
            kind="spend",
            review_state="confirmed",
            source="manual",
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)
        return txn.id


async def _make_bill(account_id, *, due_date, matched_txn_id=None, biller="XCEL ENERGY") -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            BillStatement(
                biller=biller,
                account_id=account_id,
                amount_due=4500,
                due_date=due_date,
                issued_at=datetime.datetime(2026, 7, 1, tzinfo=UTC),
                matched_transaction_id=matched_txn_id,
            )
        )
        await db.commit()


async def _sweep_unparsed(user_id, publisher, now=NOW) -> None:
    """Run the unparsed sweep AND commit the latch — the loop commits; tests must too, or the
    persisted latch (F11) rolls back when the session closes."""
    async with AsyncSessionLocal() as db:
        await run_unparsed_backlog_sweep(db, user_id, publisher, now=now)
        await db.commit()


async def _sweep_bills(user_id, publisher, now=NOW) -> None:
    async with AsyncSessionLocal() as db:
        await run_missing_bill_sweep(db, user_id, publisher, now=now)
        await db.commit()


# --- unparsed backlog ---------------------------------------------------------------------


async def test_no_backlog_publishes_nothing():
    user_id = await _make_user()
    publisher = FakeNtfyPublisher()
    await _sweep_unparsed(user_id, publisher)
    assert publisher.published == []


async def test_new_backlog_publishes_once():
    user_id = await _make_user()
    await _add_unparsed_event(user_id)
    publisher = FakeNtfyPublisher()
    await _sweep_unparsed(user_id, publisher)
    assert len(publisher.published) == 1
    assert "1 email" in publisher.published[0][0]


async def test_repeated_sweeps_stay_silent_while_backlog_persists():
    # F11: the latch is DATA, so even these fully independent sweep calls (each its own session,
    # no process memory carried) do not re-page while the backlog stays open.
    user_id = await _make_user()
    await _add_unparsed_event(user_id)
    publisher = FakeNtfyPublisher()
    await _sweep_unparsed(user_id, publisher)
    await _sweep_unparsed(user_id, publisher)
    await _sweep_unparsed(user_id, publisher)
    assert len(publisher.published) == 1  # still just the first alert


async def test_resolved_and_recurring_backlog_fires_a_new_alert():
    user_id = await _make_user()
    publisher = FakeNtfyPublisher()

    await _add_unparsed_event(user_id)
    await _sweep_unparsed(user_id, publisher)
    assert len(publisher.published) == 1  # episode 1

    # Resolve: delete the unparsed events; the sweep sees zero -> latch flips false, no new alert.
    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(IngestEvent).where(IngestEvent.user_id == user_id))
        for ev in rows.scalars().all():
            await db.delete(ev)
        await db.commit()
    await _sweep_unparsed(user_id, publisher)
    assert len(publisher.published) == 1  # resolving does not page

    # Episode 2: backlog recurs -> a fresh rising edge -> a new alert.
    await _add_unparsed_event(user_id)
    await _sweep_unparsed(user_id, publisher)
    assert len(publisher.published) == 2


# --- missing bill (CLAUDE.md Phase-6 exit: "a simulated missing bill pages the phone") -----


async def test_overdue_unmatched_bill_pages_once():
    user_id = await _make_user()
    account_id = await _make_account(user_id)
    await _make_bill(account_id, due_date=datetime.date(2026, 7, 20))  # well past the cutoff
    publisher = FakeNtfyPublisher()

    await _sweep_bills(user_id, publisher)
    assert len(publisher.published) == 1
    assert "XCEL ENERGY" in publisher.published[0][0]
    assert "$45.00" in publisher.published[0][0]

    await _sweep_bills(user_id, publisher)  # latched — no re-page
    assert len(publisher.published) == 1


async def test_matched_or_not_yet_due_bill_does_not_page():
    user_id = await _make_user()
    account_id = await _make_account(user_id)
    txn_id = await _make_transaction(account_id)
    await _make_bill(account_id, due_date=datetime.date(2026, 7, 20), matched_txn_id=txn_id)  # paid
    await _make_bill(
        account_id, due_date=datetime.date(2026, 7, 31), biller="OTHER"
    )  # within grace
    publisher = FakeNtfyPublisher()
    await _sweep_bills(user_id, publisher)
    assert publisher.published == []


async def test_bill_becomes_overdue_only_as_time_advances():
    user_id = await _make_user()
    account_id = await _make_account(user_id)
    await _make_bill(account_id, due_date=datetime.date(2026, 8, 1))  # due "today", within grace
    publisher = FakeNtfyPublisher()

    await _sweep_bills(user_id, publisher, now=NOW)
    assert publisher.published == []  # not yet past grace

    later = datetime.datetime(2026, 8, 10, 12, 0, tzinfo=UTC)  # cutoff now 2026-08-07 > due 08-01
    await _sweep_bills(user_id, publisher, now=later)
    assert len(publisher.published) == 1
