async def test_create_and_list_account(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Checking", "institution": "US Bank", "type": "depository"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Checking"
    assert body["active"] is True

    r = await auth_client.get("/accounts")
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_create_rejects_invalid_type(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Bad", "institution": "X", "type": "savings"}
    )
    assert r.status_code == 422


async def test_create_rejects_bad_last4(auth_client):
    r = await auth_client.post(
        "/accounts",
        json={"name": "Card", "institution": "Amex", "type": "card", "last4": "12"},
    )
    assert r.status_code == 422


async def test_get_update_delete_account(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Amex", "institution": "Amex", "type": "card", "last4": "1234"}
    )
    account_id = r.json()["id"]

    r = await auth_client.get(f"/accounts/{account_id}")
    assert r.status_code == 200

    r = await auth_client.patch(f"/accounts/{account_id}", json={"active": False})
    assert r.status_code == 200
    assert r.json()["active"] is False

    r = await auth_client.delete(f"/accounts/{account_id}")
    assert r.status_code == 204

    r = await auth_client.get(f"/accounts/{account_id}")
    assert r.status_code == 404


async def test_unknown_account_returns_404(auth_client):
    r = await auth_client.get("/accounts/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


async def test_account_not_visible_to_a_different_user(
    client, auth_client, suite_enabled, make_suite_token
):
    r = await auth_client.post(
        "/accounts", json={"name": "Mine", "institution": "X", "type": "depository"}
    )
    account_id = r.json()["id"]

    # A second suite login (different email -> different user) must not see the first user's
    # account — ownership is enforced by filtering on user_id, not by anything client-supplied.
    other = await client.post(
        "/auth/suite", json={"suite_token": make_suite_token("someone-else@example.com")}
    )
    client.headers["Authorization"] = f"Bearer {other.json()['access_token']}"
    r = await client.get(f"/accounts/{account_id}")
    assert r.status_code == 404
