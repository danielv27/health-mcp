# Handoff — health-mcp logging UI

Session was interrupted mid-flow while designing a new web UI on top of health-mcp,
using the `impeccable` skill (`/impeccable init` → new-work). This captures where it
left off so a future session can resume without re-deriving the decisions below.

## What this UI is

A new, separate web service (not a change to the existing stdio MCP server) that gives
Daniel a fast, pleasant way to log food by hand instead of chatting with the agent every
time. It shares the same SQLite file (`data/health.db`) the MCP server already
reads/writes, by importing `health_mcp.tools.food` directly rather than reimplementing
logging logic. Full rationale, users, positioning, and constraints are written up in
[`PRODUCT.md`](PRODUCT.md) (already committed to disk, complete) — read that first.

## Decisions already locked (via AskUserQuestion, confirmed by Daniel)

- **Scope (v1):** Food logging + a "today" snapshot (macro totals, recent entries).
  Browsing/trends over workouts, activities, and steps stay in the MCP chat surface for
  now, not built here.
- **Stack:** FastAPI backend + Vue frontend (SPA). Backend imports
  `health_mcp.tools.food` functions directly. New Docker service alongside the existing
  `health-mcp` image, on the `homelab` Compose network.
- **Access:** LAN-only, no login — same pattern as `kuma.verner.home`,
  `beszel.verner.home`, etc. via the existing Caddy reverse proxy.
- **Targets:** the snapshot shows **progress against daily targets** (kcal/protein/carbs/
  fat), not just raw totals. **No `targets` table exists in the schema yet** — this is new
  scope, not something to discover in the DB. Needs a small addition (e.g. a migration
  adding a single-row `targets` table, or a `daily_targets` table if it should ever vary
  by day) plus a minimal way to set/edit it (a settings view is fine for v1; it doesn't
  need to be fancy).
- **Device priority:** phone-first. Design and build the mobile layout as primary, not as
  a breakpoint afterthought.
- **Quick-log pattern:** recent/frequent foods surfaced up front on open (including
  "log this again" for something already logged today, e.g. a second helping) — search is
  the fallback path, not the default one.

## Where the design process stopped

Following `impeccable`'s `new-work.md` flow for a greenfield visual world (no DESIGN.md
exists yet — this is the first visual surface for this data):

1. **PRODUCT.md** — done, written to repo root.
2. **Ask round for Operate mode** — done (the four bullets above under "Targets",
   "Device priority", "Quick-log pattern").
3. **Direction candidates** — drafted seven concrete visual systems from Daniel's actual
   world (serious lifter who home-labs his own tools), ordered by resonance:
   1. **Instrument Panel** — cockpit/gauge world: dark panel, backlit dial-style macro
      rings, toggle-switch quick-log buttons, monospace readouts.
   2. **Plate Board** — gym PR-board world: bold black/white, chalk-stencil numerals,
      plate-loading metaphor for macro progress, quick-log as a "rack" of recent foods.
   3. **Kitchen Scale** — digital scale LED-readout world: seven-segment digits,
      tare/zero button language, nutrition-facts-panel grid for the entry list.
   4. **Server Rack / Homelab** — matches Daniel's *other* homelab dashboards
      (uptime-kuma/beszel/Grafana-style): dark terminal ground, sparkline macro bars,
      monospace, status-pill badges — makes this feel like one more service in the stack
      rather than a separate app.
   5. **Lab Bench** — pharmacy/reagent-label world: precise grid labels, small-caps type,
      clinical white with an instrument-blue accent.
   6. **Logbook** — paper training-log world: graph-paper ground, tick marks, pencil-grey
      ink (anti-reference/contrast direction — legitimate but less likely default).
   7. **Timer Wall** — gym interval-timer world: huge countdown-style digits, minimal
      chrome, built for a glance while busy.

