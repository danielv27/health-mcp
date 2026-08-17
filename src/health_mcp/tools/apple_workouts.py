"""Apple Health workout tools. Import is the whole of it — reads go through `query`
(docs/adr/0006).

The work lives in `apple_workouts.py`; this is the seam the MCP transport calls, matching
how `tools/food.py` / `tools/training.py` / `tools/steps.py` take an already-open
connection.
"""

import sqlite3
from pathlib import Path

from health_mcp import apple_workouts


def import_workouts(conn: sqlite3.Connection, paths: str | Path | list[str | Path]) -> dict:
    return apple_workouts.import_csv(conn, paths)
