"""Step-count tools. Import is the whole of it — reads go through `query` (docs/adr/0006).

The work lives in `steps.py`; this is the seam the MCP transport calls, matching how
`tools/food.py` / `tools/training.py` take an already-open connection.
"""

import sqlite3
from pathlib import Path

from health_mcp import steps


def import_steps(conn: sqlite3.Connection, path: str | Path) -> dict:
    return steps.import_csv(conn, path)
