"""Tests for tools/query.py — PLAN.md Verification #3.

INSERT, UPDATE, DROP, PRAGMA, and two statements separated by a semicolon must all be
refused; a plain SELECT must work. Exercised against both a rw connection (isolates the
SQL-shape validation) and a ro connection (the real defence, per docs/adr/0006).
"""

import sqlite3

import pytest

from health_mcp.db import migrate, ro, rw
from health_mcp.tools.food import add_product
from health_mcp.tools.query import query


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "health.db"
    migrate(path)
    return path


@pytest.fixture
def writer(db_path):
    conn = rw(db_path)
    yield conn
    conn.close()


@pytest.fixture
def reader(db_path):
    conn = ro(db_path)
    yield conn
    conn.close()


def test_select_works(writer, reader):
    add_product(
        writer, name="Cottage cheese", kcal_100g=98, protein_100g=10,
        carbs_100g=3.4, fat_100g=4.3,
    )
    rows = query(reader, "SELECT name FROM products")
    assert [r["name"] for r in rows] == ["Cottage cheese"]


def test_with_cte_works(reader):
    rows = query(reader, "WITH x AS (SELECT 1 AS n) SELECT n FROM x")
    assert rows[0]["n"] == 1


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO sync_state (source) VALUES ('hevy')",
        "UPDATE sync_state SET cursor = '1'",
        "DELETE FROM sync_state",
        "DROP TABLE sync_state",
        "PRAGMA table_info(products)",
        "CREATE TABLE evil (id INTEGER)",
    ],
)
def test_non_select_rejected_by_shape_check(writer, sql):
    with pytest.raises(ValueError):
        query(writer, sql)


def test_two_statements_rejected(writer):
    with pytest.raises(ValueError):
        query(writer, "SELECT 1; DROP TABLE products")


def test_select_disguised_as_multi_statement_still_rejected(writer):
    with pytest.raises(ValueError):
        query(writer, "SELECT 1; SELECT 2")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO sync_state (source) VALUES ('hevy')",
        "DROP TABLE sync_state",
    ],
)
def test_writes_also_fail_at_the_connection_level_on_ro(db_path, sql):
    # Bypass the shape check to prove the ro() connection is the real defence.
    conn = ro(db_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(sql)
    finally:
        conn.close()


def test_read_only_pragma_is_not_blocked_by_the_connection_only_the_shape_check(db_path):
    # PRAGMA table_info is schema introspection, not a write — ro() alone lets it
    # through. query()'s shape check is what actually excludes PRAGMA, by design.
    conn = ro(db_path)
    try:
        conn.execute("PRAGMA table_info(products)").fetchall()
    finally:
        conn.close()


def test_leading_comment_before_select_is_allowed(reader):
    rows = query(reader, "-- a comment\nSELECT 1 AS n")
    assert rows[0]["n"] == 1
