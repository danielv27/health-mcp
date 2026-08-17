"""Tests for strava.py.

Client tests drive `StravaClient` through an `httpx.MockTransport`, same style as
test_hevy.py — pagination and auth-error handling are actually exercised, not stubbed
over. `ACTIVITY` mirrors the documented SummaryActivity shape from
developers.strava.com/docs/reference/.
"""

import json
import stat
from datetime import datetime, timezone

import httpx
import pytest

from health_mcp import strava
from health_mcp.db import migrate, rw

ACTIVITY = {
    "id": 987654321,
    "name": "Morning Run",
    "type": "Run",
    "sport_type": "Run",
    "start_date": "2026-08-10T06:30:00Z",
    "start_date_local": "2026-08-10T08:30:00Z",
    "elapsed_time": 1800,
    "moving_time": 1750,
    "distance": 5000.0,
    "total_elevation_gain": 42.0,
    "average_speed": 2.86,
    "max_speed": 4.1,
    "average_heartrate": 152.3,
    "max_heartrate": 178,
}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    db_path = tmp_path / "health.db"
    monkeypatch.setattr(strava.settings, "db_path", db_path)
    migrate(db_path)
    connection = rw(db_path)
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setattr(strava.settings, "strava_client_id", "test-client-id")
    monkeypatch.setattr(strava.settings, "strava_client_secret", "test-client-secret")


def fake_client(handler) -> "strava.StravaClient":
    transport = httpx.MockTransport(handler)
    return strava.StravaClient(
        "test-token",
        client=httpx.Client(
            transport=transport, base_url=strava.BASE_URL,
            headers={"Authorization": "Bearer test-token"},
        ),
    )


