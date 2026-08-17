# Personal Health MCP Server

## Context

A single MCP server that lets a Claude session answer questions spanning training and
eating — "what did I lift this week", "how much protein yesterday", "did intake track
with volume" — without copying data between apps. Training data comes from Hevy
(strength) and Strava (cardio — runs, rides). Daily step counts and Apple Watch-native
workout sessions are imported by hand from Apple Health CSV exports. Eating data is
logged by hand against a small, hand-curated Catalog of the foods actually eaten.

The server runs on this Mac, registered as a project-scoped MCP server
(`.mcp.json`) that any Claude Code session opened in this repo loads automatically —
including one reached from a phone via Claude Code's own remote access. It speaks
**stdio** — the agent launches it as a subprocess on the same host. There is no HTTP
endpoint, no TLS, and no token.

See [`CONTEXT.md`](./CONTEXT.md) for the vocabulary and [`docs/adr/`](./docs/adr/) for why
the shape is what it is. In particular: [no Albert Heijn integration](./docs/adr/0004-no-albert-heijn-integration-in-v1.md),
[stdio over SSH](./docs/adr/0005-stdio-over-ssh-instead-of-public-https.md),
[own the data](./docs/adr/0003-own-the-data-rather-than-compose-external-mcp-servers.md),
[one SQL read tool](./docs/adr/0006-one-read-only-sql-tool-instead-of-narrow-read-tools.md),
[Claude Code remote access instead of a VM](./docs/adr/0007-claude-code-remote-access-instead-of-a-vm.md),
[Strava OAuth by manual paste](./docs/adr/0008-strava-oauth-captured-by-manual-paste.md),
[Strava tokens outside the queryable database](./docs/adr/0009-strava-tokens-stored-outside-the-queryable-database.md),
[daily step count deduplicated by per-source daily max](./docs/adr/0010-daily-step-count-deduplicated-by-per-source-daily-max.md),
[Hevy-sourced Apple Health rows excluded at import](./docs/adr/0011-hevy-sourced-apple-health-rows-excluded-at-import.md).

**Hevy Pro is active** as of 2026-08-12, and the client was rewritten against observed
responses rather than docs. The two-phase shape stayed anyway: `sync` persists the raw
JSON payload first and normalizes into `workout_exercises` / `workout_sets` as a
**separate, re-runnable pass**, so a parsing mistake costs a re-parse of stored data
rather than a re-sync. That bet paid for itself immediately — see the quirks table below.

## Status

Design is settled — the decisions below came out of a grilling session and are recorded
in `docs/adr/`. Hevy, Strava, step import, and food are all now built.

| | |
|---|---|
| Done | `pyproject.toml`; `day.py`; `config.py`; `migrations/001_init.sql` + `002_strava.sql` + `003_steps.sql` + `004_apple_workouts.sql` (12 tables); `db.py` (rw/ro + migration runner); `tools/food.py`; `tools/query.py`; `hevy.py` (client + delta/full sync + `normalize`); `strava.py` (OAuth + client + delta/full sync, tokens isolated per ADR-0009); `steps.py` (Apple Health CSV import, deduplicated per ADR-0010); `apple_workouts.py` (Apple Health workout CSV import, Hevy rows dropped per ADR-0011); `tools/training.py`; `tools/steps.py`; `tools/apple_workouts.py`; `server.py` (all 9 tools registered); `cli.py` (`serve`, `sync [--full]`, `normalize`, `strava-auth`, `sync-strava [--full]`, `import-steps`, `import-workouts`); `.mcp.json` (project-scoped, see ADR-0007) — **132 tests passing** |
| Verified live | 2026-08-12 (Hevy): 102 workouts / 583 exercises / 1,961 sets / 451 templates / 11 measurements, in ~3 s. Full and delta syncs agree, `PRAGMA foreign_key_check` clean, cross-source volume-vs-protein join works, a deliberately broken key lands in `sync_state.last_error` and leaves the cursor untouched. 2026-08-14 (steps): a real 9-year, 180,601-row export imported cleanly — see "Step import" below for the resulting counts. 2026-08-14 (Apple workouts): a real 519-row, six-file export imported to 414 rows (105 Hevy-sourced correctly dropped) — see "Apple workout import" below |
| Paused | Strava is fully built and unit-tested but **not connected to a real account yet** — as of 2026-08-14, Strava requires an active paid subscription ($11.99/mo) for Standard Tier API access (their developer-program change took effect 2026-06-01). Decided to hold off on subscribing for now; see "Strava setup (when ready)" below for the exact steps to pick this back up |
| Not started | Nightly backup (now needs to cover `strava_auth.db` too, see ADR-0009), `launchd` job for `sync` / `sync-strava` |

