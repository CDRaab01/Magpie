async def _make_account(auth_client, **overrides):
    payload = {"name": "Checking", "institution": "US Bank", "type": "depository"}
    payload.update(overrides)
    r = await auth_client.post("/accounts", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


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
