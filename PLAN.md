# Personal Health MCP Server

## Context

A single MCP server that lets a Claude session answer questions spanning training and
eating — "what did I lift this week", "how much protein yesterday", "did intake track
with volume" — without copying data between apps. Training data comes from Hevy. Eating
data is logged by hand against a small, hand-curated Catalog of the foods actually eaten.

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
[Claude Code remote access instead of a VM](./docs/adr/0007-claude-code-remote-access-instead-of-a-vm.md).

**Hevy Pro is not yet active** and will be bought once the integration is built. Two
consequences:

- **Build food-first.** The food half needs no credentials and is fully testable today.
- **The Hevy client is written blind**, against docs rather than observed responses. So
  `sync` persists the raw JSON payload first and normalizes into `workout_exercises` /
  `workout_sets` as a **separate, re-runnable pass**. A shape surprise on subscription day
  is then a re-parse of stored data, not a re-sync and not a migration.

## Status

Design is settled — the decisions below came out of a grilling session and are recorded
in `docs/adr/`. Implementation has barely started.

| | |
|---|---|
| Done | `pyproject.toml`; `day.py`; `config.py`; `migrations/001_init.sql` (all 9 tables); `db.py` (rw/ro + migration runner); `tools/food.py`; `tools/query.py`; `server.py` (5 tools registered: `add_product`, `find_product`, `log_food`, `delete_food_entry`, `query`); `cli.py` (`serve` works, `sync` stubbed); `.mcp.json` (project-scoped, see ADR-0007) — 50 tests passing, plus a manual `call_tool` smoke test end to end (add → find → log → query → a rejected `DROP TABLE`) |
| Next | Open a Claude Code session in this repo (from the phone, via remote access) and approve the `.mcp.json` prompt — first real live test |
| Then | `hevy.py` (client + incremental sync, written blind against docs — see PLAN.md "Hevy sync"), register `sync_workouts` in `server.py` |
| Not started | Hevy sync, `normalize`, backups, `launchd` for `sync` |

## Architecture

```
phone ──Claude Code remote access──> this Mac ──> Claude Code ──stdio──> health-mcp
                                                                              │
                                                                       SQLite (~/health/health.db)
                                                                              │
                                                          health-mcp sync ────> Hevy API (api-key)
```

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
    cli.py                  # `serve` and `sync` subcommands
    config.py               # env-var settings
    day.py                  # the 04:00 Amsterdam day rule — one function, unit-tested
    db.py                   # connections (rw + ro), migration runner
    migrations/001_init.sql
    hevy.py                 # Hevy client + incremental sync
    tools/
      food.py               # add_product, log_food, delete_food_entry, find_product
      training.py           # sync_workouts
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
| `sync_state` | `source` PK, `cursor`, `last_run_at`, `last_status`, `last_error` |

`food_log` stores absolute totals rather than a reference, so history can't be rewritten
by a later edit ([ADR-0002](./docs/adr/0002-food-log-entries-store-macros-not-references.md)).
`sync_state` carries `last_status`/`last_error` specifically so a cron sync that has been
failing for a week is one `query` away from being visible.

Index `food_log(date)`, `workouts(date)`, `workouts(start_time)`,
`workout_exercises(workout_id)`, `workout_sets(workout_exercise_id)`.

## Tools

Six. Writes are narrow and explicit; reads are one tool.

**Writes**
- `add_product(name, kcal_100g, protein_100g, carbs_100g, fat_100g, brand=None, source="verified", ...)`
  — adds to the Catalog.
- `log_food(grams, product_id=None, name=None, macros=None, entered_as=None, at=None)`
  — either a Catalog Product *or* a one-off with model-supplied Macros marked `estimated`.
  Computes `date` via the 04:00 rule and writes absolute totals.
- `delete_food_entry(id)`
- `sync_workouts(full=False)` — delta by default.

**Reads**
- `find_product(query=None)` — returns the Catalog, filtered. The resolution step before
  any `log_food` against a Product.
