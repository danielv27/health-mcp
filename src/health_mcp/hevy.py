"""Hevy API client and sync logic.

Two-phase sync: fetch raw JSON first, normalize later. This allows parse errors to be
re-runnable without re-fetching (see PLAN.md "Hevy sync").

Auth is `api-key: <uuid>` header on https://api.hevyapp.com/v1.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

import httpx

from health_mcp.config import settings
from health_mcp.day import day_of


class HevyClient:
    """HTTP client for the Hevy API with pagination and error handling."""

    BASE_URL = "https://api.hevyapp.com/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.Client(
            headers={"api-key": api_key},
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _get_paginated(self, endpoint: str, **params) -> list[dict]:
        """Fetch all pages from an endpoint, respecting pageSize from responses."""
        results = []
        page = 1
        page_size = None

        while True:
            params_with_page = {**params, "page": page}
            if page_size:
                params_with_page["pageSize"] = page_size

            response = self.client.get(f"{self.BASE_URL}{endpoint}", params=params_with_page)
            response.raise_for_status()
            data = response.json()

            # Extract the data array — endpoint-dependent
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and "data" in data:
                items = data["data"]
            else:
                raise ValueError(f"Unexpected response shape from {endpoint}: {data}")

            results.extend(items)

            # Check if there are more pages
            if page_size is None and isinstance(data, dict):
                page_size = data.get("pageSize", 100)

            if len(items) < (page_size or 100):
                break

            page += 1

        return results

    def get_user_info(self) -> dict:
        """Verify auth and get user info — returns 200 if key is valid and Pro is active."""
        response = self.client.get(f"{self.BASE_URL}/user/info")
        response.raise_for_status()
        return response.json()

    def get_workouts(self) -> list[dict]:
        """Fetch all workouts for backfill."""
        return self._get_paginated("/workouts")

    def get_workout_events(self, since: str | None = None) -> list[dict]:
        """Fetch workout events (creates and updates and deletes) since a cursor."""
        params = {}
        if since:
            params["since"] = since
        return self._get_paginated("/workouts/events", **params)

    def get_exercise_templates(self) -> list[dict]:
        """Fetch exercise templates for muscle group lookup."""
        return self._get_paginated("/exercise_templates")

    def get_body_measurements(self) -> list[dict]:
        """Fetch body measurements (weight and body fat)."""
        return self._get_paginated("/body_measurements")


def sync_workouts(conn: sqlite3.Connection, full: bool = False) -> dict[str, Any]:
    """Sync workouts from Hevy in two phases: fetch raw JSON, then normalize.

    Returns a dict with sync status: {success, fetched, updated, deleted, cursor, error}.
    """
    if not settings.hevy_api_key:
        return {
            "success": False,
            "error": "HEALTH_MCP_HEVY_API_KEY not set",
        }

    try:
        with HevyClient(settings.hevy_api_key) as client:
            # Verify auth
            user_info = client.get_user_info()

            # Get sync cursor
            if full:
                cursor = None
            else:
                cursor_row = conn.execute(
                    "SELECT cursor FROM sync_state WHERE source = 'hevy'"
                ).fetchone()
                cursor = cursor_row["cursor"] if cursor_row else None

            # Fetch and store raw JSON
            if full:
                events = client.get_workouts()
                fetched_count = len(events)
            else:
                events = client.get_workout_events(since=cursor)
                fetched_count = len(events)

            # Store raw JSON and track new cursor
            new_cursor = None
            updated_count = 0
            deleted_count = 0

            for event in events:
                if event.get("type") == "DELETED":
                    # Handle deletion
                    workout_id = event.get("id")
                    if workout_id:
                        conn.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))
                        deleted_count += 1
                else:
                    # Handle create/update
                    workout = event if event.get("type") != "DELETED" else event.get("data", {})
                    workout_id = workout.get("id")
                    title = workout.get("title", "")
                    start_time = workout.get("start_time")
                    end_time = workout.get("end_time")
                    updated_at = workout.get("updated_at", datetime.now(timezone.utc).isoformat())

                    if workout_id and start_time:
                        date = day_of(datetime.fromisoformat(start_time.replace("Z", "+00:00")))
                        conn.execute(
                            """
                            INSERT INTO workouts (id, title, start_time, end_time, date, updated_at, raw)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET
                                title = excluded.title,
                                start_time = excluded.start_time,
                                end_time = excluded.end_time,
                                date = excluded.date,
                                updated_at = excluded.updated_at,
                                raw = excluded.raw
                            """,
                            (
                                workout_id,
                                title,
                                start_time,
                                end_time,
                                date.isoformat(),
                                updated_at,
                                json.dumps(workout),
                            ),
                        )
                        updated_count += 1

                # Update cursor from the event's cursor if present
                if "cursor" in event:
                    new_cursor = event["cursor"]

            conn.commit()

            # Update sync state
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO sync_state (source, cursor, last_run_at, last_status)
                VALUES ('hevy', ?, ?, 'success')
                ON CONFLICT(source) DO UPDATE SET
                    cursor = excluded.cursor,
                    last_run_at = excluded.last_run_at,
                    last_status = excluded.last_status,
                    last_error = NULL
                """,
                (new_cursor or cursor, now),
            )
            conn.commit()

            return {
                "success": True,
                "fetched": fetched_count,
                "updated": updated_count,
                "deleted": deleted_count,
                "cursor": new_cursor or cursor,
            }

    except httpx.HTTPError as e:
        error_msg = f"HTTP error: {str(e)}"
        _record_sync_error(conn, error_msg)
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"Sync error: {str(e)}"
        _record_sync_error(conn, error_msg)
        return {"success": False, "error": error_msg}


