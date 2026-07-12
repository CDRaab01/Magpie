"""Magpie's cross-app consumer client (federated awareness Link A): RS256-only token mint,
the 14/14 cooked-window split, unconfigured-absence, and degrade-to-None on failure."""

import datetime

import httpx

from app.config import settings
from app.services.cross_app_client import (
    CookedWindow,
    cross_app_configured,
    fetch_cooked_window,
)

NOW = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=datetime.timezone.utc)


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "suite_issuer", "https://id.test")
    monkeypatch.setattr(settings, "cross_app_client_id", "magpie")
    monkeypatch.setattr(settings, "cross_app_client_secret", "s3cret")
    monkeypatch.setattr(settings, "cookbook_base_url", "https://cookbook.test")


def _client(cooked_events, *, fail_cooked=False):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cross-app/token"):
            body = request.read().decode()
            assert "client_id=magpie" in body and "subject_email=" in body
            return httpx.Response(200, json={"access_token": "rs256-tok", "expires_in": 120})
        if request.url.path.endswith("/cross-app/cooked"):
            if fail_cooked:
                return httpx.Response(500)
            assert request.headers["Authorization"] == "Bearer rs256-tok"
            return httpx.Response(
                200,
                json={
                    "start": "x",
                    "end": "y",
                    "count": len(cooked_events),
                    "distinct_recipes": 1,
                    "events": cooked_events,
                },
            )
        raise AssertionError(f"unexpected call {request.url}")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_unconfigured_returns_none_without_network():
    # Defaults: no client creds, no cookbook_base_url — absent, instantly.
    assert not cross_app_configured()
    assert await fetch_cooked_window("a@b.com", now=NOW) is None


async def test_cooked_window_splits_last_14_vs_prior_14(monkeypatch):
    _configure(monkeypatch)
    today = NOW.date()
    events = [
        {"date": (today - datetime.timedelta(days=20)).isoformat(), "recipe_name": "Old Stew"},
        {"date": (today - datetime.timedelta(days=15)).isoformat(), "recipe_name": "Old Stew"},
        {"date": (today - datetime.timedelta(days=5)).isoformat(), "recipe_name": "Tikka"},
        {"date": (today - datetime.timedelta(days=13)).isoformat(), "recipe_name": "Tikka"},
    ]
    async with _client(events) as client:
        window = await fetch_cooked_window("a@b.com", now=NOW, client=client)
    # days 5 and 13 fall inside the last-14 window (midpoint = today-13, inclusive).
    assert window == CookedWindow(last_14_days=2, prior_14_days=2)


async def test_provider_failure_degrades_to_none(monkeypatch):
    _configure(monkeypatch)
    async with _client([], fail_cooked=True) as client:
        assert await fetch_cooked_window("a@b.com", now=NOW, client=client) is None