4. **Ran the required roll**: `node .claude/skills/impeccable/scripts/concept-seed.mjs
   --scope direction --mode operate`. Seed key **`c4de87c6`** (mode: operate). Reproduce
   the exact same roll against the same candidate list with:
   ```
   node .claude/skills/impeccable/scripts/concept-seed.mjs --scope direction --mode operate --from c4de87c6 --candidate-count 7
   ```
   **Assigned index: 4 → "Server Rack / Homelab."** That's the direction to build unless
   a fused challenger beats it on both audience identification and product clarity (next
   step, not yet done).

   The script also dealt six catalog challengers to weigh against it: a nixie-tube lab
   counter, an interactive variable-font specimen, a midnight transit-diagram map, an
   Emigre bitmap type specimen, a theatrical dawn cyclorama, and a gravity-rain garden.
   None of these were fused/judged yet — the run was interrupted right after the
   challenger list printed, before the fuse-and-weigh step (new-work.md step 3.4).

## DECISION LOCKED (2026-09-01)

Fuse-and-weigh (`new-work.md` step 3.4) completed against the six dealt challengers
(nixie-tube lab counter, interactive variable-font specimen, midnight transit-diagram map,
Emigre bitmap type specimen, theatrical dawn cyclorama, gravity-rain garden). Verdicts:
nixie-tube, transit map, and rain-garden were **competitive** (each held product clarity
on the macro-vs-target view but lost audience identification — none are grounded in
Daniel's documented world the way Server Rack/Homelab is); variable-font, Emigre bitmap,
and theatrical cyclorama were **declined**, each donating one raise into the assigned
direction (rolling digit animation on log; a distinct display-digit face for headline
macro numbers; a spotlight accent on the macro furthest off-target).

Presented via `serve-question.mjs` (no browser in this environment → routed to the
structured question tool per new-work.md step 3.5's exit-2 fallback), including the
assigned roll, Impeccable's Pick, the three competitive challengers, and the standing-exit
canon card as options.

**Daniel chose "Instrument Panel" — not the dice-assigned Server Rack / Homelab.**
Instrument Panel was Impeccable's Pick (topped the original resonance ranking pre-roll):
cockpit/gauge world — dark panel, backlit dial-style macro progress rings, toggle-switch
quick-log buttons, monospace readouts inside gauge bezels. This is the locked direction to
build. The three raises drafted for Server Rack (digit-roll animation, display-digit face,
off-target spotlight accent) are worth re-evaluating for reuse inside Instrument Panel's
own grammar (e.g. a needle-snap or gauge-sweep animation instead of a digit roll) but are
not binding — they were authored for the other direction.

## BUILD COMPLETE (2026-09-01)

Everything through new-work.md steps 4–7 is done:

- Color strategy: Restrained (near-black neutrals + one amber accent), IBM Plex Mono
  (numerals) / IBM Plex Sans (labels/body) — avoids the warm-cream/serif and
  near-black/neon AI-cliché defaults per new-work.md's calibration section.
- `targets` table + migration: `src/health_mcp/migrations/005_targets.sql`,
  `src/health_mcp/tools/targets.py` (`get_targets`/`set_targets`), single row, no
  history. Tests: `tests/test_targets.py`, plus `tests/test_db.py` updated for
  schema version 5.
- Backend: `src/health_mcp/web/app.py`, a FastAPI service importing
  `health_mcp.tools.food`/`targets` directly (short-lived connections per request,
  matching the MCP tools' pattern). Endpoints: `/api/today`, `/api/products`,
  `/api/products/recent` (frequency + last-grams for one-tap re-log),
  `/api/log` (POST/DELETE), `/api/targets` (GET/PUT). Tests: `tests/test_web_app.py`.
  **Found and fixed a real bug during testing**: sqlite3 connections need
  `check_same_thread=False` (`src/health_mcp/db.py`) because FastAPI's sync
  dependency-with-`yield` can open and close a connection on different threadpool
  workers — intermittent `SQLite objects created in a thread...` 500s otherwise.
- Frontend: `web-frontend/` (Vue 3 + Vite SPA) — "Instrument Panel" world: dial-ring
  gauges (`DialGauge.vue`), toggle-switch quick-log rack (`FoodToggle.vue`), bottom-sheet
  log/settings drawers, all in `App.vue`. Direction contract lives as an HTML comment,
  first child of `<body>`, in `web-frontend/index.html`.
- Docker: `Dockerfile.web` (multi-stage: Node build → Python/uv runtime serving the
  built SPA as static files via the FastAPI app itself, one container). Verified
  end-to-end with a throwaway `docker run` (migrations run at FastAPI startup, full
  log/delete/edit/targets round-trip over curl).
- Inspected mobile (390×844, primary) and desktop (1280×900) via a one-off
  Playwright container (no browser automation tool was available in this
  environment) — screenshots in `.impeccable/review/`. Found and fixed a real
  layout bug: the log-sheet's macro-grid inputs overflowed the viewport on mobile
  (classic CSS Grid `1fr` min-content overflow) — fixed with `minmax(0, 1fr)`.
- Finish review: ran in-thread (no `impeccable-finish-reviewer` agent type available
  in this harness — disclosed substitution, per new-work.md's degraded path). Found
  and fixed two craft-floor violations: Unicode glyph icons (⚙/✕) replaced with
  drawn SVG icons; the "brushed-metal" bezel was a flat gradient, now carries an
  actual brushed hatch texture. Also added `:focus-visible` theming (was falling
  back to the browser default ring). **Known, disclosed, not-yet-fixed gaps** from
  that review: no hover states for desktop/mouse use (this is a phone-first
  surface, so lower priority); no visible error state if a log/target request
  fails; the true-empty state (no entries, no recent foods yet) wasn't
  screenshot-verified, only inferred from the template's `v-if`s.
- DESIGN.md + `.impeccable/design.json` written (also in-thread — no
  `impeccable-documenter` agent type available, disclosed).
- `docker-compose.yml` / `Caddyfile` in `~/docker` updated (service `foodlog`,
  host `foodlog.verner.home`, sharing `health-mcp`'s `data/` bind mount with the
  MCP server container) and validated with `docker compose config` — **not yet
  applied** (no `docker compose up`/`restart caddy` run against the live stack;
  that's a deliberate stop before touching shared infrastructure).

## LIVE (2026-09-01)

Applied to the real stack: `docker compose up -d foodlog && docker compose restart
caddy` in `~/docker`. Verified through Caddy (`Host: foodlog.verner.home`) against
the real `data/health.db` — returned Daniel's actual recent entries. Reachable at
`http://foodlog.verner.home` on the LAN.

`targets` is unset (`null`) — the four gauges will read 0% until targets are set
once via the settings gear on the page itself.

## Next steps (optional, not blocking)

Hover states, an explicit empty-state screenshot check — see "Known, disclosed" gaps
above. (The error-toast gap is now partially closed — see below.)

## CRITIQUE + REBUILD (2026-09-01)

Daniel reported the Quick Log toggle logged food he hadn't eaten with no way to
revert, and that the data model doesn't match reality — food is never logged
standalone, always as part of a meal. Ran `/impeccable critique` (dual-agent: design
review + detector/browser evidence), scored **19/40 (Poor)**, persisted at
`.impeccable/critique/2026-08-31T23-20-36Z__web-frontend-src-app-vue.md`. Root cause
traced and confirmed live: `FoodToggle.vue`'s `flip()` fired a real `POST /api/log` on
a single tap with zero confirmation, then auto-reverted its lever to "off" after
700ms — erasing the only evidence a log had occurred.

Daniel chose "everything in the report" (P0 + all three P1s) plus a rough sketch
(not build) of where photo-based product ID would fit. Ran the full recommended
pipeline (`shape` → `harden` → `audit` → `polish`):

- **shape**: confirmed named meal types (breakfast/lunch/dinner/snack, inferred from
  time of day, editable), a staging-cart build flow, and that Quick Log stops writing
  to the DB entirely — a tap now only stages a food into the pending meal.
- **harden — schema/backend**: `006_meals.sql` (`meals` table, `food_log.meal_id`),
  `tools/meals.py` (`log_meal` — one meal + all its entries in a single atomic
  commit, rolls back completely on any bad item; `delete_meal`; `infer_meal_type`).
  `tools/food.py`'s `log_food` gained `meal_id`/`commit` params;
  `delete_food_entry` deliberately does **not** cascade-delete an emptied meal (that
  broke the edit flow's delete-then-relog on the meal's last item via a foreign-key
  violation — `/api/today` just skips meals with zero entries instead).
  `web/app.py`: `POST/DELETE /api/meals`, `GET /api/meals/suggested-type`,
  `/api/today` now returns `meals: [...]` (grouped, with subtotals) and
  `ungrouped: [...]` instead of a flat `entries` list.
- **harden — frontend**: `FoodToggle.vue` rewired to reflect real, persistent cart
  membership (on iff staged) instead of firing-and-reverting regardless of outcome.
  New `Toast.vue` (undo pattern) wired to every commit and every delete — the P1
  "no confirmation/undo anywhere" fix. New cart-tray UI in `App.vue` (meal-type
  chips, staged items, one "Log meal" commit button) and the Today list now renders
  grouped under meal headers with per-meal subtotals, plus an "Other" bucket for
  pre-existing ungrouped entries. Also fixed the dead `searching` loading state
  (P3).
- **audit**: browser-detector re-run confirmed the fix — findings went from 48 to 12,
  all of the low-contrast and undersized-text findings gone. Fixed:
  `--text-dim` (`#8a8d94` → `#aeb2b9`, was 3.1:1 against the bezel, now clears
  4.5:1 everywhere) and every functional label/badge raised to a 0.7rem (11.2px)
  floor. Remaining 11 findings are the same likely-false-positive `text-occlusion`
  flag on the dial numerals already noted in the original critique (DOM-order vs.
  actual paint-order artifact — screenshots confirm the numbers render legibly); one
  new minor `flat-type-hierarchy` note (the size floor compressed the type scale's
  range) is polish-level, not accessibility-blocking.
- **polish**: full interactive Playwright pass confirmed no-write-on-tap, persistent
  toggle state, cart commit, undo-restores-meal, and delete-undo all work with zero
  console errors; DESIGN.md and `.impeccable/design.json` updated with two new named
  rules (**The Honest State Rule**, **The No Silent Write Rule**) and four new
  documented components (Toggle Switch redefined, Meal Cart Tray, Meal Header,
  Toast/Undo).

All 170 tests pass (`tests/test_meals.py` added — atomicity, cascade-on-empty-meal
behavior, meal-type inference). Deployed: `docker compose build foodlog && docker
compose up -d foodlog` in `~/docker` — verified live against the real `data/health.db`
through Caddy, no data loss, migration to schema version 6 applied cleanly on
existing production data.

**Not done, deliberately deferred**: photo-based product identification. Daniel asked
to "rough out the plan" rather than build it. Sketch: it would live as a secondary
entry point next to the search field (a camera icon opening a capture flow that
either matches an existing Catalog product or pre-fills the one-off macro form) —
not built, no code exists for it yet.

## Things NOT yet decided / built

- No migration, backend, or frontend code exists yet — nothing under `src/` or a new
  service directory has been touched. This session only produced `PRODUCT.md` and this
  handoff.
- Exact shape of the `targets` table/settings UI (single row vs. dated history) is
  unresolved — pick the simplest thing that satisfies "progress against a daily target"
  unless Daniel says he wants targets to change over time.
- Docker Compose service name, hostname (`<name>.verner.home`), and Caddy block wording
  aren't chosen yet — follow the existing pattern in `~/docker/docker-compose.yml` and
  `~/docker/caddy/Caddyfile` (see `/home/daniel/CLAUDE.md` for the stack index).
