"""Tests for hevy.py.

Payloads here are trimmed copies of real responses observed on 2026-08-12 — same field
names, same envelope, same lowercase set types. The client is driven through an
`httpx.MockTransport` rather than a mocked-out `HevyClient`, so pagination and envelope
parsing are actually exercised instead of stubbed over.
"""

import json

import httpx
import pytest

from health_mcp import hevy
from health_mcp.db import migrate, rw
from health_mcp.hevy import HevyClient, HevyError

WORKOUT = {
    "id": "9B119A46-D59F-4748-A59D-12004D9B9438",
    "title": "Push",
    "routine_id": "217429b3-c62a-412f-bd00-a4c32ebfcaa3",
    "description": "",
    "start_time": "2026-08-10T17:38:30+00:00",
    "end_time": "2026-08-10T18:48:27+00:00",
    "updated_at": "2026-08-10T18:48:28.986Z",
    "created_at": "2026-08-10T18:48:28.986Z",
    "exercises": [
        {
            "index": 0,
            "title": "Bench Press (Barbell)",
            "notes": "",
            "exercise_template_id": "79D0BB3A",
            "superset_id": None,
            "sets": [
                {"index": 0, "type": "warmup", "weight_kg": 20, "reps": 10,
                 "distance_meters": 0, "duration_seconds": 0, "rpe": 6, "custom_metric": 0},
                {"index": 1, "type": "normal", "weight_kg": 60, "reps": 12,
                 "distance_meters": 0, "duration_seconds": 0, "rpe": 7.5, "custom_metric": 0},
            ],
        }
    ],
}

TEMPLATE = {
    "id": "79D0BB3A",
    "title": "Bench Press (Barbell)",
    "type": "weight_reps",
    "primary_muscle_group": "chest",
    "secondary_muscle_groups": ["triceps", "shoulders"],
    "equipment": "barbell",
    "is_custom": False,
}

MEASUREMENT = {
    "id": 63317078,
    "date": "2026-08-12",
    "weight_kg": 69,
    "created_at": "2026-08-12T11:11:32.169Z",
}


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "health.db"
    migrate(db_path)
    connection = rw(db_path)
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setattr(hevy.settings, "hevy_api_key", "test-key")


