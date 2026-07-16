"""Family mode (household sharing) — a member reads and writes the owner's ledger; outsiders can't.

Sharing is **consented**: adding someone creates a *pending* invite that shares nothing until the
invitee accepts it (financial data is never joined silently).
"""

import uuid

from httpx import ASGITransport, AsyncClient

from app.main import app


def _email() -> str:
    # Unique per call: household membership is committed, so fixed emails would leak state across
    # runs (a member from a prior run would already see the ledger).
    return f"fam_{uuid.uuid4().hex[:10]}@magpie.test"


async def _authed(make_suite_token, email: str) -> AsyncClient:
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    r = await c.post("/auth/suite", json={"suite_token": make_suite_token(email)})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c


async def test_invite_shares_nothing_until_accepted(suite_enabled, make_suite_token):
    owner_email, wife_email, stranger_email = _email(), _email(), _email()
    owner = await _authed(make_suite_token, owner_email)
    wife = await _authed(make_suite_token, wife_email)
    stranger = await _authed(make_suite_token, stranger_email)
    try:
        # Owner creates an account (their ledger).
        r = await owner.post(
            "/accounts",
            json={"name": "Joint Checking", "institution": "US Bank", "type": "depository"},
        )
        assert r.status_code == 201, r.text
        acct_id = r.json()["id"]

        # Owner invites the wife by email. The invite is PENDING — not yet shared.
        r = await owner.post("/household/members", json={"email": wife_email})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["shared"] is False  # only the owner is active yet
        wife_row = next(m for m in body["members"] if m["email"] == wife_email)
        assert wife_row["status"] == "pending"

        # She has a pending invite naming the owner...
        r = await wife.get("/household/invite")
        assert r.status_code == 200
        invite = r.json()
        assert invite is not None
        assert invite["owner_email"] == owner_email

        # ...but until she accepts, she sees none of the owner's ledger.
        r = await wife.get("/accounts")
        assert r.status_code == 200
        assert all(a["id"] != acct_id for a in r.json())

        # She accepts — now the ledger is shared.
        r = await wife.post("/household/accept")
        assert r.status_code == 200, r.text
        assert r.json()["shared"] is True

        # She reads the owner's account and can act on it.
        r = await wife.get("/accounts")
        assert any(a["id"] == acct_id for a in r.json())
        r = await wife.post(
            "/transactions",
            json={"account_id": acct_id, "amount": -2500, "date": "2026-07-01", "kind": "spend"},
        )
        assert r.status_code in (200, 201), r.text

        # The owner sees the wife's transaction — one ledger, two contributors.
        r = await owner.get("/transactions")
        assert r.status_code == 200
        assert any(t["amount"] == -2500 for t in r.json())

        # After accepting, there's no pending invite left.
        r = await wife.get("/household/invite")
        assert r.json() is None

        # A non-member sees none of it.
        r = await stranger.get("/accounts")
        assert all(a["id"] != acct_id for a in r.json())
    finally:
        await owner.aclose()
        await wife.aclose()
        await stranger.aclose()


async def test_decline_removes_the_invite(suite_enabled, make_suite_token):
    owner_email, wife_email = _email(), _email()
    owner = await _authed(make_suite_token, owner_email)
    wife = await _authed(make_suite_token, wife_email)
    try:
        r = await owner.post(
            "/accounts", json={"name": "Checking", "institution": "X", "type": "depository"}
        )
        acct_id = r.json()["id"]
        await owner.post("/household/members", json={"email": wife_email})

        # She declines the invite.
        r = await wife.post("/household/decline")
        assert r.status_code == 204

        # No invite remains, and she never gained access to the ledger.
        r = await wife.get("/household/invite")
        assert r.json() is None
        r = await wife.get("/accounts")
        assert all(a["id"] != acct_id for a in r.json())

        # Declining frees her to start her own household later (no lingering pending row).
        r = await wife.post(
            "/accounts", json={"name": "Hers", "institution": "Y", "type": "depository"}
        )
        assert r.status_code == 201, r.text
    finally:
        await owner.aclose()
        await wife.aclose()


async def test_only_owner_manages_members_and_leaving_reverts_to_solo(
    suite_enabled, make_suite_token
):
    owner_email, wife_email = _email(), _email()
    owner = await _authed(make_suite_token, owner_email)
    wife = await _authed(make_suite_token, wife_email)
    try:
        r = await owner.post(
            "/accounts", json={"name": "Checking", "institution": "X", "type": "depository"}
        )
        acct_id = r.json()["id"]
        await owner.post("/household/members", json={"email": wife_email})
        await wife.post("/household/accept")

        # A member (not the owner) can't add others.
        r = await wife.post("/household/members", json={"email": "someone@magpie.test"})
        assert r.status_code == 403

        # She sees the shared ledger while a member...
        r = await wife.get("/accounts")
        assert any(a["id"] == acct_id for a in r.json())

        # ...leaves, and reverts to her own (empty) ledger.
        r = await wife.post("/household/leave")
        assert r.status_code == 204
        r = await wife.get("/accounts")
        assert all(a["id"] != acct_id for a in r.json())
    finally:
        await owner.aclose()
        await wife.aclose()


async def test_pending_invitee_cannot_start_own_household(suite_enabled, make_suite_token):
    owner_email, wife_email = _email(), _email()
    owner = await _authed(make_suite_token, owner_email)
    wife = await _authed(make_suite_token, wife_email)
    try:
        await owner.post("/household/members", json={"email": wife_email})
        # With an invite outstanding, trying to invite someone (which would create her own
        # household) is refused until she resolves it.
        r = await wife.post("/household/members", json={"email": "third@magpie.test"})
        assert r.status_code == 409
    finally:
        await owner.aclose()
        await wife.aclose()


async def test_add_unknown_email_is_404(suite_enabled, make_suite_token):
    owner = await _authed(make_suite_token, _email())
    try:
        r = await owner.post("/household/members", json={"email": "never_signed_in@magpie.test"})
        assert r.status_code == 404
    finally:
        await owner.aclose()
