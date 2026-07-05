async def test_create_and_list_category(auth_client):
    r = await auth_client.post("/categories", json={"name": "Groceries"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Groceries"
    assert body["shared"] is False

    r = await auth_client.get("/categories")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert "Groceries" in names


async def test_delete_own_category(auth_client):
    r = await auth_client.post("/categories", json={"name": "Temp"})
    category_id = r.json()["id"]
    r = await auth_client.delete(f"/categories/{category_id}")
    assert r.status_code == 204
    r = await auth_client.get("/categories")
    assert "Temp" not in [c["name"] for c in r.json()]


async def test_delete_unknown_category_returns_404(auth_client):
    r = await auth_client.delete("/categories/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
