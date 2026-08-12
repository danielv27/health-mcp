"""Hevy client and sync, against https://api.hevyapp.com/docs/.

Collection endpoints answer `{"page": n, "page_count": m, "<collection>": [...]}`, so
paging means counting to `page_count`. `/workouts/events` carries updates *and* deletions
since a timestamp, newest first, and `since` defaults to the epoch — so a full resync is
just a delta from the epoch, and no separate backfill path is needed.

Sync is two phases on purpose (PLAN.md "Hevy sync"): `sync` writes each workout's raw
JSON into `workouts.raw`, and `normalize` parses that back out into `workout_exercises` /
`workout_sets`, so a parsing mistake costs a re-parse rather than a re-fetch.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

import httpx

from health_mcp.config import settings
from health_mcp.day import day_of

BASE_URL = "https://api.hevyapp.com/v1"

# Documented per-endpoint `pageSize` maxima; the API 400s above them.
EVENTS_PAGE_SIZE = 10
TEMPLATES_PAGE_SIZE = 100
MEASUREMENTS_PAGE_SIZE = 10

EPOCH = "1970-01-01T00:00:00Z"


class HevyError(RuntimeError):
    """A sync failed in a way worth showing the user verbatim."""


class HevyClient:
    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self._client = client or httpx.Client(
            base_url=BASE_URL, headers={"api-key": api_key}, timeout=30.0
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HevyClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, path: str, **params: Any) -> dict:
        response = self._client.get(path, params=params)
        if response.status_code in (401, 403):
            raise HevyError(
                f"Hevy rejected the API key ({response.status_code}) — check "
                "HEALTH_MCP_HEVY_API_KEY in ~/health/.env and that Hevy Pro is active"
            )
        if response.status_code >= 400:
            raise HevyError(f"Hevy returned {response.status_code}: {response.text[:200]}")
        return response.json()

    def _collect(self, path: str, keys: tuple[str, ...], size: int, **params: Any) -> list[dict]:
        """Every page of `path`, concatenated."""
        items: list[dict] = []
        page = 1
        while True:
            body = self._get(path, **params, page=page, pageSize=size)
            key = next((k for k in keys if k in body), None)
            if key is None:
                raise HevyError(f"{path}: expected one of {list(keys)}, got {sorted(body)}")
            items.extend(body[key])
            if page >= body.get("page_count", page):
                return items
            page += 1

    def user_info(self) -> dict:
        """Round-trips the key. 200 here proves both the key and Pro status."""
        return self._get("/user/info")["data"]

    def workout_events(self, since: str) -> list[dict]:
        # Undocumented: an *empty* feed comes back under "workouts" rather than "events".
        return self._collect("/workouts/events", ("events", "workouts"), EVENTS_PAGE_SIZE,
                             since=since)

    def exercise_templates(self) -> list[dict]:
        return self._collect("/exercise_templates", ("exercise_templates",), TEMPLATES_PAGE_SIZE)

    def body_measurements(self) -> list[dict]:
        return self._collect("/body_measurements", ("body_measurements",), MEASUREMENTS_PAGE_SIZE)


# -- sync ---------------------------------------------------------------------


def sync(conn: sqlite3.Connection, full: bool = False, client: HevyClient | None = None) -> dict:
    """Pull everything since the cursor into the database, then normalize what changed.

    `full=True` replays from the epoch, which re-fetches every workout *and* every
    deletion — the "make the local copy right" path when the cursor has drifted.
    """
    if not settings.hevy_api_key:
        return _fail(conn, "HEALTH_MCP_HEVY_API_KEY is not set (expected in ~/health/.env)")

    # Captured before the first request, so anything saved mid-sync is picked up next
    # time. Re-delivery is harmless: every write below is an upsert.
    started_at = _stamp(datetime.now(timezone.utc))

    owned = client is None
    client = client or HevyClient(settings.hevy_api_key)
    try:
        client.user_info()

        # Templates first: workout_exercises.exercise_template_id points at this table.
        templates = _store_templates(conn, client.exercise_templates())

        since = EPOCH if full else (_cursor(conn) or EPOCH)
        workouts, deleted = _apply_events(conn, client.workout_events(since))
        touched = _store_workouts(conn, workouts)
        measurements = _store_measurements(conn, client.body_measurements())
        conn.commit()

        # A full sync re-parses the whole table; a delta only touches what moved.
        counts = normalize(conn, workout_ids=None if full else touched)

        _record(conn, "success", cursor=started_at)
        return {
            "ok": True,
            "workouts": len(touched),
            "deleted": deleted,
            "templates": templates,
            "measurements": measurements,
            "cursor": started_at,
            **counts,
        }
    except (HevyError, httpx.HTTPError, sqlite3.Error, ValueError, KeyError) as exc:
        # sqlite3.Error is caught deliberately: a sync broken by a schema problem has to
        # leave a trace too, or `last_status` sits on "success" while nothing syncs.
        conn.rollback()
        return _fail(conn, str(exc) if isinstance(exc, HevyError) else f"{type(exc).__name__}: {exc}")
    finally:
        if owned:
            client.close()


def _apply_events(conn: sqlite3.Connection, events: list[dict]) -> tuple[list[dict], int]:
    """Deletions applied, updates returned for storing.

    Events are newest first, so the first one mentioning a workout is its current state
    and every later mention is superseded — including an update that precedes its own
    deletion, which is why a seen id is skipped outright rather than merged.
    """
    workouts: list[dict] = []
    deleted = 0
    seen: set[str] = set()
    for event in events:
        gone = event["type"] == "deleted"
        workout = None if gone else event["workout"]
        workout_id = event["id"] if gone else workout["id"]
        if workout_id in seen:
            continue
        seen.add(workout_id)
        if not gone:
            workouts.append(workout)
        elif _delete_workout(conn, workout_id):
            # Only count a deletion that removed something: a replay from the epoch
            # carries deletions for workouts this database never held.
            deleted += 1
    return workouts, deleted


def _clear_exercises(conn: sqlite3.Connection, workout_id: str) -> None:
    """A workout's parsed rows, torn down. Sets before exercises — the foreign keys have
    no ON DELETE CASCADE, so a parent with children can't be deleted first."""
    conn.execute(
        """
        DELETE FROM workout_sets WHERE workout_exercise_id IN
            (SELECT id FROM workout_exercises WHERE workout_id = ?)
        """,
        (workout_id,),
    )
    conn.execute("DELETE FROM workout_exercises WHERE workout_id = ?", (workout_id,))


