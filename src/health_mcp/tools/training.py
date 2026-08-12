"""Training write tools: sync_workouts from Hevy."""

import sqlite3

from health_mcp.hevy import normalize_workouts, sync_workouts as hevy_sync


def sync_workouts(conn: sqlite3.Connection, full: bool = False) -> dict:
    """Sync workouts from Hevy (delta by default).

    Runs both fetch and normalize phases, returning a summary. `full=True` does a
    complete re-fetch from the beginning instead of using the cursor.
    """
    # Fetch phase
    fetch_result = hevy_sync(conn, full=full)
    if not fetch_result.get("success"):
        return fetch_result

    # Normalize phase
    norm_result = normalize_workouts(conn)

    return {
        **fetch_result,
        "normalized": norm_result if norm_result.get("success") else {"error": norm_result.get("error")},
    }
