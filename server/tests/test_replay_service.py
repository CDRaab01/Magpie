"""Parser replay (F15 / ROADMAP Wave 0 #7) — the same mock-the-seam discipline as
`test_ingest_service.py`, minus even the fake IMAP: replay's input is the DB, not a mailbox.

The scenario under test throughout is the real one that motivated the tool: an Amex alert that
arrived before its account existed, was filed `unparsed`, and must be retro-filed now — without
double-counting a swipe the CSV backfill already posted.
"""

import datetime
import uuid
from email.utils import parsedate_to_datetime
from pathlib import Path

import email

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.ingest_event import IngestEvent
from app.models.transaction import Transaction
from app.models.user import User
from app.services.replay_service import replay_unparsed_events

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# amex_large_purchase.eml: TEST MERCHANT CO, $42.00 on Jul 5 2026, card ending 0000.
AMEX_AMOUNT_CENTS = -4200
AMEX_DATE = datetime.date(2026, 7, 5)


def _unique_email() -> str:
    return f"replay-test-{uuid.uuid4().hex[:8]}@magpie.test"


async def _make_user_with_account(last4: str = "0000") -> tuple[uuid.UUID, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        user = User(name="Replay Test", email=_unique_email())
        db.add(user)
        await db.flush()
        account = Account(
            user_id=user.id, name="Amex", institution="American Express", type="card", last4=last4
        )
        db.add(account)
        await db.commit()
        return user.id, account.id


async def _make_unparsed_event(user_id: uuid.UUID, fixture: str) -> uuid.UUID:
    """Insert an event exactly as the poller leaves an unfileable email: raw payload kept whole,
    no account, no transaction, `parse_version` "0"."""
    raw = (FIXTURES_DIR / fixture).read_text()
    msg = email.message_from_string(raw)
    async with AsyncSessionLocal() as db:
        event = IngestEvent(
            user_id=user_id,
            account_id=None,
            message_id=f"<{uuid.uuid4().hex}@test.magpie.invalid>",
            received_at=parsedate_to_datetime(msg.get("Date")),
            parser=email.utils.parseaddr(msg.get("From", ""))[1],
            parse_version="0",
            payload_hash=uuid.uuid4().hex,
            outcome="unparsed",
            raw_payload=raw,
        )
        db.add(event)
        await db.commit()
        return event.id


async def _transactions_for(account_id: uuid.UUID) -> list[Transaction]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            Transaction.__table__.select().where(Transaction.account_id == account_id)
        )
        return list(result.fetchall())


async def _event(event_id: uuid.UUID) -> IngestEvent:
    async with AsyncSessionLocal() as db:
        return await db.get(IngestEvent, event_id)


async def test_replay_files_an_alert_that_arrived_before_its_account_existed():
    """The 22-Amex case: parsed fine, no account at the time, so no transaction. Now there is one."""
    user_id, account_id = await _make_user_with_account()
    event_id = await _make_unparsed_event(user_id, "amex_large_purchase.eml")

    async with AsyncSessionLocal() as db:
        summary = await replay_unparsed_events(db, user_id, dry_run=False)

    assert summary.examined == 1
    assert summary.filed == 1
    assert summary.duplicate == summary.still_unparsed == summary.skipped == 0

    rows = await _transactions_for(account_id)
    assert len(rows) == 1
    assert rows[0].amount == AMEX_AMOUNT_CENTS
    assert rows[0].date == AMEX_DATE
    assert rows[0].status == "pending"
    assert rows[0].source == "email"
    assert rows[0].ingest_event_id == event_id

    # The event is no longer a parser mystery: outcome, account and parse_version all move.
    event = await _event(event_id)
    assert event.outcome == "created"
    assert event.account_id == account_id
    assert event.parser == "amex"
    assert event.parse_version == "1"


async def test_dry_run_reports_the_filing_but_writes_nothing():
    user_id, account_id = await _make_user_with_account()
    event_id = await _make_unparsed_event(user_id, "amex_large_purchase.eml")

    async with AsyncSessionLocal() as db:
        summary = await replay_unparsed_events(db, user_id, dry_run=True)

    assert summary.dry_run is True
    assert summary.filed == 1
    assert summary.events[0].amount_cents == AMEX_AMOUNT_CENTS
    assert summary.events[0].txn_date == AMEX_DATE

    assert await _transactions_for(account_id) == []
    assert (await _event(event_id)).outcome == "unparsed"


async def test_replay_twice_files_once():
    """Idempotence is the property that makes this safe to run on real money."""
    user_id, account_id = await _make_user_with_account()
    await _make_unparsed_event(user_id, "amex_large_purchase.eml")

    async with AsyncSessionLocal() as db:
        first = await replay_unparsed_events(db, user_id, dry_run=False)
    async with AsyncSessionLocal() as db:
        second = await replay_unparsed_events(db, user_id, dry_run=False)

    assert first.filed == 1
    # The filed event left the unparsed backlog, so the second pass has nothing to examine.
    assert second.examined == 0
    assert second.filed == 0
    assert len(await _transactions_for(account_id)) == 1


