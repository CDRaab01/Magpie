"""The injected clock seam (CLAUDE.md §9): everything interesting in `app/rules/` is
time-dependent — cadence windows, band aging, auth-hold expiry, freshness alerts — so nothing
here may call `datetime.now()` directly. Production wires `SystemClock`; tests use a fixed
callable and get real time-travel tests for free (advance the fake, assert the behavior
changes) instead of racing the real clock.
"""

import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime.datetime: ...


class SystemClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)


class FixedClock:
    """Test double — always returns the same instant unless explicitly advanced."""

    def __init__(self, at: datetime.datetime):
        self._at = at

    def now(self) -> datetime.datetime:
        return self._at

    def advance(self, delta: datetime.timedelta) -> None:
        self._at = self._at + delta
