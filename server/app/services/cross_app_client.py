"""Magpie's cross-app CONSUMER client (federated awareness, CROSS-APP.md rule 7).

Link A: Cookbook's cooked-meal counts — the lever behind dining-out spend. The budget coach can
see the symptom (dining over pace) but not the cause (nobody cooked); this fetches the fact.

Link G: Spotter's training-day counts — turns a gym subscription's flat monthly cost into a
cost-per-visit ("$3.75/visit · 12 visits"), the number that actually says whether it's worth it.

RS256-ONLY by construction: Magpie post-dates the HS256 retirement plan, so unlike Plate/Cookbook
there is no legacy shared-secret branch — a short-lived service token is minted from dragonfly-id
(`POST /cross-app/token`, confidential client) per call. Unset config ⇒ every fetch returns None.

Every fetch is **best-effort**: any failure — provider down, token mint down, malformed reply —
returns None, and None means "the source didn't say", never a zero (rule 7's absence-vs-zero
distinction). Callers simply omit the context.
"""

import datetime
import logging
from dataclasses import dataclass

import httpx

from app.config import settings

log = logging.getLogger("magpie.cross_app")


def cross_app_configured() -> bool:
    return bool(
        settings.suite_issuer and settings.cross_app_client_id and settings.cross_app_client_secret
    )


async def fetch_cross_app_token(email: str, *, client: httpx.AsyncClient | None = None) -> str:
    """Mint a short-lived RS256 cross-app token for `email` from dragonfly-id."""
    request = lambda c: c.post(  # noqa: E731 - tiny local binding, reused for both client paths
        f"{settings.suite_issuer.rstrip('/')}/cross-app/token",
        data={
            "client_id": settings.cross_app_client_id,
            "client_secret": settings.cross_app_client_secret,
            "subject_email": email,
        },
    )
    if client is not None:
        resp = await request(client)
    else:
        async with httpx.AsyncClient(timeout=settings.cross_app_timeout_seconds) as owned:
            resp = await request(owned)
    resp.raise_for_status()
    return resp.json()["access_token"]


@dataclass(frozen=True)
class CookedWindow:
    """Home-cooked meals over the last 14 days vs the prior 14 (mirrors Cookbook's
    /cross-app/cooked contract, split into two halves so 'fewer than usual' is visible)."""

    last_14_days: int
    prior_14_days: int


async def fetch_cooked_window(
    email: str, *, now: datetime.datetime, client: httpx.AsyncClient | None = None
) -> CookedWindow | None:
    """Cook events over the trailing 28 days, split 14/14. None on any failure or when the
    integration is unconfigured."""
    if not settings.cookbook_base_url or not cross_app_configured():
        return None
    today = now.date()
    start = today - datetime.timedelta(days=27)
    try:
        token = await fetch_cross_app_token(email, client=client)
        request = lambda c: c.get(  # noqa: E731
            f"{settings.cookbook_base_url.rstrip('/')}/cross-app/cooked",
            params={"start": start.isoformat(), "end": today.isoformat()},
            headers={"Authorization": f"Bearer {token}"},
        )
        if client is not None:
            resp = await request(client)
        else:
            async with httpx.AsyncClient(timeout=settings.cross_app_timeout_seconds) as owned:
                resp = await request(owned)
        resp.raise_for_status()
        events = resp.json().get("events", [])
        midpoint = today - datetime.timedelta(days=13)
        last_14 = sum(1 for e in events if datetime.date.fromisoformat(e["date"]) >= midpoint)
        return CookedWindow(last_14_days=last_14, prior_14_days=len(events) - last_14)
    except Exception as exc:  # noqa: BLE001 - rule 7: degrade to absence, never propagate
        log.warning("cooked-window lookup failed for %s: %s", email, exc)
        return None


async def fetch_month_workout_visits(
    email: str, *, now: datetime.datetime, client: httpx.AsyncClient | None = None
) -> int | None:
    """Training days so far this month from Spotter's ``GET /workouts?start=&end=`` (Link G).

    Returns ``days_trained`` (a day with any session counts once — the visit count for a gym
    membership). None on any failure or when the integration is unconfigured — never 0, since
    'Spotter didn't answer' is not 'you didn't train' (rule 7's absence-vs-zero)."""
    if not settings.spotter_base_url or not cross_app_configured():
        return None
    today = now.date()
    start = today.replace(day=1)
    try:
        token = await fetch_cross_app_token(email, client=client)
        request = lambda c: c.get(  # noqa: E731
            f"{settings.spotter_base_url.rstrip('/')}/workouts",
            params={"start": start.isoformat(), "end": today.isoformat()},
            headers={"Authorization": f"Bearer {token}"},
        )
        if client is not None:
            resp = await request(client)
        else:
            async with httpx.AsyncClient(timeout=settings.cross_app_timeout_seconds) as owned:
                resp = await request(owned)
        resp.raise_for_status()
        return int(resp.json()["totals"]["days_trained"])
    except Exception as exc:  # noqa: BLE001 - rule 7: degrade to absence, never propagate
        log.warning("workout-visits lookup failed for %s: %s", email, exc)
        return None
