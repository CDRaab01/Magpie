"""Family mode (household sharing) — a member reads and writes the owner's ledger; outsiders can't."""

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


async def test_member_shares_the_ledger_both_ways(suite_enabled, make_suite_token):
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

        # Before sharing, the wife's ledger is her own — she can't see it.
        r = await wife.get("/accounts")
        assert r.status_code == 200
        assert all(a["id"] != acct_id for a in r.json())

        # Owner shares the household with the wife by email.
        r = await owner.post("/household/members", json={"email": wife_email})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["shared"] is True
        assert {m["email"] for m in body["members"]} == {owner_email, wife_email}

        # Now she reads the owner's account (the shared ledger).
        r = await wife.get("/accounts")
        assert any(a["id"] == acct_id for a in r.json())

        # ...and she can act on it: a transaction she posts lands in the shared ledger.
        r = await wife.post(
            "/transactions",
            json={"account_id": acct_id, "amount": -2500, "date": "2026-07-01", "kind": "spend"},
        )
        assert r.status_code in (200, 201), r.text

        # The owner sees the wife's transaction — one ledger, two contributors.
        r = await owner.get("/transactions")
        assert r.status_code == 200
        assert any(t["amount"] == -2500 for t in r.json())

        # A non-member sees none of it.
        r = await stranger.get("/accounts")
        assert all(a["id"] != acct_id for a in r.json())
    finally:
        await owner.aclose()
        await wife.aclose()
        await stranger.aclose()


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


async def test_add_unknown_email_is_404(suite_enabled, make_suite_token):
    owner = await _authed(make_suite_token, _email())
    try:
        r = await owner.post("/household/members", json={"email": "never_signed_in@magpie.test"})
        assert r.status_code == 404
    finally:
        await owner.aclose()
