"""Daily macro targets — a single editable row backing the logging UI's "today"
snapshot. See migrations/005_targets.sql.
"""

import sqlite3


def get_targets(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM targets WHERE id = 1").fetchone()


def set_targets(
    conn: sqlite3.Connection,
    kcal: float,
    protein: float,
    carbs: float,
    fat: float,
) -> sqlite3.Row:
    conn.execute(
        """
        INSERT INTO targets (id, kcal, protein, carbs, fat, updated_at)
        VALUES (1, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        ON CONFLICT (id) DO UPDATE SET
            kcal = excluded.kcal,
            protein = excluded.protein,
            carbs = excluded.carbs,
            fat = excluded.fat,
            updated_at = excluded.updated_at
        """,
        (kcal, protein, carbs, fat),
    )
    conn.commit()
    return get_targets(conn)
