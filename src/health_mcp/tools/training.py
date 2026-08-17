"""Training tools. Sync is the whole of it — reads go through `query` (docs/adr/0006).

The work lives in `hevy.py` / `strava.py`; this is the seam the MCP transport calls,
matching how `tools/food.py` takes an already-open connection.
"""

import sqlite3

from health_mcp import hevy, strava


def sync_workouts(conn: sqlite3.Connection, full: bool = False) -> dict:
    return hevy.sync(conn, full=full)


def sync_activities(conn: sqlite3.Connection, full: bool = False) -> dict:
    return strava.sync(conn, full=full)
