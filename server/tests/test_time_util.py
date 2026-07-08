"""Owner-local date derivation (F18)."""

import datetime

from app.time_util import owner_local_date


def test_late_evening_month_end_files_under_owner_month_not_utc():
    # 2026-08-01 02:00 UTC is 2026-07-31 21:00 US-Central — the swipe belongs to JULY, not August.
    dt = datetime.datetime(2026, 8, 1, 2, 0, tzinfo=datetime.timezone.utc)
    assert owner_local_date(dt, "America/Chicago") == datetime.date(2026, 7, 31)


def test_naive_datetime_is_treated_as_utc():
    dt = datetime.datetime(2026, 8, 1, 2, 0)  # naive — the pipeline stamps received_at in UTC
    assert owner_local_date(dt, "America/Chicago") == datetime.date(2026, 7, 31)


def test_daytime_timestamp_is_unaffected():
    dt = datetime.datetime(2026, 7, 15, 18, 0, tzinfo=datetime.timezone.utc)  # midday, no rollover
    assert owner_local_date(dt, "America/Chicago") == datetime.date(2026, 7, 15)


def test_unknown_zone_degrades_to_the_datetime_date():
    dt = datetime.datetime(2026, 8, 1, 2, 0, tzinfo=datetime.timezone.utc)
    assert owner_local_date(dt, "Not/AZone") == datetime.date(2026, 8, 1)