def fake_api(routes, seen=None):
    """A HevyClient wired to canned responses. `routes` maps a path to a list of page
    bodies; `seen` collects the requests made, for asserting on query params."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        pages = routes.get(request.url.path)
        if pages is None:
            return httpx.Response(404, json={"error": "not found"})
        page = int(request.url.params.get("page", 1))
        return httpx.Response(200, json=pages[page - 1])

    transport = httpx.MockTransport(handler)
    return HevyClient(
        "test-key",
        client=httpx.Client(
            transport=transport, base_url=hevy.BASE_URL, headers={"api-key": "test-key"}
        ),
    )


def api(events=(), templates=(TEMPLATE,), measurements=(MEASUREMENT,), seen=None):
    routes = {
        "/v1/user/info": [{"data": {"id": "user-1", "name": "Daniel"}}],
        "/v1/workouts/events": [{"page": 1, "page_count": 1, "events": list(events)}],
        "/v1/exercise_templates": [
            {"page": 1, "page_count": 1, "exercise_templates": list(templates)}
        ],
        "/v1/body_measurements": [
            {"page": 1, "page_count": 1, "body_measurements": list(measurements)}
        ],
    }
    return fake_api(routes, seen=seen)


# -- client -------------------------------------------------------------------


def test_collect_follows_page_count_and_concatenates():
    """Paging stops on page_count, which the API reports up front."""
    routes = {
        "/v1/workouts/events": [
            {"page": 1, "page_count": 3, "events": [{"type": "updated", "workout": {"id": "a"}}]},
            {"page": 2, "page_count": 3, "events": [{"type": "updated", "workout": {"id": "b"}}]},
            {"page": 3, "page_count": 3, "events": [{"type": "updated", "workout": {"id": "c"}}]},
        ]
    }
    with fake_api(routes) as client:
        events = client.workout_events(hevy.EPOCH)
    assert [e["workout"]["id"] for e in events] == ["a", "b", "c"]


def test_events_request_the_documented_page_size_cap():
    """The docs cap /workouts/events at 10 and the API 400s above it."""
    seen = []
    with api(seen=seen) as client:
        client.workout_events(hevy.EPOCH)
    assert seen[-1].url.params["pageSize"] == "10"


def test_events_default_cursor_is_the_epoch():
    seen = []
    with api(seen=seen) as client:
        client.workout_events(hevy.EPOCH)
    assert seen[-1].url.params["since"] == "1970-01-01T00:00:00Z"


def test_unauthorized_says_what_to_check():
    routes = {}

    def handler(request):
        return httpx.Response(401, json={"error": "unauthorized"})

    client = HevyClient(
        "bad", client=httpx.Client(transport=httpx.MockTransport(handler), base_url=hevy.BASE_URL)
    )
    with pytest.raises(HevyError, match="rejected the API key"):
        client.user_info()


def test_unexpected_envelope_key_is_an_error():
    routes = {"/v1/exercise_templates": [{"page": 1, "page_count": 1, "data": []}]}
    with fake_api(routes) as client:
        with pytest.raises(HevyError, match="expected one of"):
            client.exercise_templates()


def test_empty_event_feed_arrives_under_the_wrong_key():
    """Observed live: an empty /workouts/events answers with `workouts`, not `events`,
    contradicting its own OpenAPI spec."""
    routes = {"/v1/workouts/events": [{"page": 1, "page_count": 1, "workouts": []}]}
    with fake_api(routes) as client:
        assert client.workout_events(hevy.EPOCH) == []


# -- sync ---------------------------------------------------------------------


def test_sync_without_an_api_key_is_a_visible_failure(conn, monkeypatch):
    monkeypatch.setattr(hevy.settings, "hevy_api_key", None)
    result = hevy.sync(conn)

    assert result["ok"] is False
    row = conn.execute("SELECT * FROM sync_state WHERE source = 'hevy'").fetchone()
    assert row["last_status"] == "failed"
    assert "HEVY_API_KEY" in row["last_error"]


def test_sync_stores_raw_payload_and_derived_day(conn):
    result = hevy.sync(conn, client=api(events=[{"type": "updated", "workout": WORKOUT}]))

    assert result["ok"] is True
    assert result["workouts"] == 1
    row = conn.execute("SELECT * FROM workouts").fetchone()
    assert row["title"] == "Push"
    # 17:38 UTC on the 10th is 19:38 Amsterdam — the same Day, not a boundary case.
    assert row["date"] == "2026-08-10"
    assert json.loads(row["raw"])["exercises"][0]["title"] == "Bench Press (Barbell)"


def test_sync_normalizes_into_exercises_and_sets(conn):
    hevy.sync(conn, client=api(events=[{"type": "updated", "workout": WORKOUT}]))

    exercise = conn.execute("SELECT * FROM workout_exercises").fetchone()
    assert exercise["title"] == "Bench Press (Barbell)"
    assert exercise["exercise_template_id"] == "79D0BB3A"

    sets = conn.execute("SELECT * FROM workout_sets ORDER BY idx").fetchall()
    assert [s["type"] for s in sets] == ["warmup", "normal"]
    assert [s["weight_kg"] for s in sets] == [20, 60]
    assert [s["reps"] for s in sets] == [10, 12]
    assert sets[1]["rpe"] == 7.5


def test_sync_advances_the_cursor_and_the_next_sync_sends_it(conn):
    hevy.sync(conn, client=api())
    cursor = conn.execute("SELECT cursor FROM sync_state WHERE source='hevy'").fetchone()["cursor"]
    assert cursor.endswith("Z")

    seen = []
    hevy.sync(conn, client=api(seen=seen))
    events_request = next(r for r in seen if r.url.path == "/v1/workouts/events")
    assert events_request.url.params["since"] == cursor


def test_first_sync_asks_for_everything(conn):
    seen = []
    hevy.sync(conn, client=api(seen=seen))
    events_request = next(r for r in seen if r.url.path == "/v1/workouts/events")
    assert events_request.url.params["since"] == hevy.EPOCH


def test_deletion_event_removes_the_workout_and_its_children(conn):
    hevy.sync(conn, client=api(events=[{"type": "updated", "workout": WORKOUT}]))
    assert conn.execute("SELECT COUNT(*) c FROM workout_sets").fetchone()["c"] == 2

    result = hevy.sync(
        conn,
        client=api(events=[{"type": "deleted", "id": WORKOUT["id"],
                            "deleted_at": "2026-08-11T09:00:00Z"}]),
    )

    assert result["deleted"] == 1
    for table in ("workouts", "workout_exercises", "workout_sets"):
        assert conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"] == 0


def test_deletion_event_for_an_unknown_workout_is_not_counted(conn):
    """A first sync from the epoch replays deletions this database never held."""
    result = hevy.sync(
        conn, client=api(events=[{"type": "deleted", "id": "never-seen",
                                  "deleted_at": "2026-08-11T09:00:00Z"}])
    )

    assert result["deleted"] == 0


def test_full_sync_replays_from_the_epoch(conn):
    """`since` defaults to the epoch, so a full resync needs no separate backfill path."""
    hevy.sync(conn, client=api())
    seen = []
    hevy.sync(conn, full=True, client=api(events=[{"type": "updated", "workout": WORKOUT}],
                                          seen=seen))

    events_request = next(r for r in seen if r.url.path == "/v1/workouts/events")
    assert events_request.url.params["since"] == hevy.EPOCH


def test_an_update_superseded_by_a_deletion_stays_deleted(conn):
    """Events are newest first, so a deletion arrives *before* the edit it supersedes."""
    hevy.sync(conn, client=api(events=[{"type": "updated", "workout": WORKOUT}]))

    result = hevy.sync(
        conn,
        client=api(events=[
            {"type": "deleted", "id": WORKOUT["id"], "deleted_at": "2026-08-11T10:00:00Z"},
            {"type": "updated", "workout": WORKOUT},
        ]),
    )

    assert result["deleted"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM workouts").fetchone()["c"] == 0


def test_a_workout_edited_twice_keeps_the_newest(conn):
    """Two edits since the cursor arrive as two events, newest first."""
    edited = {**WORKOUT, "title": "Push (edited)", "updated_at": "2026-08-11T09:00:00.000Z"}
    result = hevy.sync(
        conn,
        client=api(events=[
            {"type": "updated", "workout": edited},
            {"type": "updated", "workout": WORKOUT},
        ]),
    )

    assert result["workouts"] == 1
    assert conn.execute("SELECT title FROM workouts").fetchone()["title"] == "Push (edited)"
    assert conn.execute("SELECT COUNT(*) c FROM workout_sets").fetchone()["c"] == 2


def test_a_database_failure_is_recorded_not_raised(conn):
    """last_status must not sit on 'success' while nothing is actually syncing."""
    conn.execute("DROP TABLE workout_sets")
    conn.commit()

    result = hevy.sync(conn, client=api(events=[{"type": "updated", "workout": WORKOUT}]))

    assert result["ok"] is False
    row = conn.execute("SELECT * FROM sync_state WHERE source='hevy'").fetchone()
    assert row["last_status"] == "failed"
    assert "workout_sets" in row["last_error"]


def test_sync_stores_templates_with_muscle_groups(conn):
    hevy.sync(conn, client=api())

    row = conn.execute("SELECT * FROM exercise_templates WHERE id = '79D0BB3A'").fetchone()
    assert row["primary_muscle_group"] == "chest"
    assert json.loads(row["secondary_muscle_groups"]) == ["triceps", "shoulders"]
    assert row["equipment"] == "barbell"


def test_sync_reads_equipment_under_the_spec_name_too(conn):
    """The OpenAPI spec calls it `equipment_category`; the live API sends `equipment`."""
    spec_shaped = {**TEMPLATE, "equipment_category": "barbell"}
    del spec_shaped["equipment"]
    hevy.sync(conn, client=api(templates=[spec_shaped]))

    row = conn.execute("SELECT equipment FROM exercise_templates").fetchone()
    assert row["equipment"] == "barbell"


def test_sync_stores_body_measurements(conn):
    hevy.sync(conn, client=api())

    row = conn.execute("SELECT * FROM body_measurements WHERE date = '2026-08-12'").fetchone()
    assert row["weight_kg"] == 69


def test_measurement_without_body_fat_does_not_blank_an_earlier_reading(conn):
    hevy.sync(conn, client=api(measurements=[{**MEASUREMENT, "fat_percent": 18.5}]))
    hevy.sync(conn, client=api(measurements=[MEASUREMENT]))

    row = conn.execute("SELECT * FROM body_measurements WHERE date = '2026-08-12'").fetchone()
    assert row["fat_percent"] == 18.5


def test_a_failed_sync_is_recorded_and_leaves_the_cursor_alone(conn):
    hevy.sync(conn, client=api())
    good_cursor = conn.execute(
        "SELECT cursor FROM sync_state WHERE source='hevy'"
    ).fetchone()["cursor"]

    def handler(request):
        return httpx.Response(500, text="upstream exploded")

    broken = HevyClient(
        "k", client=httpx.Client(transport=httpx.MockTransport(handler), base_url=hevy.BASE_URL)
    )
    result = hevy.sync(conn, client=broken)

    assert result["ok"] is False
    row = conn.execute("SELECT * FROM sync_state WHERE source='hevy'").fetchone()
    assert row["last_status"] == "failed"
    assert "500" in row["last_error"]
    assert row["cursor"] == good_cursor


# -- normalize ----------------------------------------------------------------


def test_normalize_is_idempotent(conn):
    hevy.sync(conn, client=api(events=[{"type": "updated", "workout": WORKOUT}]))

    first = hevy.normalize(conn)
    second = hevy.normalize(conn)

    assert first == second == {"exercises": 1, "sets": 2}
    assert conn.execute("SELECT COUNT(*) c FROM workout_exercises").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM workout_sets").fetchone()["c"] == 2


def test_normalize_reparses_a_changed_payload(conn):
    hevy.sync(conn, client=api(events=[{"type": "updated", "workout": WORKOUT}]))
    trimmed = {**WORKOUT, "exercises": [{**WORKOUT["exercises"][0], "sets": []}]}
    hevy.sync(conn, client=api(events=[{"type": "updated", "workout": trimmed}]))

    assert conn.execute("SELECT COUNT(*) c FROM workout_sets").fetchone()["c"] == 0


def test_normalize_stubs_a_template_the_templates_endpoint_did_not_return(conn):
    """A custom or since-deleted template still has to satisfy the foreign key."""
    hevy.sync(
        conn,
        client=api(events=[{"type": "updated", "workout": WORKOUT}], templates=[]),
    )

    row = conn.execute("SELECT * FROM exercise_templates WHERE id = '79D0BB3A'").fetchone()
    assert row["title"] == "Bench Press (Barbell)"
    assert row["primary_muscle_group"] is None
    assert conn.execute("SELECT COUNT(*) c FROM workout_exercises").fetchone()["c"] == 1


def test_normalize_over_the_whole_table_needs_no_network(conn):
    hevy.sync(conn, client=api(events=[{"type": "updated", "workout": WORKOUT}]))
    conn.execute("DELETE FROM workout_sets")
    conn.execute("DELETE FROM workout_exercises")
    conn.commit()

    assert hevy.normalize(conn) == {"exercises": 1, "sets": 2}


def test_normalize_with_an_empty_id_list_does_nothing(conn):
    assert hevy.normalize(conn, workout_ids=[]) == {"exercises": 0, "sets": 0}
