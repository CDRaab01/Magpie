async def test_refresh_issues_a_new_pair(client, suite_enabled, make_suite_token):
    login = await client.post(
        "/auth/suite", json={"suite_token": make_suite_token("refresh-test@example.com")}
    )
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    r = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] and body["refresh_token"]


async def test_refresh_rejects_an_access_token(client, suite_enabled, make_suite_token):
    login = await client.post(
        "/auth/suite", json={"suite_token": make_suite_token("refresh-test-2@example.com")}
    )
    access_token = login.json()["access_token"]

    r = await client.post("/auth/refresh", json={"refresh_token": access_token})
    assert r.status_code == 401


async def test_refresh_rejects_garbage(client):
    r = await client.post("/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert r.status_code == 401
