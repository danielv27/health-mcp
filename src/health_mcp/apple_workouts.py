"""Apple Health workout sessions, from CSV exports (the "Simple Health Export CSV" app
exports one file per `HKWorkoutActivityType`, e.g. Running, Cycling, Walking — this module
takes any number of them together).

The one thing worth getting right: Hevy also writes its workouts into HealthKit
(`sourceName == 'Hevy'`), so an unfiltered import of this export would duplicate every
strength session already pulled in directly from the Hevy API (`workouts`/ADR-0003 "own
the data"). Rows sourced from Hevy are dropped at import time, not just tagged — see
docs/adr/0011.

No API and no cursor, same as steps.py — a file dropped in by hand, always reprocessed
and upserted whole.
"""

import csv
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from health_mcp.day import day_of

WORKOUT_TYPE_IDENTIFIER = "HKWorkoutTypeIdentifier"


class AppleWorkoutError(RuntimeError):
    """A CSV didn't look like the expected workout export."""


def import_csv(conn: sqlite3.Connection, paths: str | Path | list[str | Path]) -> dict:
    """Aggregate one or more per-type CSVs into `apple_workouts` and upsert. Rows sourced
    from Hevy are dropped, not stored — see module docstring."""
    if isinstance(paths, (str, Path)):
        paths = [paths]

    rows: list[dict] = []
    for path in paths:
        rows.extend(_read_rows(path))

    kept = [row for row in rows if row["source"] != "Hevy"]
    for row in kept:
        conn.execute(
            """
            INSERT INTO apple_workouts (id, source, workout_type, start_date, end_date,
                date, duration_s, energy_kcal, distance_m)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source = excluded.source, workout_type = excluded.workout_type,
                start_date = excluded.start_date, end_date = excluded.end_date,
                date = excluded.date, duration_s = excluded.duration_s,
                energy_kcal = excluded.energy_kcal, distance_m = excluded.distance_m
            """,
            (row["id"], row["source"], row["workout_type"], row["start_date"],
             row["end_date"], row["date"], row["duration_s"], row["energy_kcal"],
             row["distance_m"]),
        )
    conn.commit()

    by_type: dict[str, int] = {}
    for row in kept:
        by_type[row["workout_type"]] = by_type.get(row["workout_type"], 0) + 1

    return {
        "ok": True,
        "rows_read": len(rows),
        "imported": len(kept),
        "skipped_hevy": len(rows) - len(kept),
        "by_type": by_type,
    }


def _read_rows(path: str | Path) -> list[dict]:
    required = {
        "type", "sourceName", "activityType", "startDate", "endDate",
        "duration", "durationUnit",
    }
    with open(path, newline="", encoding="utf-8") as fh:
        first = fh.readline()
        if not first.startswith("sep="):
            fh.seek(0)

        reader = csv.DictReader(fh)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise AppleWorkoutError(f"expected columns {sorted(required)}, got {reader.fieldnames}")

        rows = []
        for raw in reader:
            if raw["type"] != WORKOUT_TYPE_IDENTIFIER:
                raise AppleWorkoutError(
                    f"expected only {WORKOUT_TYPE_IDENTIFIER} rows, found {raw['type']!r}"
                )
            if raw["durationUnit"] != "sec":
                raise AppleWorkoutError(f"expected durationUnit 'sec', got {raw['durationUnit']!r}")

            source = _normalize_source(raw["sourceName"])
            start = datetime.strptime(raw["startDate"], "%Y-%m-%d %H:%M:%S %z")
            rows.append({
                # Truncated to the minute: re-exports of the same workout (and Strava's
                # own occasional double-post of one activity) land within a second or two
                # of each other but rarely cross a minute boundary, so this is what lets
                # the upsert collide onto the same row instead of drifting into a new one.
                "id": f"{source}:{start.strftime('%Y-%m-%d %H:%M')}",
                "source": source,
                "workout_type": raw["activityType"],
                "start_date": raw["startDate"],
                "end_date": raw["endDate"],
                "date": day_of(start).isoformat(),
                "duration_s": float(raw["duration"]),
                "energy_kcal": _parse_quantity(raw.get("totalEnergyBurned")),
                "distance_m": _parse_quantity(raw.get("totalDistance")),
            })
    return rows


def _normalize_source(name: str) -> str:
    lowered = name.lower()
    if "hevy" in lowered:
        return "Hevy"
    if "strava" in lowered:
        return "Strava"
    if "watch" in lowered:
        return "Apple Watch"
    raise AppleWorkoutError(f"unrecognized workout source: {name!r}")


def _parse_quantity(value: str | None) -> float | None:
    """Apple's export embeds the unit in the value itself, e.g. `'127.734 kcal'` or
    `'1637.06 m'` — units are consistent (always kcal / m) but the number needs pulling
    out regardless."""
    if not value or not value.strip():
        return None
    match = re.match(r"(-?[\d.]+)", value.strip())
    if not match:
        raise AppleWorkoutError(f"unparseable quantity: {value!r}")
    return float(match.group(1))
