"""Daily step counts, from Apple Health CSV exports (the "Simple Health Export CSV" app,
or equivalent — any exporter producing HealthKit's standard `HKQuantityTypeIdentifier
StepCount` CSV columns works: `startDate`, `sourceName`, `unit`, `value`).

There's no API and no cursor here, unlike hevy.py/strava.py — this is a file dropped in by
hand, whenever a fresh export is available. `import_csv` always reprocesses the whole file
and upserts by date, so re-importing an overlapping or repeated export is harmless.

The one real judgment call: a phone and a watch worn on the same day each report their own
full step count, and naively summing every source double-counts — measured at +19% on a
real 9-year export. Each day's count is the *max* of any single source's daily total, not
a sum across sources. See docs/adr/0010.
"""

import csv
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from health_mcp.day import day_of

QUANTITY_TYPE = "HKQuantityTypeIdentifierStepCount"


class StepsError(RuntimeError):
    """A CSV didn't look like the expected step-count export."""


def import_csv(conn: sqlite3.Connection, path: str | Path) -> dict:
    """Aggregate `path` into `daily_steps` and upsert. Returns row/day counts and the
    date range touched."""
    daily, rows_read = _aggregate(path)
    if not daily:
        return {"ok": True, "rows_read": rows_read, "days": 0, "from": None, "to": None}

    for date, per_source in daily.items():
        source, steps = max(per_source.items(), key=lambda item: item[1])
        conn.execute(
            """
            INSERT INTO daily_steps (date, steps, source) VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET steps = excluded.steps, source = excluded.source
            """,
            (date, round(steps), source),
        )
    conn.commit()

    dates = sorted(daily)
    return {
        "ok": True,
        "rows_read": rows_read,
        "days": len(daily),
        "from": dates[0],
        "to": dates[-1],
    }


def _aggregate(path: str | Path) -> tuple[dict[str, dict[str, float]], int]:
    """`{date: {source: total_steps}}`, summing raw samples within a (Day, source) pair,
    and the count of raw CSV rows read."""
    daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    rows_read = 0
    with open(path, newline="", encoding="utf-8") as fh:
        # Excel-style exports lead with a `sep=,` hint line before the real header.
        first = fh.readline()
        if not first.startswith("sep="):
            fh.seek(0)

        reader = csv.DictReader(fh)
        required = {"type", "sourceName", "startDate", "unit", "value"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise StepsError(f"expected columns {sorted(required)}, got {reader.fieldnames}")

        for row in reader:
            if row["type"] != QUANTITY_TYPE:
                raise StepsError(f"expected only {QUANTITY_TYPE} rows, found {row['type']!r}")
            if row["unit"] != "count":
                raise StepsError(f"expected unit 'count', got {row['unit']!r}")

            start = datetime.strptime(row["startDate"], "%Y-%m-%d %H:%M:%S %z")
            date = day_of(start).isoformat()
            daily[date][row["sourceName"]] += float(row["value"])
            rows_read += 1

    return daily, rows_read
