import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.ingest_event import IngestEvent
from app.models.user import User
from app.services.ntfy_client import FakeNtfyPublisher
from app.services.sweep_service import run_unparsed_backlog_sweep


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
                received_at=datetime.datetime.now(datetime.timezone.utc),
                parser="unknown",
                parse_version="0",
                payload_hash=uuid.uuid4().hex,
                outcome="unparsed",
                raw_payload="irrelevant",
            )
        )
        await db.commit()


async def test_no_backlog_publishes_nothing():
    user_id = await _make_user()
    publisher = FakeNtfyPublisher()
    async with AsyncSessionLocal() as db:
        previously_true = await run_unparsed_backlog_sweep(
            db, user_id, publisher, previously_true=False
        )
    assert previously_true is False
    assert publisher.published == []


async def test_new_backlog_publishes_once():
    user_id = await _make_user()
    await _add_unparsed_event(user_id)
    publisher = FakeNtfyPublisher()

    async with AsyncSessionLocal() as db:
        previously_true = await run_unparsed_backlog_sweep(
            db, user_id, publisher, previously_true=False
        )
    assert previously_true is True
    assert len(publisher.published) == 1
    assert "1 email" in publisher.published[0][0]


async def test_repeated_sweeps_stay_silent_while_backlog_persists():
    user_id = await _make_user()
    await _add_unparsed_event(user_id)
    publisher = FakeNtfyPublisher()

    previously_true = False
    async with AsyncSessionLocal() as db:
        previously_true = await run_unparsed_backlog_sweep(
            db, user_id, publisher, previously_true=previously_true
        )
    async with AsyncSessionLocal() as db:
        previously_true = await run_unparsed_backlog_sweep(
            db, user_id, publisher, previously_true=previously_true
        )
    async with AsyncSessionLocal() as db:
        previously_true = await run_unparsed_backlog_sweep(
            db, user_id, publisher, previously_true=previously_true
        )

    assert len(publisher.published) == 1  # still just the one alert from the first sweep


async def test_resolved_and_recurring_backlog_fires_a_new_alert():
    user_id = await _make_user()
    publisher = FakeNtfyPublisher()

    # Episode 1: backlog appears.
    await _add_unparsed_event(user_id)
    async with AsyncSessionLocal() as db:
        previously_true = await run_unparsed_backlog_sweep(
            db, user_id, publisher, previously_true=False
        )
    assert len(publisher.published) == 1

    # Episode 1 resolves (simulate by using a fresh user with none unparsed — the real sweep
    # would see this if the events got reprocessed/fixed; here we just assert the *pure*
    # latch behavior directly instead of re-plumbing resolution through the DB).
    async with AsyncSessionLocal() as db:
        previously_true = await run_unparsed_backlog_sweep(
            db, uuid.uuid4(), publisher, previously_true=previously_true
        )
    assert previously_true is False
    assert len(publisher.published) == 1  # no new alert just because it resolved

    # Episode 2: backlog recurs for the original user.
    await _add_unparsed_event(user_id)
    async with AsyncSessionLocal() as db:
        previously_true = await run_unparsed_backlog_sweep(
            db, user_id, publisher, previously_true=previously_true
        )
    assert len(publisher.published) == 2  # a new episode fires a new alert
