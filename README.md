# health-mcp

A single agent-facing surface over one person's health data, so an AI can cross-reference
sources that usually sit in separate apps — training and nutrition today ("did intake
track with volume?"), with room to bring in sleep or other metrics later — in service of
actually optimizing toward that person's health goals, not just logging numbers.

It's an [MCP](https://modelcontextprotocol.io) server, speaking stdio, backed by one
SQLite file. Training data is synced in from external sources —
[Hevy](https://www.hevyapp.com/) for lifting, [Strava](https://www.strava.com/) for cardio
(runs, rides). Daily step counts and Apple Watch-native workout sessions are imported by
hand from Apple Health CSV exports — no API for those, just files dropped into chat. Food
is logged directly through the agent against a small hand-curated Catalog of Products.

## Tools

- `find_product(query?)` — search the Catalog by name/brand; list it all if `query` is
  omitted. Always call this before `log_food` against a Catalog item.
- `add_product(...)` — add a Product to the Catalog. Macros are per 100g; `source` is
  `verified` (off a package label) or `estimated`.
- `log_food(grams, product_id? | name + macros, at?)` — log that a quantity was eaten,
  either against a Catalog Product or as a one-off (always recorded as estimated).
- `delete_food_entry(id)` — remove a Food Log Entry.
- `sync_workouts(full?)` — pull new workouts, exercise templates, and body measurements
  from Hevy. Delta by default; `full=True` re-fetches everything and reconciles
  deletions.
- `sync_activities(full?)` — pull new cardio activities (runs, rides) from Strava. Delta
  by default, but only sees activities whose *start date* is after the last sync — an
  edited or back-dated activity needs `full=True` to be picked up (see PLAN.md "Strava
  sync"). Requires having run `strava-auth` once (below).
- `import_steps(path)` — import an Apple Health step-count CSV export from wherever it
  landed (e.g. attached to a chat message). No API, no cursor — always reprocesses the
  whole file and upserts by day, so a repeated or overlapping export is harmless. A day
  with samples from more than one source (phone + watch) is deduplicated by taking the
  larger source total, not summing them — see PLAN.md "Step import" and
  [ADR-0010](docs/adr/0010-daily-step-count-deduplicated-by-per-source-daily-max.md).
- `import_workouts(paths)` — import Apple Health workout CSV export(s) (one file per
  workout type — Running, Cycling, Walking, ... — so this is usually several paths at
  once). Rows sourced from Hevy are dropped, not stored: that training already exists via
  `sync_workouts`, and keeping both would double-count it — see PLAN.md "Apple workout
  import" and [ADR-0011](docs/adr/0011-hevy-sourced-apple-health-rows-excluded-at-import.md).
- `query(sql)` — read-only SQL (`SELECT`/`WITH` only) against the whole schema. There
  are deliberately no narrow read tools (`list_workouts`, `daily_nutrition`, etc.) — see
  [ADR-0006](docs/adr/0006-one-read-only-sql-tool-instead-of-narrow-read-tools.md).

The domain vocabulary these tools use (Product, Food Log Entry, Macros, Catalog,
Verified/Estimated, Day, Workout, Activity, Daily Steps, Apple Workout, Volume) is defined in
[CONTEXT.md](CONTEXT.md).

## Setup

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Configure via a `.env` file in the repo root (or `HEALTH_MCP_*` env vars):

```
HEALTH_MCP_DB_PATH=/path/to/health.db        # defaults to ~/health/health.db
HEALTH_MCP_HEVY_API_KEY=...                  # required for sync_workouts / `sync`
HEALTH_MCP_STRAVA_CLIENT_ID=...              # from strava.com/settings/api
HEALTH_MCP_STRAVA_CLIENT_SECRET=...          # required for sync_activities / `strava-auth`
```

Strava additionally needs a one-time interactive `strava-auth` (below) before
`sync_activities` / `sync-strava` will work — the resulting token pair is stored
separately, not in `.env` (see [ADR-0009](docs/adr/0009-strava-tokens-stored-outside-the-queryable-database.md)).

**Strava is built but not yet connected in this deployment** — as of 2026-06-01 Strava
requires an active paid subscription ($11.99/mo) to register and use an API app, which is
why this is paused rather than done. See PLAN.md "Strava setup (when ready)" for the exact
steps to pick it back up once that's worth it.

Migrations run automatically on every CLI invocation.

## Running

As an MCP server (what Claude Code / Claude Desktop launch):

```bash
uv run health-mcp serve
```

This repo is already registered as a project-scoped MCP server in `.mcp.json`, so any
Claude Code session opened here loads it automatically.

Other CLI commands:

```bash
uv run health-mcp sync                # pull new workouts from Hevy (delta)
uv run health-mcp sync --full         # re-fetch everything, reconcile deletions
uv run health-mcp normalize           # re-parse stored raw workout payloads, no network

uv run health-mcp strava-auth         # one-time: connect a Strava account (ADR-0008)
uv run health-mcp sync-strava         # pull new activities from Strava (delta)
uv run health-mcp sync-strava --full  # re-fetch everything, reconcile deletions

uv run health-mcp import-steps <path>          # import an Apple Health step-count CSV export
uv run health-mcp import-workouts <path> [...]  # import Apple Health workout CSV export(s)
```

## Tests

```bash
uv run pytest
```

## Roadmap

Hevy (lifting) syncs into the database today, and daily step counts plus Apple
Watch-native workout sessions import from Apple Health CSV exports on request. Strava
(cardio) is fully built alongside them but paused before its first real connection — see
"Setup" above and PLAN.md "Strava setup (when ready)". `query` can already answer
questions across Hevy, steps, and Apple workouts; Strava joins once connected. See
"Future ideas" in [PLAN.md](PLAN.md) for what's next after that — an Albert Heijn / NEVO
product lookup, a scheduled digest, and a couple of other candidates, in rough order of
likely value.

## Design notes

Key decisions and their rationale live in `docs/adr/`:

- [0001 — day runs 04:00–04:00 Europe/Amsterdam](docs/adr/0001-day-runs-0400-to-0400-amsterdam.md)
- [0002 — food log entries store macros, not references](docs/adr/0002-food-log-entries-store-macros-not-references.md)
- [0003 — own the data rather than compose external MCP servers](docs/adr/0003-own-the-data-rather-than-compose-external-mcp-servers.md)
- [0004 — no Albert Heijn integration in v1](docs/adr/0004-no-albert-heijn-integration-in-v1.md)
- [0005 — stdio over SSH instead of a public HTTPS endpoint](docs/adr/0005-stdio-over-ssh-instead-of-public-https.md)
- [0006 — one read-only SQL tool instead of narrow read tools](docs/adr/0006-one-read-only-sql-tool-instead-of-narrow-read-tools.md)
- [0007 — Claude Code remote access instead of a dedicated VM](docs/adr/0007-claude-code-remote-access-instead-of-a-vm.md)
- [0008 — Strava OAuth captured by manual paste, not a local listener](docs/adr/0008-strava-oauth-captured-by-manual-paste.md)
- [0009 — Strava tokens stored outside the queryable database](docs/adr/0009-strava-tokens-stored-outside-the-queryable-database.md)
- [0010 — daily step count deduplicated by per-source daily max](docs/adr/0010-daily-step-count-deduplicated-by-per-source-daily-max.md)
- [0011 — Hevy-sourced Apple Health rows excluded at import](docs/adr/0011-hevy-sourced-apple-health-rows-excluded-at-import.md)
