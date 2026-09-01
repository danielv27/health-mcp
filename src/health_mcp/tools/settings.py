"""App-wide settings — a single editable row, same pattern as tools/targets.py.
See migrations/007_settings.sql.
"""

import sqlite3


def get_settings(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()


def set_hevy_auto_sync(conn: sqlite3.Connection, enabled: bool) -> sqlite3.Row:
    conn.execute("UPDATE settings SET hevy_auto_sync = ? WHERE id = 1", (int(enabled),))
    conn.commit()
    return get_settings(conn)
