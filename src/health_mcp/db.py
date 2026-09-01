"""SQLite connections and the migration runner.

Two connections by design, per docs/adr/0006: `rw()` is unrestricted and backs write
tools plus the migration runner. `ro()` opens the same file `mode=ro` — the first,
real defence behind the `query` tool; SQL-shape validation in `query.py` is the second.
"""

import sqlite3
from pathlib import Path

from health_mcp.config import settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def rw(db_path: Path | None = None) -> sqlite3.Connection:
    """check_same_thread=False: a FastAPI sync dependency's open (`yield`) and close
    (post-`yield`) can each land on a different threadpool worker, which sqlite3's
    default same-thread check rejects even though the two phases never run
    concurrently."""
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def ro(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.db_path
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if not exists:
        return 0
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] or 0


def migrate(db_path: Path | None = None) -> None:
    """Apply migrations from MIGRATIONS_DIR, in order, that are newer than what's applied.

    Each migration file ends with its own `INSERT INTO schema_version`, so applying it
    and recording it happen in the same script — see migrations/001_init.sql.
    """
    conn = rw(db_path)
    try:
        current = current_version(conn)
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = int(path.name.split("_", 1)[0])
            if version <= current:
                continue
            conn.executescript(path.read_text())
        conn.commit()
    finally:
        conn.close()
