"""Tests for steps.py.

CSV fixtures here only include the columns the importer actually reads — the real Apple
Health export carries several more (sourceVersion, device, endDate, ...) that are ignored.
"""

import csv

import pytest

from health_mcp import steps
from health_mcp.db import migrate, rw

HEADER = ["type", "sourceName", "startDate", "unit", "value"]


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


def row(source, start, value, unit="count", type_=steps.QUANTITY_TYPE):
    return [type_, source, start, unit, value]


# -- aggregation and dedup ----------------------------------------------------------


def test_import_sums_rows_within_a_source_and_day(tmp_path, conn):
    csv_path = tmp_path / "export.csv"
    write_csv(csv_path, [
        row("iPhone", "2026-08-10 09:00:00 +0000", "100"),
        row("iPhone", "2026-08-10 15:00:00 +0000", "50"),
    ])

    result = steps.import_csv(conn, csv_path)

    assert result["ok"] is True
    assert result["days"] == 1
    db_row = conn.execute("SELECT * FROM daily_steps").fetchone()
    assert db_row["date"] == "2026-08-10"
    assert db_row["steps"] == 150
    assert db_row["source"] == "iPhone"


def test_import_dedups_by_max_across_sources_not_sum(tmp_path, conn):
    """The measured problem: a phone and a watch each report their own full day of
    steps. Summing both would overcount — see docs/adr/0010."""
    csv_path = tmp_path / "export.csv"
    write_csv(csv_path, [
        row("iPhone", "2026-08-10 09:00:00 +0000", "4000"),
        row("Apple Watch", "2026-08-10 09:00:00 +0000", "9000"),
    ])

    steps.import_csv(conn, csv_path)

    db_row = conn.execute("SELECT * FROM daily_steps").fetchone()
    assert db_row["steps"] == 9000
    assert db_row["source"] == "Apple Watch"


def test_rows_read_counts_raw_csv_rows_not_days(tmp_path, conn):
    csv_path = tmp_path / "export.csv"
    write_csv(csv_path, [
        row("iPhone", "2026-08-10 09:00:00 +0000", "100"),
        row("iPhone", "2026-08-11 09:00:00 +0000", "200"),
        row("Apple Watch", "2026-08-11 09:00:00 +0000", "150"),
    ])

    result = steps.import_csv(conn, csv_path)

    assert result["rows_read"] == 3
    assert result["days"] == 2
    assert result["from"] == "2026-08-10"
    assert result["to"] == "2026-08-11"


# -- idempotency ----------------------------------------------------------------


def test_reimporting_the_same_file_does_not_duplicate_rows(tmp_path, conn):
    csv_path = tmp_path / "export.csv"
    write_csv(csv_path, [row("iPhone", "2026-08-10 09:00:00 +0000", "500")])

    steps.import_csv(conn, csv_path)
    result = steps.import_csv(conn, csv_path)

    assert result["days"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM daily_steps").fetchone()["c"] == 1


def test_reimport_overwrites_rather_than_accumulates(tmp_path, conn):
    csv_path = tmp_path / "export.csv"
    write_csv(csv_path, [row("iPhone", "2026-08-10 09:00:00 +0000", "500")])
    steps.import_csv(conn, csv_path)

    write_csv(csv_path, [row("iPhone", "2026-08-10 09:00:00 +0000", "700")])
    steps.import_csv(conn, csv_path)

    db_row = conn.execute("SELECT * FROM daily_steps").fetchone()
    assert db_row["steps"] == 700


# -- the Day rule ---------------------------------------------------------------


def test_a_sample_before_0400_amsterdam_lands_on_the_previous_day(tmp_path, conn):
    # 2026-01-10 01:30 UTC is 02:30 CET (winter, UTC+1) — before the 04:00 cutoff.
    csv_path = tmp_path / "export.csv"
    write_csv(csv_path, [row("iPhone", "2026-01-10 01:30:00 +0000", "10")])

    steps.import_csv(conn, csv_path)

    db_row = conn.execute("SELECT * FROM daily_steps").fetchone()
    assert db_row["date"] == "2026-01-09"


# -- export format quirks --------------------------------------------------------


def test_the_sep_hint_line_is_skipped(tmp_path, conn):
    csv_path = tmp_path / "export.csv"
    write_csv(csv_path, [row("iPhone", "2026-08-10 09:00:00 +0000", "10")], sep_line=True)

    result = steps.import_csv(conn, csv_path)
    assert result["days"] == 1


def test_an_export_without_the_sep_line_also_works(tmp_path, conn):
    csv_path = tmp_path / "export.csv"
    write_csv(csv_path, [row("iPhone", "2026-08-10 09:00:00 +0000", "10")], sep_line=False)

    result = steps.import_csv(conn, csv_path)
    assert result["days"] == 1


def test_an_empty_export_is_a_no_op(tmp_path, conn):
    csv_path = tmp_path / "export.csv"
    write_csv(csv_path, [])

    result = steps.import_csv(conn, csv_path)
    assert result == {"ok": True, "rows_read": 0, "days": 0, "from": None, "to": None}


# -- validation -------------------------------------------------------------------


def test_missing_columns_is_a_visible_error(tmp_path, conn):
    csv_path = tmp_path / "export.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["type", "sourceName", "startDate"])  # no unit, no value
        writer.writerow([steps.QUANTITY_TYPE, "iPhone", "2026-08-10 09:00:00 +0000"])

    with pytest.raises(steps.StepsError, match="expected columns"):
        steps.import_csv(conn, csv_path)


def test_wrong_unit_is_a_visible_error(tmp_path, conn):
    csv_path = tmp_path / "export.csv"
    write_csv(csv_path, [row("iPhone", "2026-08-10 09:00:00 +0000", "10", unit="km")])

    with pytest.raises(steps.StepsError, match="unit"):
        steps.import_csv(conn, csv_path)


def test_wrong_quantity_type_is_a_visible_error(tmp_path, conn):
    csv_path = tmp_path / "export.csv"
    write_csv(csv_path, [
        row("iPhone", "2026-08-10 09:00:00 +0000", "10",
            type_="HKQuantityTypeIdentifierHeartRate"),
    ])

    with pytest.raises(steps.StepsError, match="StepCount"):
        steps.import_csv(conn, csv_path)
