import io


async def _make_account(auth_client, **overrides):
    payload = {"name": "Checking", "institution": "US Bank", "type": "depository"}
    payload.update(overrides)
    r = await auth_client.post("/accounts", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _csv(text: str, name: str = "s.csv"):
    return {"file": (name, io.BytesIO(text.encode()), "text/csv")}


async def _make_transfer_pair(auth_client):
    """Create a real transfer pair through the import path: a card payment inflow, then the
    matching checking outflow that pairs with it during evaluation. Returns the two legs."""
    card_id = await _make_account(auth_client, name="Amex", type="card", institution="Amex")
    checking_id = await _make_account(auth_client, name="Checking", type="depository")
    await auth_client.post(
        "/imports/csv",
        data={"account_id": card_id, "institution": "Amex"},
        files=_csv("Date,Description,Amount\n2026-07-04,PAYMENT THANK YOU,50.00\n", "card.csv"),
    )
    await auth_client.post(
        "/imports/csv",
        data={"account_id": checking_id, "institution": "US Bank"},
        files=_csv("Date,Description,Amount\n2026-07-05,CREDIT CARD PAYMENT,-50.00\n", "chk.csv"),
    )
    txns = (await auth_client.get("/transactions")).json()
    transfers = [t for t in txns if t["kind"] == "transfer"]
    return transfers


async def test_create_and_get_transaction(auth_client):
    account_id = await _make_account(auth_client)
    r = await auth_client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "amount": -1200,
            "date": "2026-07-01",
            "kind": "spend",
            "merchant_raw": "Coffee Shop",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["amount"] == -1200
    assert body["source"] == "manual"
    assert body["review_state"] == "confirmed"

    r = await auth_client.get(f"/transactions/{body['id']}")
    assert r.status_code == 200
    assert r.json()["merchant_raw"] == "Coffee Shop"


async def test_create_rejects_wrong_sign_for_kind(auth_client):
    account_id = await _make_account(auth_client)
    r = await auth_client.post(
        "/transactions",
        json={"account_id": account_id, "amount": 1200, "date": "2026-07-01", "kind": "spend"},
    )
    assert r.status_code == 422


async def test_create_rejects_zero_amount(auth_client):
    account_id = await _make_account(auth_client)
    r = await auth_client.post(
        "/transactions",
        json={"account_id": account_id, "amount": 0, "date": "2026-07-01", "kind": "income"},
    )
    assert r.status_code == 422


async def test_create_rejects_unknown_account(auth_client):
    r = await auth_client.post(
        "/transactions",
        json={
            "account_id": "00000000-0000-0000-0000-000000000000",
            "amount": -500,
            "date": "2026-07-01",
            "kind": "spend",
        },
    )
    assert r.status_code == 404


async def test_list_filters_by_date_range(auth_client):
    account_id = await _make_account(auth_client)
    for d in ("2026-06-15", "2026-07-01", "2026-07-15", "2026-08-01"):
        r = await auth_client.post(
            "/transactions",
            json={"account_id": account_id, "amount": -100, "date": d, "kind": "spend"},
        )
        assert r.status_code == 201

    r = await auth_client.get("/transactions", params={"start": "2026-07-01", "end": "2026-07-31"})
    assert r.status_code == 200
    dates = {t["date"] for t in r.json()}
    assert dates == {"2026-07-01", "2026-07-15"}


async def test_update_and_delete_transaction(auth_client):
    account_id = await _make_account(auth_client)
    category = await auth_client.post("/categories", json={"name": "Dining"})
    category_id = category.json()["id"]

    r = await auth_client.post(
        "/transactions",
        json={"account_id": account_id, "amount": -500, "date": "2026-07-01", "kind": "spend"},
    )
    txn_id = r.json()["id"]

    r = await auth_client.patch(f"/transactions/{txn_id}", json={"category_id": category_id})
    assert r.status_code == 200
    assert r.json()["category_id"] == category_id

    r = await auth_client.delete(f"/transactions/{txn_id}")
    assert r.status_code == 204
    r = await auth_client.get(f"/transactions/{txn_id}")
    assert r.status_code == 404


async def test_transaction_not_visible_to_a_different_user(
    client, auth_client, suite_enabled, make_suite_token
):
    account_id = await _make_account(auth_client)
    r = await auth_client.post(
        "/transactions",
        json={"account_id": account_id, "amount": -500, "date": "2026-07-01", "kind": "spend"},
    )
    txn_id = r.json()["id"]

    other = await client.post(
        "/auth/suite", json={"suite_token": make_suite_token("someone-else@example.com")}
    )
    client.headers["Authorization"] = f"Bearer {other.json()['access_token']}"
    r = await client.get(f"/transactions/{txn_id}")
    assert r.status_code == 404


async def test_monthly_summary_matches_ledger_math(auth_client):
    account_id = await _make_account(auth_client)
    rows = [
        (450000, "income", "2026-07-05"),
        (-120000, "spend", "2026-07-01"),
        (-8500, "spend", "2026-07-10"),
        (1500, "refund", "2026-07-12"),
        (-24000, "transfer", "2026-07-15"),
        (24000, "transfer", "2026-07-15"),
        # Outside the month — must not leak into the summary.
        (-999999, "spend", "2026-06-30"),
    ]
    for amount, kind, date in rows:
        r = await auth_client.post(
            "/transactions",
            json={"account_id": account_id, "amount": amount, "date": date, "kind": kind},
        )
        assert r.status_code == 201, r.text

    r = await auth_client.get("/transactions/summary", params={"year": 2026, "month": 7})
    assert r.status_code == 200
    body = r.json()
    assert body["income_cents"] == 450000
    assert body["spend_cents"] == -120000 - 8500 + 1500
    assert body["net_cents"] == body["income_cents"] + body["spend_cents"]


async def test_import_pairs_a_card_payment_across_accounts(auth_client):
    # F3 happy path through the import pipeline: a payment-shaped pair (card inflow + checking
    # outflow) auto-files as a transfer group.
    transfers = await _make_transfer_pair(auth_client)
    assert len(transfers) == 2
    group = transfers[0]["transfer_group"]
    assert group is not None
    assert all(t["transfer_group"] == group for t in transfers)
    assert all(t["review_state"] == "auto" for t in transfers)


async def test_unpair_dissolves_a_transfer_pair(auth_client):
    transfers = await _make_transfer_pair(auth_client)
    assert len(transfers) == 2

    r = await auth_client.post(f"/transactions/{transfers[0]['id']}/unpair")
    assert r.status_code == 200, r.text
    affected = r.json()
    assert len(affected) == 2
    assert all(t["transfer_group"] is None for t in affected)
    assert all(t["review_state"] == "needs_review" for t in affected)
    # Legs revert to their sign-based kind (the +card leg -> income, the -checking leg -> spend).
    assert {t["kind"] for t in affected} == {"income", "spend"}


async def test_unpair_on_a_non_transfer_is_rejected(auth_client):
    account_id = await _make_account(auth_client)
    r = await auth_client.post(
        "/transactions",
        json={"account_id": account_id, "amount": -500, "date": "2026-07-01", "kind": "spend"},
    )
    txn_id = r.json()["id"]
    r = await auth_client.post(f"/transactions/{txn_id}/unpair")
    assert r.status_code == 422


async def test_patch_kind_away_from_transfer_dissolves_the_whole_group(auth_client):
    # F12: correcting one leg's kind away from "transfer" must dissolve the partner too, never
    # leave a dangling half-group that no longer nets to zero.
    transfers = await _make_transfer_pair(auth_client)
    card_leg = next(t for t in transfers if t["amount"] > 0)
    other_id = next(t["id"] for t in transfers if t["id"] != card_leg["id"])

    r = await auth_client.patch(f"/transactions/{card_leg['id']}", json={"kind": "income"})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "income"
    assert r.json()["transfer_group"] is None

    partner = (await auth_client.get(f"/transactions/{other_id}")).json()
    assert partner["transfer_group"] is None
    assert partner["kind"] == "spend"  # sign-based revert of the negative checking leg
    assert partner["review_state"] == "needs_review"
