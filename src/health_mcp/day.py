"""The day rule.

A Day runs 04:00 to 04:00 `Europe/Amsterdam` — see docs/adr/0001. Every rollup groups by
it, so this module is the single place the rule is expressed. Nothing else should reach
for a timezone or a date.

The 04:00 cutoff has a second, quieter virtue beyond matching how a day is experienced:
EU clock changes happen between 02:00 and 03:00 local, so 04:00 local always exists and
is never ambiguous. Midnight would survive that too, but 04:00 has more headroom.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Amsterdam")
CUTOFF_HOUR = 4


def now_utc() -> datetime:
    """The current moment, timezone-aware and in UTC."""
    return datetime.now(timezone.utc)


def to_utc(moment: datetime) -> datetime:
    """Normalize a moment to aware UTC. Naive input is assumed to already be UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def day_of(moment: datetime) -> date:
    """The Day a moment belongs to.

    A meal at 01:00 belongs to the day that just ended, not the one that just began.
    """
    local = to_utc(moment).astimezone(ZONE)
    if local.hour < CUTOFF_HOUR:
        return (local - timedelta(days=1)).date()
    return local.date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """The half-open UTC interval `[start, end)` covering a Day.

    The inverse of `day_of`. Note that a Day spanning a clock change is 23 or 25 hours
    long, which is correct: it still starts and ends at 04:00 as lived.
    """
    start_local = datetime(day.year, day.month, day.day, CUTOFF_HOUR, tzinfo=ZONE)
    next_day = day + timedelta(days=1)
    end_local = datetime(next_day.year, next_day.month, next_day.day, CUTOFF_HOUR, tzinfo=ZONE)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
