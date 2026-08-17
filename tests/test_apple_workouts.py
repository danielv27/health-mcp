"""Tests for apple_workouts.py.

CSV fixtures only include the columns the importer reads — the real export carries
several more (sourceVersion, device, HKTimeZone, ...) that are ignored.
"""

import csv

import pytest

from health_mcp import apple_workouts
from health_mcp.db import migrate, rw

HEADER = [
    "type", "sourceName", "activityType", "startDate", "endDate",
    "duration", "durationUnit", "totalEnergyBurned", "totalDistance",
]


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "health.db"
    migrate(db_path)
    connection = rw(db_path)
    yield connection
    connection.close()


def write_csv(path, rows, sep_line=True):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        if sep_line:
            fh.write("sep=,\n")
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        for r in rows:
            writer.writerow(r)


def row(source, activity_type, start, end, duration_s, energy="", distance="",
        type_=apple_workouts.WORKOUT_TYPE_IDENTIFIER, duration_unit="sec"):
    return [type_, source, activity_type, start, end, duration_s, duration_unit,
            energy, distance]


# -- Hevy exclusion (the whole point) --------------------------------------------


def test_hevy_sourced_rows_are_excluded(tmp_path, conn):
    csv_path = tmp_path / "strength.csv"
    write_csv(csv_path, [
        row("Hevy", "TraditionalStrengthTraining",
            "2026-08-10 09:00:00 +0000", "2026-08-10 09:45:00 +0000", 2700),
        row("Daniel’s Apple\xa0Watch", "TraditionalStrengthTraining",
            "2025-03-06 21:35:52 +0000", "2025-03-06 22:35:50 +0000", 3598),
    ])

    result = apple_workouts.import_csv(conn, csv_path)

    assert result["rows_read"] == 2
    assert result["imported"] == 1
    assert result["skipped_hevy"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM apple_workouts").fetchone()["c"] == 1
    remaining = conn.execute("SELECT * FROM apple_workouts").fetchone()
    assert remaining["source"] == "Apple Watch"


# -- source normalization ---------------------------------------------------------


@pytest.mark.parametrize("raw_source", [
    "Daniel’s Apple\xa0Watch", "daniel’s Apple\xa0Watch", "Apple Watch",
])
def test_watch_name_variants_normalize_to_one_source(tmp_path, conn, raw_source):
    csv_path = tmp_path / "cycling.csv"
    write_csv(csv_path, [
        row(raw_source, "Cycling", "2026-08-10 09:00:00 +0000",
            "2026-08-10 09:40:00 +0000", 2400),
    ])

    apple_workouts.import_csv(conn, csv_path)

    db_row = conn.execute("SELECT * FROM apple_workouts").fetchone()
    assert db_row["source"] == "Apple Watch"


def test_strava_source_is_kept(tmp_path, conn):
    csv_path = tmp_path / "running.csv"
    write_csv(csv_path, [
        row("Strava", "Running", "2026-06-04 16:49:30 +0000",
            "2026-06-04 17:02:20 +0000", 770, energy="60.5 kcal", distance="2422 m"),
    ])

    apple_workouts.import_csv(conn, csv_path)

    db_row = conn.execute("SELECT * FROM apple_workouts").fetchone()
    assert db_row["source"] == "Strava"
    assert db_row["workout_type"] == "Running"
    assert db_row["distance_m"] == 2422.0
    assert db_row["energy_kcal"] == 60.5


def test_unrecognized_source_is_a_visible_error(tmp_path, conn):
    csv_path = tmp_path / "running.csv"
    write_csv(csv_path, [
        row("Nike Run Club", "Running", "2026-08-10 09:00:00 +0000",
            "2026-08-10 09:20:00 +0000", 1200),
    ])

    with pytest.raises(apple_workouts.AppleWorkoutError, match="unrecognized"):
        apple_workouts.import_csv(conn, csv_path)


# -- quantity parsing ---------------------------------------------------------------


def test_a_row_without_energy_or_distance_stores_null(tmp_path, conn):
    csv_path = tmp_path / "strength.csv"
    write_csv(csv_path, [
        row("Apple Watch", "TraditionalStrengthTraining", "2026-08-10 09:00:00 +0000",
            "2026-08-10 09:45:00 +0000", 2700, energy="", distance=""),
    ])

    apple_workouts.import_csv(conn, csv_path)

    db_row = conn.execute("SELECT * FROM apple_workouts").fetchone()
    assert db_row["energy_kcal"] is None
    assert db_row["distance_m"] is None


# -- multi-file import, idempotency -------------------------------------------------


def test_multiple_files_import_in_one_call(tmp_path, conn):
    cycling = tmp_path / "cycling.csv"
    write_csv(cycling, [
        row("Apple Watch", "Cycling", "2026-08-10 09:00:00 +0000",
            "2026-08-10 09:40:00 +0000", 2400),
    ])
    running = tmp_path / "running.csv"
    write_csv(running, [
        row("Strava", "Running", "2026-08-11 09:00:00 +0000",
            "2026-08-11 09:20:00 +0000", 1200),
    ])

    result = apple_workouts.import_csv(conn, [cycling, running])

    assert result["imported"] == 2
    assert result["by_type"] == {"Cycling": 1, "Running": 1}


def test_reimporting_the_same_file_does_not_duplicate_rows(tmp_path, conn):
    csv_path = tmp_path / "cycling.csv"
    write_csv(csv_path, [
        row("Apple Watch", "Cycling", "2026-08-10 09:00:00 +0000",
            "2026-08-10 09:40:00 +0000", 2400),
    ])

    apple_workouts.import_csv(conn, csv_path)
    result = apple_workouts.import_csv(conn, csv_path)

    assert result["imported"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM apple_workouts").fetchone()["c"] == 1


# -- the Day rule, and validation -----------------------------------------------


def test_a_session_before_0400_amsterdam_lands_on_the_previous_day(tmp_path, conn):
    csv_path = tmp_path / "cycling.csv"
    write_csv(csv_path, [
        row("Apple Watch", "Cycling", "2026-01-10 01:30:00 +0000",
            "2026-01-10 02:00:00 +0000", 1800),
    ])

    apple_workouts.import_csv(conn, csv_path)

    db_row = conn.execute("SELECT * FROM apple_workouts").fetchone()
    assert db_row["date"] == "2026-01-09"


def test_wrong_workout_type_identifier_is_a_visible_error(tmp_path, conn):
    csv_path = tmp_path / "cycling.csv"
    write_csv(csv_path, [
        row("Apple Watch", "Cycling", "2026-08-10 09:00:00 +0000",
            "2026-08-10 09:40:00 +0000", 2400, type_="HKQuantityTypeIdentifierStepCount"),
    ])

    with pytest.raises(apple_workouts.AppleWorkoutError, match="WorkoutTypeIdentifier"):
        apple_workouts.import_csv(conn, csv_path)


def test_wrong_duration_unit_is_a_visible_error(tmp_path, conn):
    csv_path = tmp_path / "cycling.csv"
    write_csv(csv_path, [
        row("Apple Watch", "Cycling", "2026-08-10 09:00:00 +0000",
            "2026-08-10 09:40:00 +0000", 40, duration_unit="min"),
    ])

    with pytest.raises(apple_workouts.AppleWorkoutError, match="durationUnit"):
        apple_workouts.import_csv(conn, csv_path)


def test_missing_columns_is_a_visible_error(tmp_path, conn):
    csv_path = tmp_path / "cycling.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["type", "sourceName", "activityType"])
        writer.writerow([apple_workouts.WORKOUT_TYPE_IDENTIFIER, "Apple Watch", "Cycling"])

    with pytest.raises(apple_workouts.AppleWorkoutError, match="expected columns"):
        apple_workouts.import_csv(conn, csv_path)
