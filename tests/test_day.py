"""Tests for the 04:00 Europe/Amsterdam day rule — see docs/adr/0001.

Covers the boundary itself (03:59 vs 04:01 local), both DST changeovers, and the
day_of / day_bounds round trip.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from health_mcp.day import ZONE, day_bounds, day_of, now_utc, to_utc

AMS = ZoneInfo("Europe/Amsterdam")


def local(y, mo, d, h, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=AMS)


# -- the boundary itself -----------------------------------------------------


def test_03_59_belongs_to_previous_day():
    assert day_of(local(2026, 6, 15, 3, 59)) == date(2026, 6, 14)


def test_04_00_exactly_belongs_to_new_day():
    assert day_of(local(2026, 6, 15, 4, 0)) == date(2026, 6, 15)


def test_04_01_belongs_to_new_day():
    assert day_of(local(2026, 6, 15, 4, 1)) == date(2026, 6, 15)


def test_just_before_midnight_belongs_to_that_calendar_day():
    assert day_of(local(2026, 6, 15, 23, 59)) == date(2026, 6, 15)


# -- DST: spring forward (clocks jump 02:00 CET -> 03:00 CEST on 2026-03-29) -
#
# The jump itself happens at 02:00-03:00 local, which is *before* the 04:00
# cutoff on the 29th — so it falls inside the Day that starts 04:00 on the
# 28th, not the Day that starts 04:00 on the 29th. The 28th is the 23-hour Day.


def test_day_of_across_spring_forward():
    # 01:00 local on the 29th, before the jump and before the cutoff -> the 28th.
    assert day_of(local(2026, 3, 29, 1, 0)) == date(2026, 3, 28)
    # 04:00 local always exists even though 02:00-03:00 is skipped.
    assert day_of(local(2026, 3, 29, 4, 0)) == date(2026, 3, 29)


def test_day_bounds_spring_forward_day_is_23_hours():
    start, end = day_bounds(date(2026, 3, 28))
    assert start.tzinfo is timezone.utc
    assert end.tzinfo is timezone.utc
    assert end - start == timedelta(hours=23)
    # 04:00 CET on the 28th is 03:00 UTC; 04:00 CEST on the 29th is 02:00 UTC.
    assert start == datetime(2026, 3, 28, 3, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 3, 29, 2, 0, tzinfo=timezone.utc)


# -- DST: fall back (clocks jump 03:00 CEST -> 02:00 CET on 2026-10-25) -----
#
# Same reasoning: the jump is before the 04:00 cutoff on the 25th, so it falls
# inside the Day that starts 04:00 on the 24th. The 24th is the 25-hour Day.


def test_day_of_across_fall_back():
    assert day_of(local(2026, 10, 25, 3, 59)) == date(2026, 10, 24)
    assert day_of(local(2026, 10, 25, 4, 0)) == date(2026, 10, 25)


def test_day_bounds_fall_back_day_is_25_hours():
    start, end = day_bounds(date(2026, 10, 24))
    assert end - start == timedelta(hours=25)
    # 04:00 CEST on the 24th is 02:00 UTC; 04:00 CET on the 25th is 03:00 UTC.
    assert start == datetime(2026, 10, 24, 2, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc)


# -- day_bounds is the inverse of day_of -------------------------------------


def test_day_bounds_round_trips_through_day_of():
    for d in (date(2026, 1, 1), date(2026, 3, 28), date(2026, 10, 24), date(2026, 12, 31)):
        start, end = day_bounds(d)
        assert day_of(start) == d
        assert day_of(end - timedelta(microseconds=1)) == d
        # end is exclusive: it belongs to the next day.
        assert day_of(end) != d


def test_day_bounds_covers_whole_day_no_gaps_no_overlap():
    d = date(2026, 6, 15)
    _, end = day_bounds(d)
    next_start, _ = day_bounds(d + timedelta(days=1))
    assert end == next_start


# -- to_utc / now_utc ---------------------------------------------------------


def test_to_utc_assumes_naive_is_already_utc():
    naive = datetime(2026, 6, 15, 12, 0, 0)
    assert to_utc(naive) == datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_to_utc_converts_aware_non_utc():
    amsterdam_noon = local(2026, 6, 15, 12, 0)  # CEST = UTC+2
    assert to_utc(amsterdam_noon) == datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)


def test_now_utc_is_aware_and_utc():
    moment = now_utc()
    assert moment.tzinfo is timezone.utc


def test_day_of_accepts_utc_moment_directly():
    # 01:30 UTC on 2026-06-15 is 03:30 CEST -> before cutoff -> previous day.
    moment = datetime(2026, 6, 15, 1, 30, tzinfo=timezone.utc)
    assert day_of(moment) == date(2026, 6, 14)


def test_zone_is_amsterdam():
    assert ZONE.key == "Europe/Amsterdam"
