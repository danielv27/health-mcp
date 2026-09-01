"""Tests for tools/meals.py — added after /impeccable critique found food is never
logged standalone; a meal groups several Food Log Entries in one atomic commit."""

import time_machine
import pytest

from health_mcp.db import migrate, rw
from health_mcp.tools.food import Macros, add_product, delete_food_entry
from health_mcp.tools.meals import MealItem, delete_meal, infer_meal_type, log_meal


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "health.db"
    migrate(db_path)
    connection = rw(db_path)
    yield connection
    connection.close()


def make_product(conn, **overrides):
    defaults = dict(
        name="Oats", kcal_100g=389.0, protein_100g=17.0, carbs_100g=66.0,
        fat_100g=7.0, source="verified",
    )
    defaults.update(overrides)
    return add_product(conn, **defaults)


def test_log_meal_creates_meal_and_all_entries(conn):
    product_id = make_product(conn)
    result = log_meal(
        conn,
        meal_type="breakfast",
        items=[
            MealItem(grams=100, product_id=product_id),
            MealItem(
                grams=150,
                name="Banana",
                macros=Macros(kcal_100g=89, protein_100g=1.1, carbs_100g=23, fat_100g=0.3),
            ),
        ],
    )
    assert result["meal_id"] is not None
    assert len(result["entry_ids"]) == 2

    meal = conn.execute("SELECT * FROM meals WHERE id = ?", (result["meal_id"],)).fetchone()
    assert meal["meal_type"] == "breakfast"

    entries = conn.execute(
        "SELECT * FROM food_log WHERE meal_id = ? ORDER BY id", (result["meal_id"],)
    ).fetchall()
    assert len(entries) == 2
    assert entries[0]["name"] == "Oats"
    assert entries[1]["name"] == "Banana"


def test_log_meal_rejects_unknown_meal_type(conn):
    with pytest.raises(ValueError):
        log_meal(conn, meal_type="brunch", items=[MealItem(grams=100, name="x", macros=Macros(kcal_100g=1, protein_100g=1, carbs_100g=1, fat_100g=1))])
    assert conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0] == 0


def test_log_meal_requires_at_least_one_item(conn):
    with pytest.raises(ValueError):
        log_meal(conn, meal_type="snack", items=[])


def test_log_meal_is_atomic_on_bad_item(conn):
    """One item referencing a nonexistent product must not leave a partial meal
    behind — the whole commit rolls back."""
    with pytest.raises(ValueError):
        log_meal(
            conn,
            meal_type="lunch",
            items=[
                MealItem(
                    grams=100,
                    name="Rice",
                    macros=Macros(kcal_100g=130, protein_100g=2.7, carbs_100g=28, fat_100g=0.3),
                ),
                MealItem(grams=100, product_id=9999),
            ],
        )
    assert conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM food_log").fetchone()[0] == 0


def test_delete_meal_removes_meal_and_its_entries(conn):
    result = log_meal(
        conn,
        meal_type="dinner",
        items=[MealItem(grams=100, name="x", macros=Macros(kcal_100g=1, protein_100g=1, carbs_100g=1, fat_100g=1))],
    )
    delete_meal(conn, result["meal_id"])
    assert conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM food_log").fetchone()[0] == 0


def test_delete_meal_missing_raises(conn):
    with pytest.raises(ValueError):
        delete_meal(conn, 999)


def test_deleting_last_entry_of_a_meal_leaves_an_empty_meal(conn):
    """delete_food_entry deliberately does not cascade-delete the meal — see its
    docstring. web/app.py's /api/today is what hides an empty meal from the UI."""
    result = log_meal(
        conn,
        meal_type="snack",
        items=[MealItem(grams=30, name="Almonds", macros=Macros(kcal_100g=579, protein_100g=21, carbs_100g=22, fat_100g=50))],
    )
    entry_id = result["entry_ids"][0]
    delete_food_entry(conn, entry_id)
    assert conn.execute("SELECT COUNT(*) FROM meals WHERE id = ?", (result["meal_id"],)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM food_log WHERE meal_id = ?", (result["meal_id"],)).fetchone()[0] == 0


def test_deleting_one_of_several_entries_keeps_the_meal(conn):
    result = log_meal(
        conn,
        meal_type="lunch",
        items=[
            MealItem(grams=100, name="a", macros=Macros(kcal_100g=1, protein_100g=1, carbs_100g=1, fat_100g=1)),
            MealItem(grams=100, name="b", macros=Macros(kcal_100g=1, protein_100g=1, carbs_100g=1, fat_100g=1)),
        ],
    )
    delete_food_entry(conn, result["entry_ids"][0])
    assert conn.execute("SELECT COUNT(*) FROM meals WHERE id = ?", (result["meal_id"],)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM food_log WHERE meal_id = ?", (result["meal_id"],)).fetchone()[0] == 1


@pytest.mark.parametrize(
    "hour,expected",
    [(6, "breakfast"), (10, "breakfast"), (12, "lunch"), (14, "lunch"), (18, "dinner"), (20, "dinner"), (22, "snack"), (2, "snack")],
)
def test_infer_meal_type_by_local_hour(hour, expected):
    # Amsterdam is UTC+1 or +2; pin a date well clear of any DST transition and
    # drive the UTC hour so the local hour lands exactly on `hour`.
    with time_machine.travel(f"2026-01-15T{(hour - 1) % 24:02d}:00:00Z"):
        assert infer_meal_type() == expected
