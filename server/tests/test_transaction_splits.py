"""Transaction splits (V1.md Tier 3 #26). The load-bearing property: a split must not
double-count — the parent carries the balance/month total; the parts carry the category
breakdown; both views agree on the total."""


async def _category_ids(auth_client) -> dict[str, str]:
    cats = (await auth_client.get("/categories")).json()
    return {c["name"]: c["id"] for c in cats}


async def _make_account(auth_client) -> str:
    return (
        await auth_client.post(
            "/accounts", json={"name": "Card", "institution": "Test", "type": "card"}
        )
    ).json()["id"]


async def _make_spend(auth_client, account_id: str, amount: int, date: str = "2026-07-15") -> str:
    return (
        await auth_client.post(
            "/transactions",
            json={"account_id": account_id, "amount": amount, "date": date, "kind": "spend"},
        )
    ).json()["id"]


def _split_body(cats: dict[str, str]):
    # $50 grocery run: $40 groceries + $10 cash back — the canonical split.
    return {
        "parts": [
            {"category_id": cats["Groceries"], "amount": -4000, "kind": "spend"},
            {"category_id": cats["Cash"], "amount": -1000, "kind": "spend"},
        ]
    }


async def test_split_creates_parts_and_marks_parent(auth_client):
    cats = await _category_ids(auth_client)
    account_id = await _make_account(auth_client)
    txn_id = await _make_spend(auth_client, account_id, -5000)

    r = await auth_client.post(f"/transactions/{txn_id}/split", json=_split_body(cats))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent"]["is_split"] is True
    assert body["parent"]["category_id"] is None  # parent has no single category once split
    assert len(body["parts"]) == 2
    assert {p["amount"] for p in body["parts"]} == {-4000, -1000}
    assert all(p["split_parent_id"] == txn_id for p in body["parts"])
    assert all(p["review_state"] == "confirmed" for p in body["parts"])


async def test_parts_must_sum_to_the_parent(auth_client):
    cats = await _category_ids(auth_client)
    account_id = await _make_account(auth_client)
    txn_id = await _make_spend(auth_client, account_id, -5000)
    bad = {
        "parts": [
            {"category_id": cats["Groceries"], "amount": -4000, "kind": "spend"},
            {
                "category_id": cats["Cash"],
                "amount": -500,
                "kind": "spend",
            },  # sums to -4500, not -5000
        ]
    }
    r = await auth_client.post(f"/transactions/{txn_id}/split", json=bad)
    assert r.status_code == 422


async def test_split_needs_at_least_two_parts(auth_client):
    cats = await _category_ids(auth_client)
    account_id = await _make_account(auth_client)
    txn_id = await _make_spend(auth_client, account_id, -5000)
    one = {"parts": [{"category_id": cats["Groceries"], "amount": -5000, "kind": "spend"}]}
    r = await auth_client.post(f"/transactions/{txn_id}/split", json=one)
    assert r.status_code == 422


async def test_list_hides_parts_but_keeps_the_parent(auth_client):
    cats = await _category_ids(auth_client)
    account_id = await _make_account(auth_client)
    txn_id = await _make_spend(auth_client, account_id, -5000)
    await auth_client.post(f"/transactions/{txn_id}/split", json=_split_body(cats))

    rows = (await auth_client.get("/transactions")).json()
    assert [t["id"] for t in rows] == [txn_id]  # only the parent, no child parts
    assert rows[0]["is_split"] is True


async def test_month_total_and_balance_count_the_split_once(auth_client):
    account_id = await _make_account(auth_client)
    txn_id = await _make_spend(auth_client, account_id, -5000)
    cats = await _category_ids(auth_client)

    before = (await auth_client.get("/transactions/summary?year=2026&month=7")).json()[
        "spend_cents"
    ]
    await auth_client.post(f"/transactions/{txn_id}/split", json=_split_body(cats))
    after = (await auth_client.get("/transactions/summary?year=2026&month=7")).json()["spend_cents"]
    assert before == after == -5000  # splitting doesn't change the month spend total

    balance = next(a for a in (await auth_client.get("/accounts")).json() if a["id"] == account_id)[
        "balance_cents"
    ]
    assert balance == -5000  # parent carries the balance; parts are not added on top


async def test_budget_actuals_use_the_parts_not_the_parent(auth_client):
    cats = await _category_ids(auth_client)
    account_id = await _make_account(auth_client)
    txn_id = await _make_spend(auth_client, account_id, -5000)
    await auth_client.post(f"/transactions/{txn_id}/split", json=_split_body(cats))
    await auth_client.post(
        "/budgets", json={"category_id": cats["Groceries"], "month": "2026-07-01", "amount": 60000}
    )

    budgets = (await auth_client.get("/budgets?month=2026-07-01")).json()
    groceries = next(b for b in budgets if b["category_id"] == cats["Groceries"])
    assert groceries["actual_cents"] == -4000  # the grocery *part*, not the -5000 parent


async def test_unsplit_removes_parts_and_restores_the_parent(auth_client):
    cats = await _category_ids(auth_client)
    account_id = await _make_account(auth_client)
    txn_id = await _make_spend(auth_client, account_id, -5000)
    await auth_client.post(f"/transactions/{txn_id}/split", json=_split_body(cats))

    r = await auth_client.delete(f"/transactions/{txn_id}/split")
    assert r.status_code == 200, r.text
    assert r.json()["is_split"] is False
    rows = (await auth_client.get("/transactions")).json()
    assert [t["id"] for t in rows] == [txn_id]  # parent still there, parts gone