## Architecture

```
phone ──Claude Code remote access──> this Mac ──> Claude Code ──stdio──> health-mcp
                                                                              │
                                                                       SQLite (~/health/health.db)
                                                                              │
                                                          health-mcp sync ────> Hevy API (api-key)
                                                          health-mcp sync-strava > Strava API (OAuth)
```

Strava's OAuth token pair lives in a second, separate file (`~/health/strava_auth.db`),
never opened by the `query` tool — see ADR-0009.

One process, one file, no network listener. `.mcp.json` in this repo registers
`health-mcp serve` as a project-scoped MCP server, so any Claude Code session opened
here — phone or laptop — loads it automatically. The same binary also runs `health-mcp
sync` (not yet wired to a scheduler; see ADR-0007) against the same database.

### Layout

```
health-mcp/
  .mcp.json                 # registers `health-mcp serve` as a project-scoped MCP server
  pyproject.toml            # uv-managed; deps: mcp, httpx, pydantic-settings
  src/health_mcp/
    server.py               # MCPServer, tool registration
    cli.py                  # `serve`, `sync`, `strava-auth`, `sync-strava`, `import-steps`
    config.py               # env-var settings
    day.py                  # the 04:00 Amsterdam day rule — one function, unit-tested
    db.py                   # connections (rw + ro), migration runner
    migrations/001_init.sql, 002_strava.sql, 003_steps.sql, 004_apple_workouts.sql
    hevy.py                 # Hevy client + incremental sync
    strava.py               # Strava OAuth + client + incremental sync (ADR-0008/0009)
    steps.py                # Apple Health CSV import, per-source-max dedup (ADR-0010)
    apple_workouts.py       # Apple Health workout CSV import, Hevy rows dropped (ADR-0011)
    tools/
      food.py               # add_product, log_food, delete_food_entry, find_product
      training.py           # sync_workouts, sync_activities
      steps.py              # import_steps
      apple_workouts.py     # import_workouts
      query.py              # query(sql)
  tests/
```

Verified against `mcp` 2.0.0 (released 2026-07-28) on 2026-08-11: the server class is
`from mcp.server import MCPServer`, and `FastMCP` is the retired v1 name. Tools register
with `@mcp.tool()` over type-hinted functions. For stdio, `mcp.run()` is all that's
needed — the HTTP machinery (`streamable_http_app`, `TransportSecuritySettings`,
`TokenVerifier`) exists but is deliberately unused here, see ADR-0005.

## Decisions locked in this session

| Question | Decision |
|---|---|
| Day boundary | 04:00–04:00 `Europe/Amsterdam`, derived at write time ([ADR-0001](./docs/adr/0001-day-runs-0400-to-0400-amsterdam.md)) |
| Quantity unit | Grams, always. `entered_as` keeps the phrasing for display only |
| Food source | Manual Catalog. No Albert Heijn ([ADR-0004](./docs/adr/0004-no-albert-heijn-integration-in-v1.md)) |
| Generic foods | Model-supplied Macros, marked `estimated` — no external nutrition API |
| Hevy | Own client and sync ([ADR-0003](./docs/adr/0003-own-the-data-rather-than-compose-external-mcp-servers.md)) |
| Transport | stdio ([ADR-0005](./docs/adr/0005-stdio-over-ssh-instead-of-public-https.md)) |
| Product resolution | Explicit `find_product` → `product_id`. No fuzzy matching inside writes |
| Read surface | One `query(sql)` tool, read-only ([ADR-0006](./docs/adr/0006-one-read-only-sql-tool-instead-of-narrow-read-tools.md)) |
| Sync trigger | `cron` every 6h, plus an explicit `sync_workouts` tool |
| Body measurements | In v1 — same sync, one table, and needed for protein-per-kg |
| Strava OAuth callback | Manual paste from a failed `localhost` redirect, never a listener ([ADR-0008](./docs/adr/0008-strava-oauth-captured-by-manual-paste.md)) |
| Strava token storage | Separate SQLite file, outside anything `query` can reach ([ADR-0009](./docs/adr/0009-strava-tokens-stored-outside-the-queryable-database.md)) |
| Step data source | Manual Apple Health CSV export, no API/listener — dropped in by hand as a chat attachment |
| Multi-source step overlap | Max of each source's daily total, not a sum — measured 19% overcounted otherwise ([ADR-0010](./docs/adr/0010-daily-step-count-deduplicated-by-per-source-daily-max.md)) |
| Hevy rows in Apple Health exports | Dropped at import, not just tagged — already covered by `workouts` via the direct Hevy sync, confirmed by matching row counts ([ADR-0011](./docs/adr/0011-hevy-sourced-apple-health-rows-excluded-at-import.md)) |

