"""Food write tools, plus `find_product` — the resolution step before logging against
a Catalog Product (see CONTEXT.md "Product resolution": no fuzzy matching inside writes).

Each function takes an already-open rw connection so the MCP transport layer (server.py)
and tests share the same entry points.
"""

import sqlite3
from datetime import datetime

from pydantic import BaseModel

from health_mcp.day import day_of, now_utc, to_utc

SOURCES = ("verified", "estimated")


class Macros(BaseModel):
    """Per-100g macros for a one-off `log_food` entry — always `estimated`."""

    kcal_100g: float
    protein_100g: float
    carbs_100g: float
    fat_100g: float


def add_product(
    conn: sqlite3.Connection,
    name: str,
    kcal_100g: float,
    protein_100g: float,
    carbs_100g: float,
    fat_100g: float,
    brand: str | None = None,
    source: str = "verified",
    fibre_100g: float | None = None,
    sugar_100g: float | None = None,
    sat_fat_100g: float | None = None,
    salt_100g: float | None = None,
    note: str | None = None,
) -> int:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
    cur = conn.execute(
        """
        INSERT INTO products (
            name, brand, source, kcal_100g, protein_100g, carbs_100g, fat_100g,
            fibre_100g, sugar_100g, sat_fat_100g, salt_100g, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name, brand, source, kcal_100g, protein_100g, carbs_100g, fat_100g,
            fibre_100g, sugar_100g, sat_fat_100g, salt_100g, note,
        ),
    )
    conn.commit()
    return cur.lastrowid


def update_product(
    conn: sqlite3.Connection,
    id: int,
    name: str | None = None,
    brand: str | None = None,
    source: str | None = None,
    kcal_100g: float | None = None,
    protein_100g: float | None = None,
    carbs_100g: float | None = None,
    fat_100g: float | None = None,
    fibre_100g: float | None = None,
    sugar_100g: float | None = None,
    sat_fat_100g: float | None = None,
    salt_100g: float | None = None,
    note: str | None = None,
) -> int:
    """Overwrite only the given fields of a Catalog Product; omitted fields keep their
    current value. Any food_log entry already logged against this product_id is
    re-derived from the corrected per-100g values (kcal/protein/carbs/fat = new value *
    grams/100) so past entries stop carrying a stale snapshot. Returns the number of
    food_log entries re-derived."""
    if source is not None and source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, got {source!r}")

    fields = {
        "name": name, "brand": brand, "source": source, "kcal_100g": kcal_100g,
        "protein_100g": protein_100g, "carbs_100g": carbs_100g, "fat_100g": fat_100g,
        "fibre_100g": fibre_100g, "sugar_100g": sugar_100g, "sat_fat_100g": sat_fat_100g,
        "salt_100g": salt_100g, "note": note,
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    if not fields:
        raise ValueError("no fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    cur = conn.execute(
        f"UPDATE products SET {set_clause} WHERE id = ?",
        (*fields.values(), id),
    )
    if cur.rowcount == 0:
        conn.rollback()
        raise ValueError(f"no product with id {id}")

    product = conn.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()
    relog_cur = conn.execute(
        """
        UPDATE food_log SET
            name = ?,
            source = ?,
            kcal = ? * grams / 100.0,
            protein = ? * grams / 100.0,
            carbs = ? * grams / 100.0,
            fat = ? * grams / 100.0
        WHERE product_id = ?
        """,
        (
            product["name"], product["source"], product["kcal_100g"],
            product["protein_100g"], product["carbs_100g"], product["fat_100g"], id,
        ),
    )
    conn.commit()
    return relog_cur.rowcount


def find_product(conn: sqlite3.Connection, query: str | None = None) -> list[sqlite3.Row]:
    if query:
        pattern = f"%{query}%"
        return conn.execute(
            "SELECT * FROM products WHERE name LIKE ? OR brand LIKE ? ORDER BY name",
            (pattern, pattern),
        ).fetchall()
    return conn.execute("SELECT * FROM products ORDER BY name").fetchall()


def log_food(
    conn: sqlite3.Connection,
    grams: float,
    product_id: int | None = None,
    name: str | None = None,
    macros: Macros | None = None,
    entered_as: str | None = None,
    at: datetime | None = None,
) -> int:
    """Log a Food Log Entry against a Catalog Product, or a one-off with model-supplied
    Macros. Quantity is always grams; `entered_as` keeps the original phrasing for
    display only — see CONTEXT.md "Food Log Entry"."""
    if (product_id is None) == (macros is None):
        raise ValueError("pass exactly one of product_id or macros")

    moment = to_utc(at) if at is not None else now_utc()
    date = day_of(moment)
    scale = grams / 100.0

    if product_id is not None:
        product = conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            raise ValueError(f"no product with id {product_id}")
        entry_name = product["name"]
        source = product["source"]
        kcal = product["kcal_100g"] * scale
        protein = product["protein_100g"] * scale
        carbs = product["carbs_100g"] * scale
        fat = product["fat_100g"] * scale
    else:
        if name is None:
            raise ValueError("name is required for a one-off entry")
        entry_name = name
        source = "estimated"
        kcal = macros.kcal_100g * scale
        protein = macros.protein_100g * scale
        carbs = macros.carbs_100g * scale
        fat = macros.fat_100g * scale

    cur = conn.execute(
        """
        INSERT INTO food_log (
            logged_at, date, product_id, name, source, grams, entered_as,
            kcal, protein, carbs, fat
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            moment.isoformat(), date.isoformat(), product_id, entry_name, source,
            grams, entered_as, kcal, protein, carbs, fat,
        ),
    )
    conn.commit()
    return cur.lastrowid


def delete_food_entry(conn: sqlite3.Connection, id: int) -> None:
    cur = conn.execute("DELETE FROM food_log WHERE id = ?", (id,))
    conn.commit()
    if cur.rowcount == 0:
        raise ValueError(f"no food_log entry with id {id}")
