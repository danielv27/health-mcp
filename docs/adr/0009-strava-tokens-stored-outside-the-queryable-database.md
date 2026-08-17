# Strava tokens stored outside the queryable database

[ADR-0006](./0006-one-read-only-sql-tool-instead-of-narrow-read-tools.md) made `query` a
single read-only SQL tool over *the whole schema*, deliberately, because the questions
worth asking of training and food data aren't knowable in advance. That reasoning holds
for every table in `health.db` — a workout, a food log entry, a sync error, all as
harmless to expose to a `SELECT` as to a person reading the file directly.

A Strava access/refresh token pair is not that kind of value. It's a live credential:
whoever holds the refresh token can mint new access tokens indefinitely and read (this
app's scope is `activity:read_all`) the account's activity history. `query`'s whole point
is that the model chooses what to select — a confused question, or a prompt injected
through some future untrusted text field, could put a working bearer token in a chat
transcript. That's a materially worse outcome than the same accident with a food entry.

So `strava_auth` — access token, refresh token, expiry — lives in its own SQLite file,
`~/health/strava_auth.db`, `chmod 600`, created and read only by `strava.py`'s own
connection helpers. `db.ro()`, and therefore the `query` tool, never opens it — the
isolation is structural (a different file), not a permission the model could be talked
past.

## Considered Options

- **A table in `health.db`** (e.g. alongside `sync_state`) — rejected. Simpler, one file,
  but puts a live credential one `SELECT` away from the same broad read surface ADR-0006
  intentionally left ungated.
- **`.env`**, like the static Hevy API key — rejected. The refresh token *rotates on every
  use* (docs/adr/0008); the app would need to rewrite `.env` on every sync, which is a
  worse fit than a database row for something that changes on every call.
- **A separate SQLite file, touched only by `strava.py`** — chosen.

## Consequences

Two SQLite files under `~/health/` instead of one. `strava.py` owns a second small
connection helper (`_auth_conn`, creating the file and its one table with `CREATE TABLE IF
NOT EXISTS` rather than going through the main migration runner — a one-table file that
isn't part of the queryable schema doesn't need `schema_version` tracking). Nightly backup
(PLAN.md "Access") needs to cover this file too, or a lost Strava connection means running
`strava-auth` again by hand rather than restoring from backup — an acceptable trade, since
re-authorizing is a two-minute manual step, not a data-loss event the way losing the food
log would be.