## Storage

SQLite in WAL mode. Plain `.sql` migrations applied in order against a `schema_version`
table — no ORM, no Alembic.

| Table | Columns of note |
|---|---|
| `products` | `id`, `name`, `brand`, `source` (`verified`\|`estimated`), per-100 g `kcal`/`protein`/`carbs`/`fat` (+ nullable fibre, sugar, sat fat, salt), `note`, `created_at` |
| `food_log` | `id`, `logged_at` (UTC), `date` (04:00 rule), nullable `product_id`, `name`, `source`, `grams`, `entered_as`, **absolute** `kcal`/`protein`/`carbs`/`fat` for the entry, `note` |
| `workouts` | `id` (Hevy), `title`, `start_time`, `end_time`, `date`, `updated_at`, `raw` JSON |
| `workout_exercises` | `workout_id`, `idx`, `exercise_template_id`, `title` |
| `workout_sets` | `workout_exercise_id`, `idx`, `type`, `weight_kg`, `reps`, `rpe`, `duration_s`, `distance_m` |
| `exercise_templates` | `id`, `title`, `primary_muscle_group`, `secondary_muscle_groups` JSON, `equipment` |
| `body_measurements` | `date` PK, `weight_kg`, `fat_percent` |
| `activities` | `id` (Strava), `name`, `type`, `sport_type`, `start_time`, `date`, `elapsed_time_s`, `moving_time_s`, `distance_m`, `total_elevation_gain_m`, `average_speed_mps`, `max_speed_mps`, `average_heartrate`, `max_heartrate`, `raw` JSON |
| `daily_steps` | `date` PK, `steps`, `source` (which device's daily total won the max, ADR-0010) |
| `apple_workouts` | `id` (synthetic `source:start_date`), `source` (`Apple Watch`\|`Strava`; `Hevy` dropped at import, ADR-0011), `workout_type`, `start_date`, `end_date`, `date`, `duration_s`, `energy_kcal`, `distance_m` |
| `sync_state` | `source` PK, `cursor`, `last_run_at`, `last_status`, `last_error` |

`food_log` stores absolute totals rather than a reference, so history can't be rewritten
by a later edit ([ADR-0002](./docs/adr/0002-food-log-entries-store-macros-not-references.md)).
`sync_state` carries `last_status`/`last_error` specifically so a cron sync that has been
failing for a week is one `query` away from being visible.

**`strava_auth` is deliberately not in this file.** The Strava access/refresh token pair
lives in its own SQLite file, `~/health/strava_auth.db`, which `db.ro()` (and therefore
`query`) never opens — see [ADR-0009](./docs/adr/0009-strava-tokens-stored-outside-the-queryable-database.md).

Index `food_log(date)`, `workouts(date)`, `workouts(start_time)`,
`workout_exercises(workout_id)`, `workout_sets(workout_exercise_id)`, `activities(date)`,
`activities(start_date)`.

## Tools

Nine. Writes are narrow and explicit; reads are one tool.

**Writes**
- `add_product(name, kcal_100g, protein_100g, carbs_100g, fat_100g, brand=None, source="verified", ...)`
  — adds to the Catalog.
- `log_food(grams, product_id=None, name=None, macros=None, entered_as=None, at=None)`
  — either a Catalog Product *or* a one-off with model-supplied Macros marked `estimated`.
  Computes `date` via the 04:00 rule and writes absolute totals.
- `delete_food_entry(id)`
- `sync_workouts(full=False)` — delta by default.
- `sync_activities(full=False)` — delta by default; delta only sees activities whose
  *start_date* is after the last sync, see "Strava sync" below.
- `import_steps(path)` — import an Apple Health step-count CSV export, dropped in by hand
  (no API, no cursor). Always reprocesses the whole file and upserts by day, so
  reimporting an overlapping export is harmless. See "Step import" below.
- `import_workouts(paths)` — import Apple Health workout CSV export(s) (one file per
  workout type). Drops any row sourced from Hevy — that training already exists in
  `workouts` via `sync_workouts`, see ADR-0011. See "Apple workout import" below.

**Reads**
- `find_product(query=None)` — returns the Catalog, filtered. The resolution step before
  any `log_food` against a Product.
- `query(sql)` — read-only, schema in the description.

Descriptions must be specific about *when* to call each; that drives tool selection more
than anything else.

## Hevy sync

**The OpenAPI spec is at `https://api.hevyapp.com/docs/` — read it rather than guessing.**
It is browsable as Swagger UI; the machine-readable spec is at `docs/swagger.json`, and
the caps below live in the parameter *descriptions*, not in JSON Schema `maximum`.

Auth is one `api-key: <uuid>` header on `https://api.hevyapp.com/v1`. Collection
endpoints answer `{"page": n, "page_count": m, "<collection>": [...]}` — page until
`page_count`, there is no next-link.

| Endpoint | Use | `pageSize` max |
|---|---|---|
| `GET /v1/workouts/events?since` | everything — updates **and** deletions | 10 |
| `GET /v1/exercise_templates` | `exercise_template_id` → muscle group | 100 |
| `GET /v1/body_measurements` | weight / body-fat series | 10 |

`GET /v1/workouts` exists but **isn't used**: `since` defaults to `1970-01-01T00:00:00Z`,
so an events replay from the epoch returns the whole history *and* the deletions, which
makes a full resync the same code path as a delta. This was measured — an epoch replay
returns 102 workouts, matching `GET /v1/workouts/count`.

Two documented details the code leans on: events are ordered **newest to oldest** (so the
first event naming a workout wins, and a deletion correctly supersedes an older edit of
the same workout), and deletion events are flat — `{"type": "deleted", "id",
"deleted_at"}` — rather than nesting a workout the way `updated` does.

### Where the spec and the API disagree

Both are handled in `hevy.py`, and both were found by hitting the API:

| | |
|---|---|
| Empty event feed | Answers `{"workouts": []}` instead of `{"events": [...]}` — the collection key changes when the feed is empty. Undocumented; the client accepts either, and without this every no-op sync fails |
| Equipment | Spec says `equipment_category`, the API sends `equipment`. Both are read |

### The cursor

There is no server-issued cursor; `since` is just a timestamp. Sync stores **the moment
it started**, captured before the first request, so anything saved mid-sync is picked up
next time. Re-delivery is harmless because every write is an upsert. The cursor advances
only on success, so a failed sync retries the same window rather than skipping it.

Sync is two phases against the same data, and they are separable on purpose:

1. **Fetch** — write each workout's raw JSON into `workouts.raw`, advance the cursor.
2. **Normalize** — read `workouts.raw`, populate `workout_exercises` / `workout_sets`.
   Idempotent and re-runnable over the whole table (`health-mcp normalize`), with no
   network access.

`--full` replays from the epoch and re-parses the whole table — the "make the local copy
right" path when the cursor has drifted. It is the same code as a delta with a different
`since`, not a second implementation.

Not yet scheduled. `0 */6 * * * health-mcp sync >> ~/health/sync.log 2>&1`, or a
`launchd` job (ADR-0007).

## Strava sync

Confirmed against `developers.strava.com` on 2026-08-14. Auth is OAuth2 — one `client_id`
+ `client_secret` (`.env`, static, like the Hevy key), plus a per-connection access/refresh
token pair that lives in its own file (ADR-0009). `health-mcp strava-auth` does the
one-time interactive authorization (ADR-0008); `sync-strava` / `sync_activities` use the
stored tokens afterward, refreshing automatically within 5 minutes of expiry and
persisting the rotated refresh token immediately — Strava invalidates the old one the
instant a new one is issued, so this can never be deferred.

| Endpoint | Use | `per_page` max |
|---|---|---|
| `POST /oauth/token` | code exchange + refresh (`grant_type=authorization_code` / `refresh_token`) | — |
| `GET /athlete/activities?after&page&per_page` | activity summaries since a cursor | 200 |

Unlike Hevy's collection endpoints, there's no `page_count` in the response — pagination
stops when a page comes back shorter than requested. Rate limit is 100 requests/15 min,
1000/day (default, non-upload) — a personal delta sync never gets close.

### The cursor, and what it misses

Same shape as Hevy's: the moment sync started is captured before the first request and
becomes next time's `after`, advancing only on success. The difference is what `after`
filters *on* — Strava's activities endpoint has no "changed since" semantics, only
`after`/`before` on **start_date**. Two consequences, written down once rather than
rediscovered:

- An activity **edited** after being synced (renamed, corrected) keeps its old start_date,
  so a delta sync never sees the edit. Only `--full` re-fetches and overwrites it.
- An activity **uploaded later with a back-dated start time** (a GPS device synced days
  after a run) has a start_date the delta cursor already passed, so it's invisible to
  delta sync too — again, only `--full` catches it.

### Deletions

No deletion feed either — Strava's equivalent of Hevy's events stream is a push-webhook
system, which needs a public HTTPS endpoint (off the table per ADR-0005, same reasoning
as Hevy's transport). `--full` reconciles anyway: it pages every activity from the epoch
and deletes any local `activities` row whose id didn't come back. Coarser than Hevy's
event-sourced reconciliation, but the only signal available without a listener.

### Strava setup (when ready)

Everything below is built; this project is just paused before the first real connection —
see "Status". Strava paywalled Standard Tier API access starting 2026-06-01: it takes an
active paid Strava subscription (their regular membership, $11.99/mo US, not a separate
developer fee) to register and use an app — confirmed via web search 2026-08-14, since
Strava's own announcement doesn't spell out whether the free tier blocks registration or
only API calls. Re-check `strava.com/settings/api` directly before assuming the price
hasn't moved.

Once subscribed:

1. **Register an app** at [strava.com/settings/api](https://www.strava.com/settings/api):
   Application Name (anything), Category (anything), Website (anything, e.g.
   `http://localhost`), and — the one field that has to be exact —
   **Authorization Callback Domain: `localhost`** (bare, no `http://`, no path). Submit to
   get a **Client ID** and **Client Secret**.
2. **Set `.env`**: `HEALTH_MCP_STRAVA_CLIENT_ID` / `HEALTH_MCP_STRAVA_CLIENT_SECRET`
   (placeholders already there, empty).
3. **Connect**: `uv run health-mcp strava-auth` — prints an authorize URL, you approve in
   the browser, it redirects to a `localhost` URL that fails to load (nothing's listening,
   by design — ADR-0008); paste that URL (or just the `code` param) back into the prompt.
4. **Sync**: `uv run health-mcp sync-strava`, then confirm via `query`:
   `SELECT * FROM activities` and `SELECT * FROM sync_state WHERE source = 'strava'`.

## Step import

No API, so no `hevy.py`/`strava.py`-style client, cursor, or `sync_state` row — a step
export from Apple Health (via a third-party export app; "Simple Health Export CSV" is
what's been used so far, any exporter producing the same HealthKit CSV columns works)
gets dropped into a Claude Code chat as an attachment, and `import_steps(path)` (or `health-mcp
import-steps <path>` from a terminal) reads it from wherever it landed.

**Workflow**: whenever there's a fresh export worth bringing in, attach the CSV to a
message in this repo's Claude Code chat and ask for it to be imported. `import_steps`
always reprocesses the *entire* file and upserts `daily_steps` by date — there's no
delta concept, so a repeated or overlapping export is harmless; each date just gets
recomputed from whatever rows are in the file, not summed on top of what's already there.

Each raw CSV row is one HealthKit sample: `type`, `sourceName` (which device), `startDate`,
`unit`, `value`. Rows are bucketed by (Day, source) and summed within a bucket, then a
day's stored count is the **max across sources**, not a sum — see
[ADR-0010](./docs/adr/0010-daily-step-count-deduplicated-by-per-source-daily-max.md) for
why: a phone and a watch each report their own full day of steps, and summing both
overcounted a real 9-year export by 19%. The `source` column records which device won, so
a suspicious day is one `query` away from being explainable.

The importer validates `type == HKQuantityTypeIdentifierStepCount` and `unit == 'count'`
on every row and raises immediately if either doesn't match — a wrong file (heart rate,
distance, a different export format) fails loudly rather than silently storing garbage.

## Apple workout import

Same shape as Step import — no API, no cursor, a CSV dropped into chat. The difference:
Apple Health exports workout history as **one file per `HKWorkoutActivityType`** (Running,
Cycling, Walking, TraditionalStrengthTraining, ...), so `import_workouts` takes a list of
paths, not one, and processes them together into a single result.

**The reason this needed care rather than a straight import**: Hevy writes every strength
workout it records into HealthKit too, so an export's `TraditionalStrengthTraining` rows
tagged `sourceName == 'Hevy'` are the *same training* already sitting in `workouts` via
`sync_workouts` — not a second source. Confirmed on a real export (2026-08-14): 105 such
rows, against 104 already in `workouts` covering the same date range. Those rows are
**dropped at import**, not stored and tagged — see
[ADR-0011](./docs/adr/0011-hevy-sourced-apple-health-rows-excluded-at-import.md) for why
exclusion beats leaving a table that could be double-counted by a query that forgets to
filter.

What's left after dropping Hevy rows is genuinely new data: `sourceName` normalizes to
either `Apple Watch` (native Workout-app sessions — including any pre-Hevy strength
history, which predates the Hevy sync entirely) or `Strava` (sessions Strava itself wrote
to HealthKit). The `Strava`-sourced rows are a **stopgap**: there's no live Strava sync
connected yet ([PLAN.md "Status"](#status)), so this is the only channel those runs come
through today. Once Strava connects, the same sessions will start arriving via
`activities` too, with richer data and no shared key back to `apple_workouts` — that
reconciliation is deliberately deferred until it's a real problem, not solved
speculatively now (ADR-0011 "Consequences").

An unrecognized `sourceName` (anything that isn't Hevy/Strava/a variant of "Apple Watch")
raises rather than importing under a guessed label — a new fitness app entering the
export later should be a deliberate decision, not something the importer glosses over.

## Access

- This Mac, reached from the phone via Claude Code's own remote access — no SSH, no
  inbound port, no VM to provision. See [ADR-0007](./docs/adr/0007-claude-code-remote-access-instead-of-a-vm.md).
- Reliability now depends on this Mac staying on and awake, not a VM built for the job —
  check sleep/power settings if phone access needs to hold up.
- Hevy API key in `~/health/.env` as `HEALTH_MCP_HEVY_API_KEY`, `chmod 600`. Never in the
  repo — `config.py` reads it from there, and nothing else should.
- Strava `client_id`/`client_secret` in `~/health/.env` as `HEALTH_MCP_STRAVA_CLIENT_ID` /
  `HEALTH_MCP_STRAVA_CLIENT_SECRET` — from registering an app at
  strava.com/settings/api (one-time, only doable by hand, see PLAN.md "Status"). The
  resulting access/refresh token pair, produced by `strava-auth`, is **not** in `.env` —
  it lives in `~/health/strava_auth.db`, `chmod 600` (ADR-0009).
- Nightly `sqlite3 .backup` to a second file; this database is not reconstructible from
  upstream, since the food log exists nowhere else. Not yet set up — the only backup is
  the one-off `~/health/health.db.bak-*` taken before the first sync. Should also cover
  `strava_auth.db` once set up, or a lost Strava connection means re-running `strava-auth`
  by hand rather than restoring (acceptable — see ADR-0009's consequences).

## Verification

1. ✅ **Unit — `day.py`.** The 04:00 rule across a DST changeover in both directions, and
   at 03:59 vs 04:01 local. This is the one piece of pure logic that would silently
   corrupt every rollup if wrong.
2. ✅ **Unit — portion maths.** 200 g of a 10 g-protein/100 g Product yields exactly 20 g.
3. ✅ **`query` is genuinely read-only.** `INSERT`, `UPDATE`, `DROP`, `PRAGMA`, and two
   statements separated by a semicolon must all be refused; a plain `SELECT` must work.
4. ✅ **Live smoke.** `GET /v1/user/info` returns 200 — proves the key and Pro status.
   A real sync populates `workouts` and `sync_state.cursor` advances; the next sync is a
   no-op.
5. ⬜ **Deletion handling.** Delete a workout in the Hevy app, run `sync`, confirm the row
   disappears rather than lingering. *Partly covered: the events feed replayed a real
   deletion during the first backfill, and full-sync reconciliation is unit-tested — but
   an end-to-end delete-then-sync hasn't been done against the app.*
6. ⬜ **End to end from the phone.** Open a Claude Code session in this repo via remote
   access, approve the `.mcp.json` prompt, `/mcp` lists the tools, then *"log 200 g of my
   cottage cheese, then show me this week's training volume next to my protein intake"*
   — exercises a write, the sync, and a cross-source join in one shot. *The query itself
   works against real data via the CLI; the phone path is untested.*
7. ✅ **Failure visibility.** Break the API key deliberately, run a sync, confirm
   `sync_state.last_error` is populated and readable via `query`. Confirmed also that a
   failed sync leaves the cursor untouched, and that a SQLite-level failure is recorded
   the same way rather than escaping as a traceback. Strava's equivalent (`sync` without
   ever having connected) is unit-tested the same way in `test_strava.py`.
8. ✅ **Unit — Strava token isolation.** `strava_auth` never appears in `sqlite_master`
   for the main `db_path` — the guarantee ADR-0009 is written to make structural.
9. ✅ **Unit — Strava token rotation.** A refresh within the expiry margin persists the
   *new* refresh token before returning, and a second call in the same window reuses the
   cached token rather than refreshing again (which would send an already-invalidated
   refresh token).
10. ⬜ **Strava live smoke.** Register the app, set `.env`, run `strava-auth` end to end
    (paste flow), then `sync-strava` against a real account, confirm `activities`
    populates and `sync_state` shows a `strava` row. Not yet done — needs the one-time app
    registration first (PLAN.md "Status").
11. ⬜ **Strava deletion handling.** Delete an activity on Strava, run `sync-strava
    --full`, confirm the row disappears. Reconciliation logic is unit-tested against a
    synthetic full fetch; an end-to-end delete-then-sync against the real app hasn't been
    done, same caveat as Hevy's equivalent item above.
12. ✅ **Unit — step dedup.** Two sources reporting different totals for the same day
    store the larger, not the sum; re-importing the same or an overlapping export doesn't
    duplicate or accumulate rows.
13. ✅ **Live — real export.** 2026-08-14: a genuine 180,601-row, ~9-year Apple Health CSV
    (five source names across phone renames and two Apple Watches) imported into
    `daily_steps` cleanly — see "Step import" for the resulting day/row counts.
14. ✅ **Unit — Hevy exclusion.** A `sourceName == 'Hevy'` row is dropped rather than
    stored, reported via `skipped_hevy`, and never reaches `apple_workouts`.
15. ✅ **Live — Hevy row count matches.** 2026-08-14: a real workout export's 105
    `Hevy`-sourced rows lined up against 104 already in `workouts` for the same date
    range — the evidence ADR-0011's exclusion decision is based on, not a hypothetical.
16. ✅ **Live — real multi-file import.** 2026-08-14: all six of a genuine export's
    per-type CSVs (Cycling, Elliptical, HIIT, Running, TraditionalStrengthTraining,
    Walking) imported in one `import_workouts` call — see "Apple workout import" for the
    resulting per-type, per-source counts.

## Future ideas

Not built, in rough order of likely value:

- **Promote repeated estimates.** If the same `estimated` one-off is logged three times,
  prompt to add it to the Catalog and correct it off a real label.
- **Albert Heijn product resolution** — verified findings preserved in
  [ADR-0004](./docs/adr/0004-no-albert-heijn-integration-in-v1.md) so the research isn't
  repeated. Purely a convenience over manual seeding.
- **NEVO** (RIVM's Dutch food composition database) for unbranded staples.
- **Open Food Facts by barcode** — thin Dutch coverage and flaky uptime when probed
  2026-08-11; would need caching, never a read-time dependency.
- **Automated Apple Health ingest.** Step counts are in (manual CSV import, see "Step
  import") — but that's a person dropping in a file, not a sync. Health Auto Export can
  also POST JSON automatically, which would need an ingest path, i.e. reintroducing an
  HTTP listener (the thing ADR-0005 avoided everywhere else). Worth it only if manual
  export becomes annoying enough in practice; other Apple Health metrics (heart rate,
  sleep) would follow the same CSV-import shape as steps if wanted before then.
- **Scheduled digest** — nightly sync plus a weekly summary pushed to you.
- **claude.ai web/mobile as a connector** — needs full OAuth 2.1 + dynamic client
  registration. A separate project, and the reason tool logic stays free of transport.
