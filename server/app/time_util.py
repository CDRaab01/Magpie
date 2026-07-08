"""Owner-local date derivation (F18).

Magpie's "months" are the owner's local months, not UTC: a swipe emailed at 11pm local on the
last day of the month must file under *that* month, not roll into the next because the server
clock is UTC. Any transaction date derived from a *timestamp* (an email whose body carries no
explicit date line) goes through here first; dates that arrive as real `date`s (CSV rows, the
manual cash-entry form) are already calendar dates and are used as-is.
"""

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def owner_local_date(dt: datetime.datetime, tz_name: str) -> datetime.date:
    """The calendar date of `dt` in the owner's timezone. A naive datetime is assumed UTC — that
    is how the ingest pipeline stamps `received_at`. Degrades to the datetime's own date if the
    zone can't be loaded (e.g. missing tzdata) rather than crashing the poll."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    try:
        return dt.astimezone(ZoneInfo(tz_name)).date()
    except (ZoneInfoNotFoundError, ValueError):
        return dt.date()
