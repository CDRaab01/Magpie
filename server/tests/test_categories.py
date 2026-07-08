# The shared vocabulary the seed migration (V1.md Tier 1 #8) must install. Pinned here
# independently of the migration on purpose — changing the seed set must break this test.
EXPECTED_SEED_CATEGORIES = {
    "Groceries",
    "Dining",
    "Transport",
    "Utilities",
    "Housing",
    "Subscriptions",
    "Entertainment",
    "Health",
    "Shopping",
    "Travel",
    "Cash",
    "Income",
    "Other",
}


async def test_seeded_shared_categories_are_visible_to_a_fresh_user(auth_client):
    # The seed migration inserts the shared vocabulary with user_id NULL, so a brand-new user
    # sees it without creating anything. (CI runs `alembic upgrade head` before pytest, so the
    # seed rows are present.) Every seeded category reads as shared/read-only.
    r = await auth_client.get("/categories")
    assert r.status_code == 200
    by_name = {c["name"]: c for c in r.json()}
    for name in EXPECTED_SEED_CATEGORIES:
        assert name in by_name, f"seeded category {name!r} missing"
        assert by_name[name]["shared"] is True


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


async def test_rename_own_category(auth_client):
    # A custom name (not one of the seeded shared categories) so the rename is unambiguous.
    r = await auth_client.post("/categories", json={"name": "Coffee Runs"})
    category_id = r.json()["id"]
    r = await auth_client.patch(f"/categories/{category_id}", json={"name": "Espresso"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Espresso"
    assert r.json()["shared"] is False

    names = [c["name"] for c in (await auth_client.get("/categories")).json()]
    assert "Espresso" in names
    assert "Coffee Runs" not in names


async def test_rename_shared_category_is_forbidden(auth_client):
    # Seeded/shared categories (user_id NULL) are read-only — renaming one 404s via the
    # ownership filter, same guard as delete.
    shared = next(c for c in (await auth_client.get("/categories")).json() if c["shared"])
    r = await auth_client.patch(f"/categories/{shared['id']}", json={"name": "Hijacked"})
    assert r.status_code == 404


async def test_rename_unknown_category_returns_404(auth_client):
    r = await auth_client.patch(
        "/categories/00000000-0000-0000-0000-000000000000", json={"name": "Nope"}
    )
    assert r.status_code == 404