def api(activities=(), seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        page = int(request.url.params.get("page", 1))
        return httpx.Response(200, json=list(activities) if page == 1 else [])

    return fake_client(handler)


# -- client ---------------------------------------------------------------------


def test_activities_stops_when_a_page_is_shorter_than_per_page():
    full_page = [{"id": i} for i in range(strava.ACTIVITIES_PAGE_SIZE)]

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", 1))
        return httpx.Response(200, json=full_page if page == 1 else [{"id": "last"}])

    with fake_client(handler) as client:
        result = client.activities(after=0)
    assert len(result) == strava.ACTIVITIES_PAGE_SIZE + 1


def test_activities_requests_the_documented_page_size_cap():
    seen = []
    with api(seen=seen) as client:
        client.activities(after=0)
    assert seen[-1].url.params["per_page"] == str(strava.ACTIVITIES_PAGE_SIZE)


def test_activities_sends_the_after_cursor():
    seen = []
    with api(seen=seen) as client:
        client.activities(after=1234567890)
    assert seen[-1].url.params["after"] == "1234567890"


def test_unauthorized_says_how_to_reconnect():
    def handler(request):
        return httpx.Response(401, json={"error": "unauthorized"})

    with fake_client(handler) as client:
        with pytest.raises(strava.StravaError, match="strava-auth"):
            client.activities(after=0)


# -- OAuth ------------------------------------------------------------------------


def test_authorize_url_carries_client_id_and_scope():
    url = strava.authorize_url()
    assert "client_id=test-client-id" in url
    assert "scope=activity:read_all" in url
    assert "redirect_uri=http://localhost/exchange_token" in url


def test_authorize_url_without_a_client_id_is_a_visible_error(monkeypatch):
    monkeypatch.setattr(strava.settings, "strava_client_id", None)
    with pytest.raises(strava.StravaError, match="STRAVA_CLIENT_ID"):
        strava.authorize_url()


def test_parse_code_accepts_a_bare_code():
    assert strava.parse_code("abc123") == "abc123"


def test_parse_code_extracts_from_a_redirect_url():
    url = "http://localhost/exchange_token?state=&code=abc123&scope=read,activity:read_all"
    assert strava.parse_code(url) == "abc123"


def test_parse_code_surfaces_a_denied_authorization():
    url = "http://localhost/exchange_token?state=&error=access_denied"
    with pytest.raises(strava.StravaError, match="denied"):
        strava.parse_code(url)


def test_exchange_code_posts_the_authorization_code_grant():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={
            "access_token": "access1", "refresh_token": "refresh1", "expires_at": 100,
            "athlete": {"firstname": "Daniel"},
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    tokens = strava.exchange_code("the-code", client=client)

    assert tokens["access_token"] == "access1"
    body = seen[-1].read().decode()
    assert "grant_type=authorization_code" in body
    assert "code=the-code" in body


def test_token_request_without_credentials_is_a_visible_error(monkeypatch):
    monkeypatch.setattr(strava.settings, "strava_client_secret", None)
    with pytest.raises(strava.StravaError, match="STRAVA_CLIENT"):
        strava.exchange_code("the-code")


def test_token_request_failure_includes_the_status():
    def handler(request):
        return httpx.Response(400, text="invalid code")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(strava.StravaError, match="400"):
        strava.exchange_code("bad-code", client=client)


# -- token storage, isolated from the main database (docs/adr/0009) ---------------


def test_store_and_load_auth_round_trips(conn):
    strava.store_auth("access1", "refresh1", 1234567890)
    auth = strava.load_auth()
    assert auth["access_token"] == "access1"
    assert auth["refresh_token"] == "refresh1"
    assert auth["expires_at"] == 1234567890


def test_store_auth_overwrites_the_single_row(conn):
    strava.store_auth("a1", "r1", 100)
    strava.store_auth("a2", "r2", 200)
    auth = strava.load_auth()
    assert auth["access_token"] == "a2"
    assert auth["refresh_token"] == "r2"


def test_load_auth_before_connecting_is_none(conn):
    assert strava.load_auth() is None


def test_auth_db_file_is_chmod_600(conn):
    strava.store_auth("a", "r", 100)
    mode = stat.S_IMODE(strava._auth_db_path().stat().st_mode)
    assert mode == 0o600


def test_strava_auth_table_is_not_in_the_main_database(conn):
    """The whole point of the separate file: `db.ro()` / the `query` tool must never be
    able to select a live Strava bearer token."""
    strava.store_auth("a", "r", 100)
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'strava_auth'"
    ).fetchone()
    assert row is None


# -- token refresh ------------------------------------------------------------------


def test_ensure_access_token_returns_the_stored_token_when_not_expiring_soon(conn):
    future = int(datetime.now(timezone.utc).timestamp()) + 3600
    strava.store_auth("access1", "refresh1", future)
    assert strava._ensure_access_token() == "access1"


def test_ensure_access_token_without_a_connection_is_a_visible_error(conn):
    with pytest.raises(strava.StravaError, match="not connected"):
        strava._ensure_access_token()


def test_ensure_access_token_refreshes_within_the_margin_and_persists_the_rotated_pair(
    conn, monkeypatch
):
    soon = int(datetime.now(timezone.utc).timestamp()) + 60  # inside REFRESH_MARGIN_S
    strava.store_auth("old-access", "old-refresh", soon)
    calls = []

    def fake_refresh(refresh_token, client=None):
        calls.append(refresh_token)
        return {
            "access_token": "new-access", "refresh_token": "new-refresh",
            "expires_at": soon + 21600,
        }

    monkeypatch.setattr(strava, "_refresh", fake_refresh)

    token = strava._ensure_access_token()
    assert token == "new-access"
    assert strava.load_auth()["refresh_token"] == "new-refresh"

    # A second call with the token now far from expiry must not refresh (and therefore
    # not try to use the already-invalidated old refresh token) again.
    strava._ensure_access_token()
    assert calls == ["old-refresh"]


# -- sync -------------------------------------------------------------------------


def test_sync_without_a_connection_is_a_visible_failure(conn):
    result = strava.sync(conn)

    assert result["ok"] is False
    row = conn.execute("SELECT * FROM sync_state WHERE source = 'strava'").fetchone()
    assert row["last_status"] == "failed"
    assert "not connected" in row["last_error"]


def test_sync_stores_activity_and_derived_day(conn):
    result = strava.sync(conn, client=api(activities=[ACTIVITY]))

    assert result["ok"] is True
    assert result["activities"] == 1
    row = conn.execute("SELECT * FROM activities").fetchone()
    assert row["id"] == "987654321"
    assert row["name"] == "Morning Run"
    assert row["sport_type"] == "Run"
    assert row["distance_m"] == 5000.0
    # 06:30 UTC on the 10th is 08:30 Amsterdam — the same Day, not a boundary case.
    assert row["date"] == "2026-08-10"
    assert json.loads(row["raw"])["name"] == "Morning Run"


def test_sync_advances_the_cursor_and_the_next_sync_sends_it(conn):
    strava.sync(conn, client=api())
    cursor = conn.execute(
        "SELECT cursor FROM sync_state WHERE source = 'strava'"
    ).fetchone()["cursor"]
    assert cursor.isdigit()

    seen = []
    strava.sync(conn, client=api(seen=seen))
    assert seen[-1].url.params["after"] == cursor


def test_first_sync_asks_since_the_epoch(conn):
    seen = []
    strava.sync(conn, client=api(seen=seen))
    assert seen[-1].url.params["after"] == "0"


def test_full_sync_replays_from_the_epoch(conn):
    strava.sync(conn, client=api())
    seen = []
    strava.sync(conn, full=True, client=api(seen=seen))
    assert seen[-1].url.params["after"] == "0"


def test_full_sync_reconciles_a_deletion(conn):
    strava.sync(conn, client=api(activities=[ACTIVITY]))
    assert conn.execute("SELECT COUNT(*) c FROM activities").fetchone()["c"] == 1

    other = {**ACTIVITY, "id": 111}
    result = strava.sync(conn, full=True, client=api(activities=[other]))

    assert result["deleted"] == 1
    ids = {row["id"] for row in conn.execute("SELECT id FROM activities").fetchall()}
    assert ids == {"111"}


def test_delta_sync_does_not_reconcile_deletions(conn):
    strava.sync(conn, client=api(activities=[ACTIVITY]))
    result = strava.sync(conn, client=api())

    assert result["deleted"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM activities").fetchone()["c"] == 1


def test_sync_upserts_on_a_repeat_id(conn):
    strava.sync(conn, client=api(activities=[ACTIVITY]))
    edited = {**ACTIVITY, "name": "Morning Run (edited)"}
    strava.sync(conn, client=api(activities=[edited]))

    row = conn.execute("SELECT * FROM activities").fetchone()
    assert row["name"] == "Morning Run (edited)"
    assert conn.execute("SELECT COUNT(*) c FROM activities").fetchone()["c"] == 1


def test_a_database_failure_is_recorded_not_raised(conn):
    conn.execute("DROP TABLE activities")
    conn.commit()

    result = strava.sync(conn, client=api(activities=[ACTIVITY]))

    assert result["ok"] is False
    row = conn.execute("SELECT * FROM sync_state WHERE source = 'strava'").fetchone()
    assert row["last_status"] == "failed"
    assert "activities" in row["last_error"]


def test_a_failed_sync_is_recorded_and_leaves_the_cursor_alone(conn):
    strava.sync(conn, client=api())
    good_cursor = conn.execute(
        "SELECT cursor FROM sync_state WHERE source = 'strava'"
    ).fetchone()["cursor"]

    def handler(request):
        return httpx.Response(500, text="upstream exploded")

    broken = fake_client(handler)
    result = strava.sync(conn, client=broken)

    assert result["ok"] is False
    row = conn.execute("SELECT * FROM sync_state WHERE source = 'strava'").fetchone()
    assert row["last_status"] == "failed"
    assert "500" in row["last_error"]
    assert row["cursor"] == good_cursor
