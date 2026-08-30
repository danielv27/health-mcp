"""Tests for tools/food.py — portion maths (PLAN.md Verification #2) and the write tools."""

from datetime import datetime, timezone

import pytest

from health_mcp.day import day_of, now_utc
from health_mcp.db import migrate, rw
from health_mcp.tools.food import (
    Macros,
    add_product,
    delete_food_entry,
    find_product,
    log_food,
    update_product,
)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "health.db"
    migrate(db_path)
    connection = rw(db_path)
    yield connection
    connection.close()


def make_product(conn, **overrides):
    defaults = dict(
        name="Cottage cheese",
        brand="Skyr Co",
        kcal_100g=98.0,
        protein_100g=10.0,
        carbs_100g=3.4,
        fat_100g=4.3,
        source="verified",
    )
    defaults.update(overrides)
    return add_product(conn, **defaults)


# -- add_product / find_product ----------------------------------------------


def test_add_product_returns_id_and_persists(conn):
    pid = make_product(conn)
    rows = find_product(conn)
    assert len(rows) == 1
    assert rows[0]["id"] == pid
    assert rows[0]["name"] == "Cottage cheese"


def test_add_product_rejects_bad_source(conn):
    with pytest.raises(ValueError):
        add_product(
            conn, name="X", kcal_100g=1, protein_100g=1, carbs_100g=1, fat_100g=1,
            source="guessed",
        )


def test_find_product_filters_by_name_or_brand(conn):
    make_product(conn, name="Cottage cheese", brand="Skyr Co")
    make_product(conn, name="Oat milk", brand="Alpro")

    assert [r["name"] for r in find_product(conn, "cottage")] == ["Cottage cheese"]
    assert [r["name"] for r in find_product(conn, "alpro")] == ["Oat milk"]
    assert len(find_product(conn)) == 2
    assert find_product(conn, "nonexistent") == []


# -- update_product ------------------------------------------------------------


def test_update_product_overwrites_only_given_fields(conn):
    pid = make_product(conn, protein_100g=6.9)
    update_product(conn, pid, protein_100g=12.0)

    row = find_product(conn)[0]
    assert row["protein_100g"] == 12.0
    assert row["name"] == "Cottage cheese"
    assert row["kcal_100g"] == 98.0


def test_update_product_rejects_bad_source(conn):
    pid = make_product(conn)
    with pytest.raises(ValueError):
        update_product(conn, pid, source="guessed")


def test_update_product_rejects_unknown_id(conn):
    with pytest.raises(ValueError):
        update_product(conn, 999, protein_100g=1.0)


def test_update_product_rejects_no_fields(conn):
    pid = make_product(conn)
    with pytest.raises(ValueError):
        update_product(conn, pid)


def test_update_product_relogs_already_logged_entries(conn):
    pid = make_product(conn, protein_100g=6.9)
    entry_id = log_food(conn, 120, product_id=pid)
    relogged = update_product(conn, pid, protein_100g=12.0)

    assert relogged == 1
    entry = conn.execute("SELECT protein FROM food_log WHERE id = ?", (entry_id,)).fetchone()
    assert entry["protein"] == pytest.approx(14.4)


def test_update_product_relog_uses_grams_unchanged(conn):
    pid = make_product(conn)
    entry_id = log_food(conn, 250, product_id=pid)
    update_product(conn, pid, kcal_100g=200.0)

    entry = conn.execute("SELECT grams, kcal FROM food_log WHERE id = ?", (entry_id,)).fetchone()
    assert entry["grams"] == 250
    assert entry["kcal"] == pytest.approx(500.0)


def test_update_product_returns_zero_when_no_entries_logged(conn):
    pid = make_product(conn)
    assert update_product(conn, pid, protein_100g=1.0) == 0


# -- log_food: portion maths --------------------------------------------------


def test_log_food_scales_macros_by_grams_exactly(conn):
    pid = make_product(
        conn, name="Test protein", kcal_100g=50.0, protein_100g=10.0,
        carbs_100g=5.0, fat_100g=2.0,
    )
    entry_id = log_food(conn, grams=200, product_id=pid)

    row = conn.execute("SELECT * FROM food_log WHERE id = ?", (entry_id,)).fetchone()
    assert row["protein"] == 20.0
    assert row["kcal"] == 100.0
    assert row["carbs"] == 10.0
    assert row["fat"] == 4.0
    assert row["grams"] == 200


def test_log_food_against_product_copies_name_and_source(conn):
    pid = make_product(conn, name="Cottage cheese", source="verified")
    entry_id = log_food(conn, grams=150, product_id=pid)
    row = conn.execute("SELECT * FROM food_log WHERE id = ?", (entry_id,)).fetchone()
    assert row["name"] == "Cottage cheese"
    assert row["source"] == "verified"
    assert row["product_id"] == pid


def test_log_food_one_off_is_always_estimated(conn):
    macros = Macros(kcal_100g=89.0, protein_100g=1.1, carbs_100g=22.8, fat_100g=0.3)
    entry_id = log_food(conn, grams=118, name="Banana", macros=macros, entered_as="1 banana")
    row = conn.execute("SELECT * FROM food_log WHERE id = ?", (entry_id,)).fetchone()
    assert row["source"] == "estimated"
    assert row["product_id"] is None
    assert row["name"] == "Banana"
    assert row["entered_as"] == "1 banana"
    assert row["protein"] == pytest.approx(1.1 * 1.18)


def test_log_food_requires_exactly_one_of_product_id_or_macros(conn):
    with pytest.raises(ValueError):
        log_food(conn, grams=100)
    pid = make_product(conn)
    with pytest.raises(ValueError):
        log_food(
            conn, grams=100, product_id=pid,
            macros=Macros(kcal_100g=1, protein_100g=1, carbs_100g=1, fat_100g=1),
        )


def test_log_food_one_off_requires_name(conn):
    with pytest.raises(ValueError):
        log_food(
            conn, grams=100,
            macros=Macros(kcal_100g=1, protein_100g=1, carbs_100g=1, fat_100g=1),
        )


def test_log_food_rejects_unknown_product_id(conn):
    with pytest.raises(ValueError):
        log_food(conn, grams=100, product_id=9999)


# -- log_food: the 04:00 day rule applied at write time -----------------------


def test_log_food_computes_date_via_04_00_rule(conn):
    # 01:30 UTC on 2026-06-15 is 03:30 Amsterdam (CEST) — before the cutoff, so the 14th.
    at = datetime(2026, 6, 15, 1, 30, tzinfo=timezone.utc)
    pid = make_product(conn)
    entry_id = log_food(conn, grams=100, product_id=pid, at=at)
    row = conn.execute("SELECT date, logged_at FROM food_log WHERE id = ?", (entry_id,)).fetchone()
    assert row["date"] == "2026-06-14"
    assert row["logged_at"] == at.isoformat()


def test_log_food_defaults_to_now(conn):
    pid = make_product(conn)
    entry_id = log_food(conn, grams=100, product_id=pid)
    row = conn.execute("SELECT date FROM food_log WHERE id = ?", (entry_id,)).fetchone()
    assert row["date"] == day_of(now_utc()).isoformat()


# -- delete_food_entry ---------------------------------------------------------


def test_delete_food_entry_removes_row(conn):
    pid = make_product(conn)
    entry_id = log_food(conn, grams=100, product_id=pid)
    delete_food_entry(conn, entry_id)
    assert conn.execute("SELECT * FROM food_log WHERE id = ?", (entry_id,)).fetchone() is None


def test_delete_food_entry_rejects_unknown_id(conn):
    with pytest.raises(ValueError):
        delete_food_entry(conn, 9999)
