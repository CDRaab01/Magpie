"""Auth-hold expiry (CLAUDE.md §2, ROADMAP Wave 0 #5) — the first data-*mutation* sweep.

Every test here is a time-travel test: the sweep takes `now` as a dependency and never reaches
for a wall clock, which is exactly why "advance 40 days, assert the hold dropped" is expressible
at all (CLAUDE.md §9).
"""

import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.services.sweep_service import run_auth_hold_expiry_sweep

SWIPE = datetime.date(2026, 7, 1)
NOW = datetime.datetime(2026, 7, 2, 12, 0, tzinfo=datetime.timezone.utc)


def _days(n: int) -> datetime.datetime:
    return NOW + datetime.timedelta(days=n)


async def _account() -> tuple[uuid.UUID, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        user = User(name="Hold", email=f"hold-{uuid.uuid4().hex[:8]}@magpie.test")
        db.add(user)
        await db.flush()
        acct = Account(user_id=user.id, name="Card", institution="Amex", type="card")
        db.add(acct)
        await db.commit()
        return user.id, acct.id


async def _txn(
    account_id,
    *,
    amount=-100,
    status="pending",
    date=SWIPE,
    review="needs_review",
    group=None,
    merchant="GAS STATION",
):
    async with AsyncSessionLocal() as db:
        t = Transaction(
            account_id=account_id,
            amount=amount,
            date=date,
            status=status,
            kind="spend",
            source="email",
            merchant_raw=merchant,
            merchant_norm=merchant,
            review_state=review,
            transfer_group=group,
        )
        db.add(t)
        await db.commit()
        return t.id


async def _get(txn_id) -> Transaction:
    async with AsyncSessionLocal() as db:
        return await db.get(Transaction, txn_id)


async def _sweep(user_id, when, **kw) -> int:
    async with AsyncSessionLocal() as db:
        n = await run_auth_hold_expiry_sweep(db, user_id, now=when, **kw)
        await db.commit()
        return n


async def test_a_pre_auth_that_never_posts_expires_after_the_hold_window():
    """The canonical case: a $1 gas-station pre-auth that never settles."""
    user_id, account_id = await _account()
    hold = await _txn(account_id, amount=-100)

    assert await _sweep(user_id, _days(3)) == 0  # still inside the window
    assert (await _get(hold)).status == "pending"

    assert await _sweep(user_id, _days(40)) == 1  # advance the clock: it drops
    dropped = await _get(hold)
    assert dropped.status == "expired"
    assert dropped.review_state == "auto"
    assert "auth hold expired" in dropped.rule_note


async def test_the_hold_row_is_kept_not_deleted_so_the_drop_is_auditable():
    user_id, account_id = await _account()
    hold = await _txn(account_id)
    await _sweep(user_id, _days(40))
    assert await _get(hold) is not None


async def test_a_hold_that_actually_posted_is_never_expired():
    """Reconciliation owns this row, not the clock — same 'same swipe' tolerance the importer
    and the parser replay use."""
    user_id, account_id = await _account()
    hold = await _txn(account_id, amount=-4200)
    await _txn(account_id, amount=-4200, status="posted", date=SWIPE + datetime.timedelta(days=2))

    assert await _sweep(user_id, _days(40)) == 0
    assert (await _get(hold)).status == "pending"


async def test_a_settled_tip_still_counts_as_posted_and_blocks_expiry():
    """The restaurant case: alerted at the pre-tip amount, posted higher."""
    user_id, account_id = await _account()
    hold = await _txn(account_id, amount=-4200)
    await _txn(account_id, amount=-5000, status="posted", date=SWIPE + datetime.timedelta(days=1))

    assert await _sweep(user_id, _days(40)) == 0
    assert (await _get(hold)).status == "pending"


async def test_a_human_confirmed_hold_is_never_expired():
    """If the owner says the pending charge is real, a sweep does not overrule them."""
    user_id, account_id = await _account()
    hold = await _txn(account_id, review="confirmed")

    assert await _sweep(user_id, _days(40)) == 0
    assert (await _get(hold)).status == "pending"


async def test_a_hold_paired_into_a_transfer_group_is_never_expired():
    """Expiring one leg would leave its partner a dangling half-group."""
    user_id, account_id = await _account()
    hold = await _txn(account_id, group="grp-1")

    assert await _sweep(user_id, _days(40)) == 0
    assert (await _get(hold)).status == "pending"


async def test_a_posted_transaction_is_never_expired():
    user_id, account_id = await _account()
    posted = await _txn(account_id, status="posted")

    assert await _sweep(user_id, _days(40)) == 0
    assert (await _get(posted)).status == "posted"


async def test_the_sweep_is_idempotent():
    """An already-expired row is not pending, so a second pass finds nothing to do."""
    user_id, account_id = await _account()
    await _txn(account_id)

    assert await _sweep(user_id, _days(40)) == 1
    assert await _sweep(user_id, _days(41)) == 0


async def test_hold_days_is_injectable_for_a_shorter_window():
    user_id, account_id = await _account()
    await _txn(account_id)
    assert await _sweep(user_id, _days(3), hold_days=2) == 1


async def test_an_unrelated_posted_amount_does_not_save_the_hold():
    user_id, account_id = await _account()
    hold = await _txn(account_id, amount=-100)
    await _txn(account_id, amount=-9999, status="posted", date=SWIPE)

    assert await _sweep(user_id, _days(40)) == 1
    assert (await _get(hold)).status == "expired"


# --- The point of it all: an expired hold stops being money --------------------------------


async def test_an_expired_hold_no_longer_counts_toward_the_balance_or_the_rollup():
    """`COUNTABLE_STATUSES` is the single filter every money query shares. If a future status
    forgets to opt out, this is the test that fails."""
    from app.services.account_service import compute_account_balance
    from app.services.summary_service import spending_history

    user_id, account_id = await _account()
    await _txn(account_id, amount=-2500)  # a pending hold, -$25

    async with AsyncSessionLocal() as db:
        before_balance = await compute_account_balance(db, account_id)
        before = await spending_history(db, user_id, months=2, now=_days(0))
    before_spend = sum(m.spend_cents for m in before)

    assert await _sweep(user_id, _days(40)) == 1

    async with AsyncSessionLocal() as db:
        after_balance = await compute_account_balance(db, account_id)
        after = await spending_history(db, user_id, months=2, now=_days(0))
    after_spend = sum(m.spend_cents for m in after)

    assert before_spend == -2500 and after_spend == 0
    assert after_balance - before_balance == 2500  # the -$25 hold left the balance


async def test_a_pending_debit_on_a_depository_account_is_never_expired():
    """An auth hold is a card concept. A checking "pending" is a real, completed ACH debit that
    is pending only until the CSV imports it — expiring those would silently delete real activity
    every time a reconciliation import slipped by a week."""
    async with AsyncSessionLocal() as db:
        user = User(name="Checking", email=f"chk-{uuid.uuid4().hex[:8]}@magpie.test")
        db.add(user)
        await db.flush()
        acct = Account(user_id=user.id, name="Checking", institution="US Bank", type="depository")
        db.add(acct)
        await db.commit()
        user_id, account_id = user.id, acct.id

    debit = await _txn(account_id, amount=-19347, merchant="ACH DEBIT")

    assert await _sweep(user_id, _days(40)) == 0
    assert (await _get(debit)).status == "pending"
