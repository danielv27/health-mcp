"""Tests for tools/targets.py."""

import pytest

from health_mcp.db import migrate, rw
from health_mcp.tools.targets import get_targets, set_targets


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "health.db"
    migrate(db_path)
    connection = rw(db_path)
    yield connection
    connection.close()


def test_get_targets_absent_by_default(conn):
    assert get_targets(conn) is None


def test_set_then_get_targets(conn):
    row = set_targets(conn, kcal=2400, protein=180, carbs=250, fat=80)
    assert row["kcal"] == 2400
    assert row["protein"] == 180

    fetched = get_targets(conn)
    assert fetched["kcal"] == 2400
    assert fetched["fat"] == 80


def test_set_targets_overwrites_single_row(conn):
    set_targets(conn, kcal=2400, protein=180, carbs=250, fat=80)
    set_targets(conn, kcal=2600, protein=190, carbs=260, fat=85)

    row = get_targets(conn)
    assert row["kcal"] == 2600
    assert row["protein"] == 190
    assert conn.execute("SELECT COUNT(*) FROM targets").fetchone()[0] == 1