- `query(sql)` — read-only, schema in the description.

Descriptions must be specific about *when* to call each; that drives tool selection more
than anything else.

## Hevy sync

Auth is one `api-key: <uuid>` header on `https://api.hevyapp.com/v1`.

| Endpoint | Use |
|---|---|
| `GET /v1/workouts?page&pageSize` | initial backfill |
| `GET /v1/workouts/events?since` | incremental — updates **and** deletions |
| `GET /v1/exercise_templates` | `exercise_template_id` → muscle group |
| `GET /v1/body_measurements` | weight / body-fat series |

`/workouts/events` makes sync cheap: keep the cursor in `sync_state` and fetch only
deltas. It emits deletion events — process them, or deleted workouts linger forever.
`pageSize` caps differ per endpoint (10 or 100); read the cap from the response rather
than hardcoding it. [`chrisdoc/hevy-mcp`](https://github.com/chrisdoc/hevy-mcp) is worth
reading for endpoint quirks, though we're not depending on it.

Sync is two phases against the same data, and they are separable on purpose:

1. **Fetch** — write each workout's raw JSON into `workouts.raw`, advance the cursor.
2. **Normalize** — read `workouts.raw`, populate `workout_exercises` / `workout_sets`.
   Idempotent and re-runnable over the whole table (`health-mcp normalize`).

Written without live API access, so phase 2 is where the guesses live. Keeping it
re-runnable means a wrong guess costs a re-parse, not a re-sync.

Cron: `0 */6 * * * health-mcp sync >> ~/health/sync.log 2>&1`.

## Access

- This Mac, reached from the phone via Claude Code's own remote access — no SSH, no
  inbound port, no VM to provision. See [ADR-0007](./docs/adr/0007-claude-code-remote-access-instead-of-a-vm.md).
- Reliability now depends on this Mac staying on and awake, not a VM built for the job —
  check sleep/power settings if phone access needs to hold up.
- Hevy API key in `~/health/.env`, `chmod 600`. Never in the repo.
- Nightly `sqlite3 .backup` to a second file; this database is not reconstructible from
  upstream, since the food log exists nowhere else. Not yet set up.

## Verification

1. **Unit — `day.py`.** The 04:00 rule across a DST changeover in both directions, and at
   03:59 vs 04:01 local. This is the one piece of pure logic that would silently corrupt
   every rollup if wrong.
2. **Unit — portion maths.** 200 g of a 10 g-protein/100 g Product yields exactly 20 g.
3. **`query` is genuinely read-only.** `INSERT`, `UPDATE`, `DROP`, `PRAGMA`, and two
   statements separated by a semicolon must all be refused; a plain `SELECT` must work.
4. **Live smoke.** `GET /v1/user/info` returns 200 — proves the key and Pro status. Then
   a real sync populates `workouts` and `sync_state.cursor` advances.
5. **Deletion handling.** Delete a workout in the Hevy app, run `sync`, confirm the row
   disappears rather than lingering.
6. **End to end from the phone.** Open a Claude Code session in this repo via remote
   access, approve the `.mcp.json` prompt, `/mcp` lists the tools, then *"log 200 g of my
   cottage cheese, then show me this week's training volume next to my protein intake"*
   — exercises a write, the sync, and a cross-source join in one shot.
7. **Failure visibility.** Break the API key deliberately, run a sync, confirm
   `sync_state.last_error` is populated and readable via `query`.

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
- **Strava** — official OAuth2. Refresh-token rotation invalidates the previous token on
  every refresh; persist the new one or get locked out.
- **Apple Health** — Health Auto Export POSTs JSON; needs an ingest path, which means
  reintroducing an HTTP listener.
- **Scheduled digest** — nightly sync plus a weekly summary pushed to you.
- **claude.ai web/mobile as a connector** — needs full OAuth 2.1 + dynamic client
  registration. A separate project, and the reason tool logic stays free of transport.
