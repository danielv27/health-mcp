# health-mcp

A single agent-facing surface over one person's health data, so an AI can cross-reference
sources that usually sit in separate apps — training and nutrition today ("did intake
track with volume?"), with room to bring in sleep or other metrics later — in service of
actually optimizing toward that person's health goals, not just logging numbers.

It's an [MCP](https://modelcontextprotocol.io) server, speaking stdio, backed by one
SQLite file. Training data is synced in from external sources — currently
[Hevy](https://www.hevyapp.com/) for lifting, with [Strava](https://www.strava.com/) for
cardio planned next. Food is logged directly through the agent against a small
hand-curated Catalog of Products.

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
- `query(sql)` — read-only SQL (`SELECT`/`WITH` only) against the whole schema. There
  are deliberately no narrow read tools (`list_workouts`, `daily_nutrition`, etc.) — see
  [ADR-0006](docs/adr/0006-one-read-only-sql-tool-instead-of-narrow-read-tools.md).

The domain vocabulary these tools use (Product, Food Log Entry, Macros, Catalog,
Verified/Estimated, Day, Workout, Volume) is defined in [CONTEXT.md](CONTEXT.md).

## Setup

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Configure via a `.env` file in the repo root (or `HEALTH_MCP_*` env vars):

```
HEALTH_MCP_DB_PATH=/path/to/health.db   # defaults to ~/health/health.db
HEALTH_MCP_HEVY_API_KEY=...             # required for sync_workouts / `sync`
```

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
uv run health-mcp sync           # pull new workouts from Hevy (delta)
uv run health-mcp sync --full    # re-fetch everything, reconcile deletions
uv run health-mcp normalize      # re-parse stored raw workout payloads, no network
```

## Tests

```bash
uv run pytest
```

## Roadmap

Next up is a Strava sync for cardio (runs, rides) alongside the existing Hevy sync for
lifting, so `query` can answer questions across both. See "Future ideas" in
[PLAN.md](PLAN.md) for this and other planned work.

## Design notes

Key decisions and their rationale live in `docs/adr/`:

- [0001 — day runs 04:00–04:00 Europe/Amsterdam](docs/adr/0001-day-runs-0400-to-0400-amsterdam.md)
- [0002 — food log entries store macros, not references](docs/adr/0002-food-log-entries-store-macros-not-references.md)
- [0003 — own the data rather than compose external MCP servers](docs/adr/0003-own-the-data-rather-than-compose-external-mcp-servers.md)
- [0004 — no Albert Heijn integration in v1](docs/adr/0004-no-albert-heijn-integration-in-v1.md)
- [0005 — stdio over SSH instead of a public HTTPS endpoint](docs/adr/0005-stdio-over-ssh-instead-of-public-https.md)
- [0006 — one read-only SQL tool instead of narrow read tools](docs/adr/0006-one-read-only-sql-tool-instead-of-narrow-read-tools.md)
- [0007 — Claude Code remote access instead of a dedicated VM](docs/adr/0007-claude-code-remote-access-instead-of-a-vm.md)