async def test_an_unparsed_event_that_somehow_has_a_transaction_is_skipped_not_doubled():
    """Defence in depth behind the outcome filter: if an event ever carries a transaction while
    still marked unparsed (a crashed run, a manual fix), replay must not file a second one."""
    user_id, account_id = await _make_user_with_account()
    event_id = await _make_unparsed_event(user_id, "amex_large_purchase.eml")
    async with AsyncSessionLocal() as db:
        db.add(
            Transaction(
                account_id=account_id,
                amount=AMEX_AMOUNT_CENTS,
                date=AMEX_DATE,
                status="pending",
                kind="spend",
                source="email",
                ingest_event_id=event_id,
            )
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        summary = await replay_unparsed_events(db, user_id, dry_run=False)

    assert summary.skipped == 1
    assert summary.filed == 0
    assert len(await _transactions_for(account_id)) == 1


async def test_a_swipe_the_csv_backfill_already_posted_is_marked_duplicate_not_filed():
    """The double-count trap: these alerts predate the backfill that already posted their swipes.
    Replay must recognise the posted row as the same swipe and file nothing."""
    user_id, account_id = await _make_user_with_account()
    event_id = await _make_unparsed_event(user_id, "amex_large_purchase.eml")
    async with AsyncSessionLocal() as db:
        db.add(
            Transaction(
                account_id=account_id,
                amount=AMEX_AMOUNT_CENTS,
                date=AMEX_DATE,
                status="posted",
                kind="spend",
                source="csv",
            )
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        summary = await replay_unparsed_events(db, user_id, dry_run=False)

    assert summary.duplicate == 1
    assert summary.filed == 0
    # Still exactly the CSV row — no second, pending copy of the same $42.
    rows = await _transactions_for(account_id)
    assert len(rows) == 1
    assert rows[0].status == "posted"

    event = await _event(event_id)
    assert event.outcome == "duplicate"
    assert event.account_id == account_id


async def test_a_still_unrecognized_template_stays_unparsed_with_a_reason():
    user_id, _ = await _make_user_with_account()
    event_id = await _make_unparsed_event(user_id, "amex_unrecognized_subject.eml")

    async with AsyncSessionLocal() as db:
        summary = await replay_unparsed_events(db, user_id, dry_run=False)

    assert summary.still_unparsed == 1
    assert summary.filed == 0
    assert "subject" in summary.events[0].reason.lower()
    assert (await _event(event_id)).outcome == "unparsed"


async def test_a_parsed_alert_with_no_matching_account_stays_unparsed_and_says_so():
    """Replay before the account exists changes nothing — and names the last4 it wanted."""
    user_id, _ = await _make_user_with_account(last4="9999")
    await _make_unparsed_event(user_id, "amex_large_purchase.eml")

    async with AsyncSessionLocal() as db:
        summary = await replay_unparsed_events(db, user_id, dry_run=False)

    assert summary.still_unparsed == 1
    assert "0000" in summary.events[0].reason
    assert summary.events[0].amount_cents == AMEX_AMOUNT_CENTS


async def test_replay_can_be_scoped_to_specific_events():
    user_id, account_id = await _make_user_with_account()
    first = await _make_unparsed_event(user_id, "amex_large_purchase.eml")
    await _make_unparsed_event(user_id, "amex_merchant_refund.eml")

    async with AsyncSessionLocal() as db:
        summary = await replay_unparsed_events(db, user_id, dry_run=False, event_ids=[first])

    assert summary.examined == 1
    assert summary.filed == 1
    assert len(await _transactions_for(account_id)) == 1


# --- The endpoint (POST /ingest/replay) --------------------------------------------------


async def _user_id_for_account(account_id: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        account = await db.get(Account, uuid.UUID(account_id))
        return account.user_id


async def test_replay_endpoint_defaults_to_a_dry_run(auth_client):
    """Forgetting the parameter must be the safe call: this endpoint creates money rows."""
    r = await auth_client.post(
        "/accounts",
        json={"name": "Amex", "institution": "American Express", "type": "card", "last4": "0000"},
    )
    assert r.status_code == 201, r.text
    account_id = r.json()["id"]
    user_id = await _user_id_for_account(account_id)
    await _make_unparsed_event(user_id, "amex_large_purchase.eml")

    r = await auth_client.post("/ingest/replay")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["filed"] == 1
    assert body["events"][0]["action"] == "filed"
    assert body["events"][0]["amount_cents"] == AMEX_AMOUNT_CENTS
    assert body["events"][0]["txn_date"] == AMEX_DATE.isoformat()

    # Nothing was written: the transactions list is still empty.
    r = await auth_client.get("/transactions")
    assert r.json() == []


async def test_replay_endpoint_commits_when_dry_run_is_false(auth_client):
    r = await auth_client.post(
        "/accounts",
        json={"name": "Amex", "institution": "American Express", "type": "card", "last4": "0000"},
    )
    account_id = r.json()["id"]
    user_id = await _user_id_for_account(account_id)
    await _make_unparsed_event(user_id, "amex_large_purchase.eml")

    r = await auth_client.post("/ingest/replay?dry_run=false")
    assert r.status_code == 200, r.text
    assert r.json()["dry_run"] is False
    assert r.json()["filed"] == 1

    items = (await auth_client.get("/transactions")).json()
    assert len(items) == 1
    assert items[0]["amount"] == AMEX_AMOUNT_CENTS
    assert items[0]["status"] == "pending"


async def test_replay_endpoint_requires_auth(client):
    assert (await client.post("/ingest/replay")).status_code == 401


async def test_replay_will_not_file_onto_an_inactive_account():
    """Replay shares `match_account`, so a retired card stays out of its reach too."""
    user_id, account_id = await _make_user_with_account()
    async with AsyncSessionLocal() as db:
        account = await db.get(Account, account_id)
        account.active = False
        await db.commit()
    await _make_unparsed_event(user_id, "amex_large_purchase.eml")

    async with AsyncSessionLocal() as db:
        summary = await replay_unparsed_events(db, user_id, dry_run=False)

    assert summary.filed == 0
    assert summary.still_unparsed == 1
    assert await _transactions_for(account_id) == []