def normalize_workouts(conn: sqlite3.Connection) -> dict[str, Any]:
    """Parse raw workout JSON into workout_exercises and workout_sets.

    This is idempotent — can be re-run over the whole table if parsing logic changes.
    """
    try:
        # Get all raw workouts
        rows = conn.execute("SELECT id, raw FROM workouts ORDER BY id").fetchall()

        exercise_count = 0
        set_count = 0

        for row in rows:
            workout_id = row["id"]
            raw_data = json.loads(row["raw"])

            # Clear existing exercises for this workout (re-parse)
            conn.execute("DELETE FROM workout_exercises WHERE workout_id = ?", (workout_id,))

            exercises = raw_data.get("exercises", [])
            for ex_idx, exercise in enumerate(exercises):
                exercise_template_id = exercise.get("exercise_template_id")
                title = exercise.get("title", "")

                cur = conn.execute(
                    """
                    INSERT INTO workout_exercises (workout_id, idx, exercise_template_id, title)
                    VALUES (?, ?, ?, ?)
                    """,
                    (workout_id, ex_idx, exercise_template_id, title),
                )
                exercise_id = cur.lastrowid
                exercise_count += 1

                # Parse sets
                sets = exercise.get("sets", [])
                for set_idx, s in enumerate(sets):
                    set_type = s.get("type", "")
                    weight_kg = s.get("weight_kg")
                    reps = s.get("reps")
                    rpe = s.get("rpe")
                    duration_s = s.get("duration_s")
                    distance_m = s.get("distance_m")

                    conn.execute(
                        """
                        INSERT INTO workout_sets
                        (workout_exercise_id, idx, type, weight_kg, reps, rpe, duration_s, distance_m)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (exercise_id, set_idx, set_type, weight_kg, reps, rpe, duration_s, distance_m),
                    )
                    set_count += 1

        conn.commit()

        return {
            "success": True,
            "exercises": exercise_count,
            "sets": set_count,
        }

    except Exception as e:
        error_msg = f"Normalization error: {str(e)}"
        return {"success": False, "error": error_msg}


def _record_sync_error(conn: sqlite3.Connection, error: str) -> None:
    """Record an error in sync_state for visibility."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO sync_state (source, last_run_at, last_status, last_error)
        VALUES ('hevy', ?, 'failed', ?)
        ON CONFLICT(source) DO UPDATE SET
            last_run_at = excluded.last_run_at,
            last_status = excluded.last_status,
            last_error = excluded.last_error
        """,
        (now, error),
    )
    conn.commit()
