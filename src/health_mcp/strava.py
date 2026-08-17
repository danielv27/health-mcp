"""Strava client, OAuth, and sync, against https://developers.strava.com/docs/.

Two things make this different from hevy.py, not just a copy of it:

1. Auth. Hevy is a static `api-key` header; Strava is OAuth2 with a one-time interactive
   authorization step and a refresh token that *rotates on every use* — the old one is
   invalidated the instant a new one is issued (docs/adr/0008). The rotated pair has to be
   persisted immediately, or the connection is dead until re-authorized by hand.
2. No deletion feed. `GET /athlete/activities` only filters by `after`/`before` on
   *start_date*, with no "changed since" semantics and no deletion events — Strava's
   equivalent of Hevy's events feed is a push-webhook system that needs a public HTTPS
   endpoint, off the table per ADR-0005. `sync(full=True)` reconciles deletions the coarse
   way instead: page everything, delete whatever local id didn't come back.

A consequence of (2) worth remembering: delta sync only sees activities whose *start_date*
is after the cursor. An activity edited after being synced, or uploaded later with a
back-dated start time, is invisible to a delta sync — only `--full` re-fetches it.

Tokens are stored *outside* this database, in a separate SQLite file — see docs/adr/0009.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from health_mcp.config import settings
from health_mcp.day import day_of

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
BASE_URL = "https://www.strava.com/api/v3"

REDIRECT_URI = "http://localhost/exchange_token"
SCOPE = "activity:read_all"

ACTIVITIES_PAGE_SIZE = 200

# Refresh this far ahead of expiry rather than racing a request against it.
REFRESH_MARGIN_S = 300


class StravaError(RuntimeError):
    """A sync or auth step failed in a way worth showing the user verbatim."""


class StravaClient:
    def __init__(self, access_token: str, client: httpx.Client | None = None):
        self._client = client or httpx.Client(
            base_url=BASE_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=30.0
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "StravaClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, path: str, **params: Any) -> Any:
        response = self._client.get(path, params=params)
        if response.status_code in (401, 403):
            raise StravaError(
                f"Strava rejected the access token ({response.status_code}) — run "
                "`health-mcp strava-auth` to reconnect"
            )
        if response.status_code >= 400:
            raise StravaError(f"Strava returned {response.status_code}: {response.text[:200]}")
        return response.json()

    def activities(self, after: int) -> list[dict]:
        """Every activity since the epoch-seconds `after`, oldest call first.

        Unlike Hevy's collection endpoints, there's no `page_count` up front — a page
        shorter than requested is the only signal that paging is done.
        """
        items: list[dict] = []
        page = 1
        while True:
            batch = self._get(
                "/athlete/activities", after=after, page=page, per_page=ACTIVITIES_PAGE_SIZE
            )
            items.extend(batch)
            if len(batch) < ACTIVITIES_PAGE_SIZE:
                return items
            page += 1


# -- OAuth ----------------------------------------------------------------------


def authorize_url() -> str:
    """The URL to open in a browser to start the one-time connection.

    redirect_uri deliberately points at nothing this Mac is listening on
    (docs/adr/0008) — the browser's failed redirect still carries `code` in its address
    bar, which `strava-auth` asks you to paste back in.
    """
    if not settings.strava_client_id:
        raise StravaError("HEALTH_MCP_STRAVA_CLIENT_ID is not set (expected in ~/health/.env)")
    params = (
        f"client_id={settings.strava_client_id}&redirect_uri={REDIRECT_URI}"
        f"&response_type=code&approval_prompt=auto&scope={SCOPE}"
    )
    return f"{AUTHORIZE_URL}?{params}"


def parse_code(pasted: str) -> str:
    """The `code` out of a pasted redirect URL, or the string itself if it's already bare.

    Denying access redirects with `error=access_denied` and no `code` — surfaced here
    rather than left to fail confusingly at the token exchange.
    """
    pasted = pasted.strip()
    if "://" not in pasted and "?" not in pasted:
        return pasted
    query = parse_qs(urlparse(pasted).query)
    if "error" in query:
        raise StravaError(f"Strava denied authorization: {query['error'][0]}")
    if "code" not in query:
        raise StravaError(f"no `code` found in the pasted URL: {pasted}")
    return query["code"][0]


def exchange_code(code: str, client: httpx.Client | None = None) -> dict:
    """The authorization-code grant: `code` for a first access/refresh token pair."""
    return _token_request(
        {
            "client_id": settings.strava_client_id,
            "client_secret": settings.strava_client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        client,
    )


def _refresh(refresh_token: str, client: httpx.Client | None = None) -> dict:
    return _token_request(
        {
            "client_id": settings.strava_client_id,
            "client_secret": settings.strava_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        client,
    )


def _token_request(data: dict, client: httpx.Client | None = None) -> dict:
    if not settings.strava_client_id or not settings.strava_client_secret:
        raise StravaError(
            "HEALTH_MCP_STRAVA_CLIENT_ID / HEALTH_MCP_STRAVA_CLIENT_SECRET are not set "
            "(expected in ~/health/.env)"
        )
    owned = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        response = client.post(TOKEN_URL, data=data)
        if response.status_code >= 400:
            raise StravaError(f"Strava token request failed ({response.status_code}): "
                               f"{response.text[:200]}")
        return response.json()
    finally:
        if owned:
            client.close()


# -- token storage, isolated from the main database (docs/adr/0009) -------------


def _auth_db_path() -> Path:
    return settings.db_path.parent / "strava_auth.db"


def _auth_conn() -> sqlite3.Connection:
    path = _auth_db_path()
    is_new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strava_auth (
            id            INTEGER PRIMARY KEY CHECK (id = 1),
            access_token  TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at    INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    if is_new:
        os.chmod(path, 0o600)
    return conn


def load_auth() -> dict | None:
    conn = _auth_conn()
    try:
        row = conn.execute("SELECT * FROM strava_auth WHERE id = 1").fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def store_auth(access_token: str, refresh_token: str, expires_at: int) -> None:
    conn = _auth_conn()
    try:
        conn.execute(
            """
            INSERT INTO strava_auth (id, access_token, refresh_token, expires_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at
            """,
            (access_token, refresh_token, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_access_token() -> str:
    """The current access token, refreshing first if it's within REFRESH_MARGIN_S of
    expiring. The rotated refresh token is persisted before this returns — never hold onto
    a refresh token Strava has already invalidated."""
    auth = load_auth()
    if auth is None:
        raise StravaError("Strava is not connected — run `health-mcp strava-auth` first")

    now = int(datetime.now(timezone.utc).timestamp())
    if now < auth["expires_at"] - REFRESH_MARGIN_S:
        return auth["access_token"]

    tokens = _refresh(auth["refresh_token"])
    store_auth(tokens["access_token"], tokens["refresh_token"], tokens["expires_at"])
    return tokens["access_token"]


# -- sync -------------------------------------------------------------------------


def sync(conn: sqlite3.Connection, full: bool = False, client: StravaClient | None = None) -> dict:
    """Pull activities since the cursor into the database.

    `full=True` replays from the epoch and deletes any local activity not present in that
    full fetch — the only deletion signal available, since Strava's activities endpoint
    carries no delete events (see module docstring).
    """
    started_at = int(datetime.now(timezone.utc).timestamp())

    owned = client is None
    try:
        if client is None:
            client = StravaClient(_ensure_access_token())

        since = 0 if full else int(_cursor(conn) or 0)
        activities = client.activities(since)
        touched = _store_activities(conn, activities)

        deleted = 0
        if full:
            deleted = _reconcile(conn, {a["id"] for a in activities})

        conn.commit()
        _record(conn, "success", cursor=str(started_at))
        return {"ok": True, "activities": len(touched), "deleted": deleted, "cursor": started_at}
    except (StravaError, httpx.HTTPError, sqlite3.Error, ValueError, KeyError) as exc:
        conn.rollback()
        return _fail(conn, str(exc) if isinstance(exc, StravaError) else f"{type(exc).__name__}: {exc}")
    finally:
        if owned and client is not None:
            client.close()


def _store_activities(conn: sqlite3.Connection, activities: list[dict]) -> list[str]:
    for activity in activities:
        activity_id = str(activity["id"])
        start_date = activity["start_date"]
        conn.execute(
            """
            INSERT INTO activities (id, name, type, sport_type, start_date, date,
                elapsed_time_s, moving_time_s, distance_m, total_elevation_gain_m,
                average_speed_mps, max_speed_mps, average_heartrate, max_heartrate, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name, type = excluded.type, sport_type = excluded.sport_type,
                start_date = excluded.start_date, date = excluded.date,
                elapsed_time_s = excluded.elapsed_time_s, moving_time_s = excluded.moving_time_s,
                distance_m = excluded.distance_m,
                total_elevation_gain_m = excluded.total_elevation_gain_m,
                average_speed_mps = excluded.average_speed_mps,
                max_speed_mps = excluded.max_speed_mps,
                average_heartrate = excluded.average_heartrate,
                max_heartrate = excluded.max_heartrate, raw = excluded.raw
            """,
            (
                activity_id,
                activity.get("name") or "",
                activity.get("type") or "",
                activity.get("sport_type") or activity.get("type") or "",
                start_date,
                day_of(datetime.fromisoformat(start_date)).isoformat(),
                activity["elapsed_time"],
                activity["moving_time"],
                activity["distance"],
                activity.get("total_elevation_gain"),
                activity.get("average_speed"),
                activity.get("max_speed"),
                activity.get("average_heartrate"),
                activity.get("max_heartrate"),
                json.dumps(activity),
            ),
        )
    return [str(activity["id"]) for activity in activities]


def _reconcile(conn: sqlite3.Connection, seen_ids: set[str]) -> int:
    """Delete any local activity not present in a full fetch. `seen_ids` come back from
    the API as ints; compared here against the TEXT ids stored in the table."""
    seen = {str(i) for i in seen_ids}
    rows = conn.execute("SELECT id FROM activities").fetchall()
    stale = [row["id"] for row in rows if row["id"] not in seen]
    for activity_id in stale:
        conn.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
    return len(stale)


# -- sync_state ---------------------------------------------------------------


def _cursor(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT cursor FROM sync_state WHERE source = 'strava'").fetchone()
    return row["cursor"] if row else None


def _record(conn: sqlite3.Connection, status: str, error: str | None = None,
            cursor: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO sync_state (source, cursor, last_run_at, last_status, last_error)
        VALUES ('strava', ?, ?, ?, ?)
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
    _record(conn, "failed", error=error)
    return {"ok": False, "error": error}


def _stamp(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")