def _delete_workout(conn: sqlite3.Connection, workout_id: str) -> bool:
    _clear_exercises(conn, workout_id)
    return conn.execute("DELETE FROM workouts WHERE id = ?", (workout_id,)).rowcount > 0


def _store_workouts(conn: sqlite3.Connection, workouts: list[dict]) -> list[str]:
    """Phase one: the raw payload, verbatim. Returns the ids written."""
    for workout in workouts:
        start_time = workout["start_time"]
        conn.execute(
            """
            INSERT INTO workouts (id, title, start_time, end_time, date, updated_at, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title, start_time = excluded.start_time,
                end_time = excluded.end_time, date = excluded.date,
                updated_at = excluded.updated_at, raw = excluded.raw
            """,
            (
                workout["id"],
                workout.get("title") or "",
                start_time,
                workout.get("end_time") or start_time,
                day_of(datetime.fromisoformat(start_time)).isoformat(),
                workout.get("updated_at") or _stamp(datetime.now(timezone.utc)),
                json.dumps(workout),
            ),
        )
    return [workout["id"] for workout in workouts]


def _store_templates(conn: sqlite3.Connection, templates: list[dict]) -> int:
    for template in templates:
        conn.execute(
            """
            INSERT INTO exercise_templates
                (id, title, primary_muscle_group, secondary_muscle_groups, equipment)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                primary_muscle_group = excluded.primary_muscle_group,
                secondary_muscle_groups = excluded.secondary_muscle_groups,
                equipment = excluded.equipment
            """,
            (
                template["id"],
                template.get("title") or "",
                template.get("primary_muscle_group"),
                json.dumps(template.get("secondary_muscle_groups") or []),
                # Schema calls it `equipment_category`, the API sends `equipment`.
                template.get("equipment") or template.get("equipment_category"),
            ),
        )
    return len(templates)


