"""Aggregate read-only rollups backing the web UI's trends dashboard.

Everything here is derived from data already written by food.py/meals.py (food_log),
hevy.py (workouts/workout_exercises/workout_sets) and body_measurements — no new
storage, just weekly/date-bucketed aggregation queries against a `db.ro()` connection.
Weeks are ISO weeks (`strftime('%Y-W%W', date)`), keyed by their Monday.
"""

import sqlite3

_WEEK_KEY = "strftime('%Y-%W', date)"
_WEEK_START = "date(date, '-' || ((strftime('%w', date) + 6) % 7) || ' days')"


def food_trends(conn: sqlite3.Connection, weeks: int) -> list[dict]:
    rows = conn.execute(
        f"""
        SELECT
            {_WEEK_START} AS week_start,
            SUM(kcal) AS kcal,
            SUM(protein) AS protein,
            SUM(carbs) AS carbs,
            SUM(fat) AS fat,
            COUNT(DISTINCT date) AS days_logged
        FROM food_log
        WHERE date >= date('now', ?)
        GROUP BY {_WEEK_KEY}
        ORDER BY week_start
        """,
        (f"-{weeks * 7} days",),
    ).fetchall()
    return [
        {
            "week_start": r["week_start"],
            "kcal_avg": round(r["kcal"] / max(r["days_logged"], 1), 1),
            "protein_avg": round(r["protein"] / max(r["days_logged"], 1), 1),
            "carbs_avg": round(r["carbs"] / max(r["days_logged"], 1), 1),
            "fat_avg": round(r["fat"] / max(r["days_logged"], 1), 1),
            "days_logged": r["days_logged"],
        }
        for r in rows
    ]


def workout_trends(conn: sqlite3.Connection, weeks: int) -> list[dict]:
    rows = conn.execute(
        f"""
        SELECT
            {_WEEK_START} AS week_start,
            COUNT(DISTINCT w.id) AS sessions,
            COALESCE(SUM(s.weight_kg * s.reps), 0) AS tonnage_kg
        FROM workouts w
        LEFT JOIN workout_exercises we ON we.workout_id = w.id
        LEFT JOIN workout_sets s ON s.workout_exercise_id = we.id
        WHERE w.date >= date('now', ?)
        GROUP BY {_WEEK_KEY.replace("date", "w.date")}
        ORDER BY week_start
        """,
        (f"-{weeks * 7} days",),
    ).fetchall()
    return [
        {"week_start": r["week_start"], "sessions": r["sessions"], "tonnage_kg": round(r["tonnage_kg"], 1)}
        for r in rows
    ]


def exercise_progression(conn: sqlite3.Connection, exercise_title: str, weeks: int) -> list[dict]:
    rows = conn.execute(
        f"""
        SELECT
            {_WEEK_START.replace("date", "w.date")} AS week_start,
            MAX(s.weight_kg) AS top_weight_kg,
            COALESCE(SUM(s.weight_kg * s.reps), 0) AS tonnage_kg
        FROM workouts w
        JOIN workout_exercises we ON we.workout_id = w.id
        JOIN workout_sets s ON s.workout_exercise_id = we.id
        WHERE we.title = ? AND w.date >= date('now', ?)
        GROUP BY {_WEEK_KEY.replace("date", "w.date")}
        ORDER BY week_start
        """,
        (exercise_title, f"-{weeks * 7} days"),
    ).fetchall()
    return [
        {"week_start": r["week_start"], "top_weight_kg": r["top_weight_kg"], "tonnage_kg": round(r["tonnage_kg"], 1)}
        for r in rows
    ]


def weight_trend(conn: sqlite3.Connection, weeks: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT date, weight_kg, fat_percent
        FROM body_measurements
        WHERE date >= date('now', ?) AND weight_kg IS NOT NULL
        ORDER BY date
        """,
        (f"-{weeks * 7} days",),
    ).fetchall()
    return [{"date": r["date"], "weight_kg": r["weight_kg"], "fat_percent": r["fat_percent"]} for r in rows]


def intake_vs_training(conn: sqlite3.Connection, weeks: int) -> list[dict]:
    """One row per week: average daily kcal/protein alongside that week's training
    volume — the cross-referencing view PRODUCT.md's Positioning promises and no
    Hevy/MyFitnessPal-style single-domain app can show."""
    food = {r["week_start"]: r for r in food_trends(conn, weeks)}
    workouts = {r["week_start"]: r for r in workout_trends(conn, weeks)}
    weeks_set = sorted(set(food) | set(workouts))
    return [
        {
            "week_start": w,
            "kcal_avg": food.get(w, {}).get("kcal_avg", 0),
            "protein_avg": food.get(w, {}).get("protein_avg", 0),
            "sessions": workouts.get(w, {}).get("sessions", 0),
            "tonnage_kg": workouts.get(w, {}).get("tonnage_kg", 0),
        }
        for w in weeks_set
    ]
