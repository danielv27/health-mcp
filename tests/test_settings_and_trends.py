import time_machine

from health_mcp.db import migrate, rw
from health_mcp.tools import trends
from health_mcp.tools.food import Macros
from health_mcp.tools.meals import MealItem, log_meal
from health_mcp.tools.settings import get_settings, set_hevy_auto_sync


def test_settings_default_off(tmp_path):
    db_path = tmp_path / "health.db"
    migrate(db_path)
    conn = rw(db_path)
    try:
        assert get_settings(conn)["hevy_auto_sync"] == 0
    finally:
        conn.close()


def test_set_hevy_auto_sync_round_trips(tmp_path):
    db_path = tmp_path / "health.db"
    migrate(db_path)
    conn = rw(db_path)
    try:
        row = set_hevy_auto_sync(conn, True)
        assert row["hevy_auto_sync"] == 1
        row = set_hevy_auto_sync(conn, False)
        assert row["hevy_auto_sync"] == 0
    finally:
        conn.close()


def test_food_trends_averages_by_week(tmp_path):
    db_path = tmp_path / "health.db"
    migrate(db_path)
    conn = rw(db_path)
    try:
        with time_machine.travel("2026-06-01T12:00:00Z", tick=False):
            log_meal(
                conn,
                meal_type="lunch",
                items=[MealItem(grams=100, name="Rice", macros=Macros(kcal_100g=130, protein_100g=3, carbs_100g=28, fat_100g=0.3))],
            )
        rows = trends.food_trends(conn, weeks=52)
        assert len(rows) == 1
        assert rows[0]["kcal_avg"] == 130.0
        assert rows[0]["days_logged"] == 1
    finally:
        conn.close()


def test_weight_trend_empty_when_no_measurements(tmp_path):
    db_path = tmp_path / "health.db"
    migrate(db_path)
    conn = rw(db_path)
    try:
        assert trends.weight_trend(conn, weeks=12) == []
    finally:
        conn.close()


def test_intake_vs_training_merges_both_series(tmp_path):
    db_path = tmp_path / "health.db"
    migrate(db_path)
    conn = rw(db_path)
    try:
        with time_machine.travel("2026-06-01T12:00:00Z", tick=False):
            log_meal(
                conn,
                meal_type="lunch",
                items=[MealItem(grams=100, name="Rice", macros=Macros(kcal_100g=130, protein_100g=3, carbs_100g=28, fat_100g=0.3))],
            )
        rows = trends.intake_vs_training(conn, weeks=52)
        assert len(rows) == 1
        assert rows[0]["kcal_avg"] == 130.0
        assert rows[0]["sessions"] == 0
    finally:
        conn.close()
