"""Cadence-window matching (CLAUDE.md §5) — pure, no I/O. A recurring rule's `cadence` JSON
shape is ``{"kind": "weekly"|"biweekly"|"monthly", "slack_days": int}``. Given the rule's
`last_matched_at` and a candidate transaction's date, decides whether the candidate falls
inside the expected next-occurrence window.
"""

import datetime

CADENCE_KINDS = ("weekly", "biweekly", "monthly")

_INTERVAL_DAYS = {"weekly": 7, "biweekly": 14}


class InvalidCadence(ValueError):
    pass


def _add_one_month(d: datetime.date) -> datetime.date:
    """Same day next month, clamped to the last valid day (e.g. Jan 31 -> Feb 28)."""
    if d.month == 12:
        year, month = d.year + 1, 1
    else:
        year, month = d.year, d.month + 1
    for day in range(31, 27, -1):
        try:
            return datetime.date(year, month, min(d.day, day))
        except ValueError:
            continue
    raise AssertionError("unreachable — every month has at least 28 days")


def expected_next_date(last_matched: datetime.date, cadence: dict) -> datetime.date:
    kind = cadence.get("kind")
    if kind not in CADENCE_KINDS:
        raise InvalidCadence(f"Unknown cadence kind: {kind!r}")
    if kind == "monthly":
        return _add_one_month(last_matched)
    return last_matched + datetime.timedelta(days=_INTERVAL_DAYS[kind])


def is_within_cadence_window(
    last_matched: datetime.date, candidate: datetime.date, cadence: dict
) -> bool:
    """True if `candidate` falls within `slack_days` of the expected next occurrence after
    `last_matched`. A first-ever match (no prior `last_matched`) has nothing to compare
    against — callers should treat that case as "always route to review" rather than call
    this at all."""
    expected = expected_next_date(last_matched, cadence)
    slack = datetime.timedelta(days=cadence.get("slack_days", 0))
    return expected - slack <= candidate <= expected + slack
