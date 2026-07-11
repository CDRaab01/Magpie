"""Manual statement-checkpoint entry (ROADMAP #4) — the path that was missing, so prod had 0
checkpoints and the v1 statement-parity gate could never start counting."""

import datetime


async def _account(auth_client, **over):
    body = {"name": "Checking", "institution": "US Bank", "type": "depository", **over}
    r = await auth_client.post("/accounts", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_post_creates_a_checkpoint_and_get_lists_it(auth_client):
    acct = await _account(auth_client)
    r = await auth_client.post(
        f"/accounts/{acct}/checkpoints",
        json={"statement_date": "2026-06-30", "stated_balance_cents": 250000},
    )
    assert r.status_code == 201, r.text
    cp = r.json()
    assert cp["stated_balance_cents"] == 250000
    assert cp["import_batch_id"] is None  # hand-entered

    r = await auth_client.get(f"/accounts/{acct}/checkpoints")
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_reposting_same_date_corrects_in_place(auth_client):
    """Re-entering a statement's balance overwrites it — a duplicate anchor on the same closing
    date would corrupt the reconciliation window."""
    acct = await _account(auth_client)
    await auth_client.post(
        f"/accounts/{acct}/checkpoints",
        json={"statement_date": "2026-06-30", "stated_balance_cents": 250000},
    )
    r = await auth_client.post(
        f"/accounts/{acct}/checkpoints",
        json={"statement_date": "2026-06-30", "stated_balance_cents": 251234},
    )
    assert r.status_code == 201
    r = await auth_client.get(f"/accounts/{acct}/checkpoints")
    assert len(r.json()) == 1  # not duplicated
    assert r.json()[0]["stated_balance_cents"] == 251234


async def test_first_checkpoint_anchors_the_balance_and_reconciles_to_zero(auth_client):
    acct = await _account(auth_client)
    await auth_client.post(
        f"/accounts/{acct}/checkpoints",
        json={"statement_date": "2026-06-30", "stated_balance_cents": 250000},
    )
    r = await auth_client.get(f"/accounts/{acct}")
    body = r.json()
    assert body["balance_cents"] == 250000  # anchored, no later transactions
    assert body["balance_delta_cents"] == 0  # a single checkpoint reconciles trivially


async def test_second_checkpoint_makes_the_delta_a_real_signal(auth_client):
    acct = await _account(auth_client)
    await auth_client.post(
        f"/accounts/{acct}/checkpoints",
        json={"statement_date": "2026-05-31", "stated_balance_cents": 250000},
    )
    # No transactions between the two dates, but the later statement claims a different balance:
    # the ledger can't account for the 2,000-cent move -> the honesty meter shows it.
    await auth_client.post(
        f"/accounts/{acct}/checkpoints",
        json={"statement_date": "2026-06-30", "stated_balance_cents": 252000},
    )
    r = await auth_client.get(f"/accounts/{acct}")
    assert r.json()["balance_delta_cents"] == -2000


async def test_future_statement_date_is_rejected(auth_client):
    acct = await _account(auth_client)
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    r = await auth_client.post(
        f"/accounts/{acct}/checkpoints",
        json={"statement_date": tomorrow, "stated_balance_cents": 100000},
    )
    assert r.status_code == 422


async def test_card_balance_is_signed_negative(auth_client):
    """A card's stated balance is what you owe; in the ledger's sign convention that reads
    negative, matching the derived balance so the delta lines up."""
    acct = await _account(auth_client, name="Amex", institution="Amex", type="card", last4="1234")
    r = await auth_client.post(
        f"/accounts/{acct}/checkpoints",
        json={"statement_date": "2026-06-30", "stated_balance_cents": -84000},
    )
    assert r.status_code == 201
    assert (await auth_client.get(f"/accounts/{acct}")).json()["balance_cents"] == -84000


async def test_checkpoints_are_not_visible_to_another_user(
    client, auth_client, suite_enabled, make_suite_token
):
    acct = await _account(auth_client)
    await auth_client.post(
        f"/accounts/{acct}/checkpoints",
        json={"statement_date": "2026-06-30", "stated_balance_cents": 250000},
    )
    other = await client.post(
        "/auth/suite", json={"suite_token": make_suite_token("intruder@example.com")}
    )
    client.headers["Authorization"] = f"Bearer {other.json()['access_token']}"
    # Ownership is enforced on the account before any checkpoint is touched.
    assert (await client.get(f"/accounts/{acct}/checkpoints")).status_code == 404
    r = await client.post(
        f"/accounts/{acct}/checkpoints",
        json={"statement_date": "2026-06-30", "stated_balance_cents": 999},
    )
    assert r.status_code == 404
