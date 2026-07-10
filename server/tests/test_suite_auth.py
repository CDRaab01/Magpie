import uuid

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.user import User


async def _count_users(email: str) -> int:
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(select(func.count()).select_from(User).where(User.email == email))
        ).scalar()


async def test_disabled_by_default_returns_404(client):
    # No suite_* config → the endpoint is off. There is no password login to fall back to
    # (SSO-only) — this 404 is the entire auth surface when the flag is unset.
    r = await client.post("/auth/suite", json={"suite_token": "anything"})
    assert r.status_code == 404


async def test_new_email_creates_and_links(client, suite_enabled, make_suite_token):
    # A fresh email per run: this test's whole premise is "an address the DB has never seen",
    # and the local throwaway DB outlives a pytest run (only CI gets a virgin container). A
    # hardcoded address made the suite pass once and fail every time after — the same
    # non-idempotent-test-data trap `test_ingest_service.py` dodges with unique Message-IDs.
    email = f"brandnew-{uuid.uuid4().hex[:8]}@example.com"
    assert await _count_users(email) == 0
    r = await client.post("/auth/suite", json={"suite_token": make_suite_token(email)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] and body["refresh_token"]
    assert await _count_users(email) == 1
    # Second suite login for the same email must reuse the account, not duplicate it.
    r = await client.post("/auth/suite", json={"suite_token": make_suite_token(email)})
    assert r.status_code == 200
    assert await _count_users(email) == 1


async def test_wrong_issuer_rejected(client, suite_enabled, make_suite_token):
    r = await client.post(
        "/auth/suite",
        json={"suite_token": make_suite_token("x@example.com", iss="http://evil")},
    )
    assert r.status_code == 401


async def test_wrong_audience_rejected(client, suite_enabled, make_suite_token):
    r = await client.post(
        "/auth/suite",
        json={"suite_token": make_suite_token("y@example.com", aud="not-suite")},
    )
    assert r.status_code == 401


async def test_garbage_token_rejected(client, suite_enabled):
    r = await client.post("/auth/suite", json={"suite_token": "not-a-jwt"})
    assert r.status_code == 401


async def test_no_email_claim_rejected(client, suite_enabled, make_suite_token):
    r = await client.post("/auth/suite", json={"suite_token": make_suite_token("")})
    assert r.status_code == 401
