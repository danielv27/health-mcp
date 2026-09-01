"""Meals — a group of Food Log Entries logged together in one commit.

Added after /impeccable critique (2026-08-31) found that food is never logged
standalone in practice: it's always part of a meal, and the prior one-entry-at-a-time
flow had no way to express or undo that. `log_meal` writes the meal and all its
entries atomically — either the whole meal lands, or none of it does — see
`health_mcp.tools.food.log_food`'s `commit=False`.
"""

import sqlite3
from datetime import datetime

from health_mcp.day import ZONE, day_of, now_utc, to_utc
from health_mcp.tools.food import Macros, log_food

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


class MealItem:
    """One food to log as part of a meal — mirrors `log_food`'s own-item args."""

    def __init__(
        self,
        grams: float,
        product_id: int | None = None,
        name: str | None = None,
        macros: Macros | None = None,
        entered_as: str | None = None,
    ) -> None:
        self.grams = grams
        self.product_id = product_id
        self.name = name
        self.macros = macros
        self.entered_as = entered_as


def infer_meal_type(at: datetime | None = None) -> str:
    """A reasonable default meal type from local time of day — always editable
    before a meal is committed, never authoritative after."""
    moment = to_utc(at) if at is not None else now_utc()
    hour = moment.astimezone(ZONE).hour
    if hour < 4:
        return "snack"  # late night, still the day that's ending — see day.py's CUTOFF_HOUR
    if hour < 11:
        return "breakfast"
    if hour < 15:
        return "lunch"
    if hour < 21:
        return "dinner"
    return "snack"


def log_meal(
    conn: sqlite3.Connection,
    meal_type: str,
    items: list[MealItem],
    at: datetime | None = None,
) -> dict:
    if meal_type not in MEAL_TYPES:
        raise ValueError(f"meal_type must be one of {MEAL_TYPES}, got {meal_type!r}")
    if not items:
        raise ValueError("a meal needs at least one item")

    moment = to_utc(at) if at is not None else now_utc()
    date = day_of(moment)

    cur = conn.execute(
        "INSERT INTO meals (date, meal_type, logged_at) VALUES (?, ?, ?)",
        (date.isoformat(), meal_type, moment.isoformat()),
    )
    meal_id = cur.lastrowid

    entry_ids = []
    try:
        for item in items:
            entry_id = log_food(
                conn,
                grams=item.grams,
                product_id=item.product_id,
                name=item.name,
                macros=item.macros,
                entered_as=item.entered_as,
                at=at,
                meal_id=meal_id,
                commit=False,
            )
            entry_ids.append(entry_id)
    except Exception:
        conn.rollback()
        raise

    conn.commit()
    return {"meal_id": meal_id, "entry_ids": entry_ids}


def delete_meal(conn: sqlite3.Connection, meal_id: int) -> None:
    """Delete a meal and every entry logged under it. Deletes food_log rows before
    the meals row itself — `foreign_keys = ON` (db.rw) rejects deleting a parent
    row a child still references."""
    exists = conn.execute("SELECT 1 FROM meals WHERE id = ?", (meal_id,)).fetchone()
    if exists is None:
        raise ValueError(f"no meal with id {meal_id}")
    conn.execute("DELETE FROM food_log WHERE meal_id = ?", (meal_id,))
    conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
    conn.commit()
