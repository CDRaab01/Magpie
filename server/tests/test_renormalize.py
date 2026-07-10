"""merchant_norm recompute (ROADMAP #25a) — the derived-data analogue of the parser replay.

The properties that make it safe to point at real money-adjacent data: it changes only the
comparison key (never an amount/date/kind), a dry run writes nothing, re-running is idempotent,
and it aborts loudly rather than write an empty key that would silently break rule matching.
"""

import datetime
import uuid


from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.services.renormalize_service import renormalize_merchants


def _email() -> str:
    return f"renorm-{uuid.uuid4().hex[:8]}@magpie.test"


async def _setup() -> tuple[uuid.UUID, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        user = User(name="Renorm", email=_email())
        db.add(user)
        await db.flush()
        acct = Account(user_id=user.id, name="Checking", institution="T", type="depository")
        db.add(acct)
        await db.commit()
        return user.id, acct.id


async def _txn(account_id, *, raw, norm, amount=-1000):
    """Insert a row with a deliberately STALE merchant_norm (as a pre-normalizer import would)."""
    async with AsyncSessionLocal() as db:
        t = Transaction(
            account_id=account_id,
            amount=amount,
            date=datetime.date(2026, 7, 1),
            status="posted",
            kind="spend",
            source="csv",
            merchant_raw=raw,
            merchant_norm=norm,
            review_state="auto",
        )
        db.add(t)
        await db.commit()
        return t.id


async def _get(txn_id) -> Transaction:
    async with AsyncSessionLocal() as db:
        return await db.get(Transaction, txn_id)


async def test_a_stale_norm_is_recomputed():
    user_id, account_id = await _setup()
    # As the pre-deploy backfill left it: the bank prefix never stripped.
    tid = await _txn(account_id, raw="WEB AUTHORIZED PMT VENMO", norm="WEB AUTHORIZED PMT VENMO")

    async with AsyncSessionLocal() as db:
        summary = await renormalize_merchants(db, user_id, dry_run=False)

    assert summary.changed == 1
    assert (await _get(tid)).merchant_norm == "VENMO"


async def test_dry_run_reports_but_writes_nothing():
    user_id, account_id = await _setup()
    tid = await _txn(account_id, raw="WEB AUTHORIZED PMT VENMO", norm="WEB AUTHORIZED PMT VENMO")

    async with AsyncSessionLocal() as db:
        summary = await renormalize_merchants(db, user_id, dry_run=True)

    assert summary.dry_run is True
    assert summary.changed == 1
    assert summary.sample[0].old == "WEB AUTHORIZED PMT VENMO"
    assert summary.sample[0].new == "VENMO"
    assert (await _get(tid)).merchant_norm == "WEB AUTHORIZED PMT VENMO"  # untouched


async def test_running_twice_changes_nothing_the_second_time():
    user_id, account_id = await _setup()
    await _txn(account_id, raw="WEB AUTHORIZED PMT VENMO", norm="WEB AUTHORIZED PMT VENMO")

    async with AsyncSessionLocal() as db:
        first = await renormalize_merchants(db, user_id, dry_run=False)
    async with AsyncSessionLocal() as db:
        second = await renormalize_merchants(db, user_id, dry_run=False)

    assert first.changed == 1
    assert second.changed == 0  # idempotent


async def test_an_already_correct_norm_is_not_counted_as_changed():
    user_id, account_id = await _setup()
    await _txn(account_id, raw="COSTCO WHSE", norm="COSTCO WHSE")

    async with AsyncSessionLocal() as db:
        summary = await renormalize_merchants(db, user_id, dry_run=False)
    assert summary.changed == 0
    assert summary.examined == 1


async def test_the_distinct_merchant_count_collapses_when_variants_merge():
    """Two rows whose stale norms differ but whose raw strings normalize to the same key."""
    user_id, account_id = await _setup()
    await _txn(account_id, raw="WEB AUTHORIZED PMT VENMO", norm="WEB AUTHORIZED PMT VENMO")
    await _txn(account_id, raw="ELECTRONIC WITHDRAWAL VENMO", norm="ELECTRONIC WITHDRAWAL VENMO")

    async with AsyncSessionLocal() as db:
        summary = await renormalize_merchants(db, user_id, dry_run=False)

    assert summary.distinct_before == 2
    assert summary.distinct_after == 1  # both become VENMO


async def test_a_row_that_would_empty_aborts_the_whole_run():
    """A normalizer that empties a real merchant is a regression; applying it would silently break
    matching, so the run raises and commits nothing."""
    user_id, account_id = await _setup()
    good = await _txn(account_id, raw="COSTCO WHSE", norm="STALE")
    # A raw string of only punctuation normalizes to an empty key.
    await _txn(account_id, raw="###", norm="###")

    import pytest

    with pytest.raises(ValueError):
        async with AsyncSessionLocal() as db:
            await renormalize_merchants(db, user_id, dry_run=False)

    # Nothing committed — the good row's stale norm is untouched.
    assert (await _get(good)).merchant_norm == "STALE"


# --- endpoint ------------------------------------------------------------------------------


async def _account_user(account_id: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        return (await db.get(Account, uuid.UUID(account_id))).user_id


async def test_renormalize_endpoint_defaults_to_dry_run(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Checking", "institution": "T", "type": "depository"}
    )
    account_id = r.json()["id"]
    tid = await _txn(
        uuid.UUID(account_id), raw="WEB AUTHORIZED PMT VENMO", norm="WEB AUTHORIZED PMT VENMO"
    )

    r = await auth_client.post("/admin/renormalize")
    assert r.status_code == 200, r.text
    assert r.json()["dry_run"] is True
    assert r.json()["changed"] == 1
    assert (await _get(tid)).merchant_norm == "WEB AUTHORIZED PMT VENMO"  # not written


async def test_renormalize_endpoint_commits_when_asked(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Checking", "institution": "T", "type": "depository"}
    )
    account_id = r.json()["id"]
    tid = await _txn(
        uuid.UUID(account_id), raw="WEB AUTHORIZED PMT VENMO", norm="WEB AUTHORIZED PMT VENMO"
    )

    r = await auth_client.post("/admin/renormalize?dry_run=false")
    assert r.status_code == 200
    assert r.json()["changed"] == 1
    assert (await _get(tid)).merchant_norm == "VENMO"


async def test_renormalize_endpoint_requires_auth(client):
    assert (await client.post("/admin/renormalize")).status_code == 401
