"""Tests for the migration runner and the rw/ro connection split — see docs/adr/0006."""

import sqlite3

import pytest

from health_mcp.db import current_version, migrate, ro, rw

EXPECTED_TABLES = {
    "schema_version",
    "products",
    "food_log",
    "workouts",
    "exercise_templates",
    "workout_exercises",
    "workout_sets",
    "body_measurements",
    "sync_state",
    "activities",
    "daily_steps",
    "apple_workouts",
    "targets",
    "meals",
    "settings",
}


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "health.db"


def test_migrate_creates_all_tables(db_path):
    migrate(db_path)
    conn = rw(db_path)
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        conn.close()
    assert EXPECTED_TABLES <= names


def test_migrate_records_schema_version(db_path):
    migrate(db_path)
    conn = rw(db_path)
    try:
        assert current_version(conn) == 7
    finally:
        conn.close()


def test_migrate_is_idempotent(db_path):
    migrate(db_path)
    migrate(db_path)  # must not re-run 001-006 and fail on "table already exists"
    conn = rw(db_path)
    try:
        assert current_version(conn) == 7
    finally:
        conn.close()


def test_current_version_is_zero_before_any_migration(tmp_path):
    db_path = tmp_path / "fresh.db"
    conn = sqlite3.connect(db_path)
    try:
        assert current_version(conn) == 0
    finally:
        conn.close()


def test_rw_enables_foreign_keys(db_path):
    migrate(db_path)
    conn = rw(db_path)
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_ro_can_read_after_migration(db_path):
    migrate(db_path)
    conn = ro(db_path)
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        assert row["version"] == 1
    finally:
        conn.close()


def test_ro_rejects_writes(db_path):
    migrate(db_path)
    conn = ro(db_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO sync_state (source) VALUES ('hevy')"
            )
    finally:
        conn.close()


def test_rw_and_ro_see_the_same_writes(db_path):
    migrate(db_path)
    writer = rw(db_path)
    try:
        writer.execute("INSERT INTO sync_state (source) VALUES ('hevy')")
        writer.commit()
    finally:
        writer.close()

    reader = ro(db_path)
    try:
        row = reader.execute(
            "SELECT source FROM sync_state WHERE source = 'hevy'"
        ).fetchone()
        assert row["source"] == "hevy"
    finally:
        reader.close()