def _store_measurements(conn: sqlite3.Connection, measurements: list[dict]) -> int:
    """One row per Day. Body fat is only present when it was recorded, so COALESCE keeps
    a later weight-only entry from blanking an earlier reading."""
    for measurement in measurements:
        conn.execute(
            """
            INSERT INTO body_measurements (date, weight_kg, fat_percent)
            VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                weight_kg = COALESCE(excluded.weight_kg, weight_kg),
                fat_percent = COALESCE(excluded.fat_percent, fat_percent)
            """,
            (measurement["date"], measurement.get("weight_kg"), measurement.get("fat_percent")),
        )
    return len(measurements)


# -- normalize ----------------------------------------------------------------


def normalize(conn: sqlite3.Connection, workout_ids: list[str] | None = None) -> dict:
    """Phase two: `workouts.raw` into `workout_exercises` / `workout_sets`.

    Every workout's rows are torn down and rebuilt, so running this twice is running it
    once. `workout_ids=None` does the whole table, and needs no network access.
    """
    if workout_ids is None:
        rows = conn.execute("SELECT id, raw FROM workouts").fetchall()
    elif workout_ids:
        placeholders = ",".join("?" * len(workout_ids))
        rows = conn.execute(
            f"SELECT id, raw FROM workouts WHERE id IN ({placeholders})", workout_ids
        ).fetchall()
    else:
        return {"exercises": 0, "sets": 0}

    exercises = sets = 0
    for row in rows:
        workout_id = row["id"]
        _clear_exercises(conn, workout_id)

        for idx, exercise in enumerate(json.loads(row["raw"]).get("exercises") or []):
            template_id = exercise.get("exercise_template_id")
            title = exercise.get("title") or ""
            if template_id:
                # A workout can name a template the templates endpoint didn't return
                # (custom, or since deleted). Stub it so the foreign key holds.
                conn.execute(
                    "INSERT OR IGNORE INTO exercise_templates (id, title) VALUES (?, ?)",
                    (template_id, title),
                )
            cursor = conn.execute(
                """
                INSERT INTO workout_exercises (workout_id, idx, exercise_template_id, title)
                VALUES (?, ?, ?, ?)
                """,
                (workout_id, exercise.get("index", idx), template_id, title),
            )
            exercises += 1

            for set_idx, entry in enumerate(exercise.get("sets") or []):
                conn.execute(
                    """
                    INSERT INTO workout_sets (workout_exercise_id, idx, type, weight_kg,
                        reps, rpe, duration_s, distance_m)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cursor.lastrowid,
                        entry.get("index", set_idx),
                        entry.get("type") or "normal",
                        entry.get("weight_kg"),
                        entry.get("reps"),
                        entry.get("rpe"),
                        entry.get("duration_seconds"),
                        entry.get("distance_meters"),
                    ),
                )
                sets += 1

    conn.commit()
    return {"exercises": exercises, "sets": sets}


# -- sync_state ---------------------------------------------------------------


def _cursor(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT cursor FROM sync_state WHERE source = 'hevy'").fetchone()
    return row["cursor"] if row else None


def _record(conn: sqlite3.Connection, status: str, error: str | None = None,
            cursor: str | None = None) -> None:
    """A failure leaves the cursor alone, so the next run retries the same window."""
    conn.execute(
        """
        INSERT INTO sync_state (source, cursor, last_run_at, last_status, last_error)
        VALUES ('hevy', ?, ?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
            cursor = COALESCE(excluded.cursor, sync_state.cursor),
            last_run_at = excluded.last_run_at,
            last_status = excluded.last_status,
            last_error = excluded.last_error
        """,
        (cursor, _stamp(datetime.now(timezone.utc)), status, error),
    )
    conn.commit()


def _fail(conn: sqlite3.Connection, error: str) -> dict:
    """Failures land in `sync_state` as well as the return value — a sync that has been
    failing for a week should be one `query` away from being visible."""
    _record(conn, "failed", error=error)
    return {"ok": False, "error": error}


def _stamp(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")
