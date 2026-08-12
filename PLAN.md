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

**Hevy Pro is active** as of 2026-08-12, and the client was rewritten against observed
responses rather than docs. The two-phase shape stayed anyway: `sync` persists the raw
JSON payload first and normalizes into `workout_exercises` / `workout_sets` as a
**separate, re-runnable pass**, so a parsing mistake costs a re-parse of stored data
rather than a re-sync. That bet paid for itself immediately — see the quirks table below.

## Status

Design is settled — the decisions below came out of a grilling session and are recorded
in `docs/adr/`. Both halves are now built and verified against live data.

| | |
|---|---|
| Done | `pyproject.toml`; `day.py`; `config.py`; `migrations/001_init.sql` (all 9 tables); `db.py` (rw/ro + migration runner); `tools/food.py`; `tools/query.py`; `hevy.py` (client + delta/full sync + `normalize`); `tools/training.py`; `server.py` (all 6 tools registered); `cli.py` (`serve`, `sync [--full]`, `normalize`); `.mcp.json` (project-scoped, see ADR-0007) — **77 tests passing** |
| Verified live | 2026-08-12: 102 workouts / 583 exercises / 1,961 sets / 451 templates / 11 measurements, in ~3 s. Full and delta syncs agree, `PRAGMA foreign_key_check` clean, cross-source volume-vs-protein join works, a deliberately broken key lands in `sync_state.last_error` and leaves the cursor untouched |
| Next | Open a Claude Code session in this repo (from the phone, via remote access) and approve the `.mcp.json` prompt — first real live test through the agent rather than the CLI |
| Not started | Nightly backup, `launchd` job for `sync` |

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

## Access

- This Mac, reached from the phone via Claude Code's own remote access — no SSH, no
  inbound port, no VM to provision. See [ADR-0007](./docs/adr/0007-claude-code-remote-access-instead-of-a-vm.md).
- Reliability now depends on this Mac staying on and awake, not a VM built for the job —
  check sleep/power settings if phone access needs to hold up.
- Hevy API key in `~/health/.env` as `HEALTH_MCP_HEVY_API_KEY`, `chmod 600`. Never in the
  repo — `config.py` reads it from there, and nothing else should.
- Nightly `sqlite3 .backup` to a second file; this database is not reconstructible from
  upstream, since the food log exists nowhere else. Not yet set up — the only backup is
  the one-off `~/health/health.db.bak-*` taken before the first sync.

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
   the same way rather than escaping as a traceback.

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
