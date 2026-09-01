# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

FastAPI backend + Vue frontend (SPA), talking to a new HTTP API layer that wraps
health-mcp's existing `tools/*.py` functions against the same SQLite file the MCP server
already uses. Ships as its own small Docker service alongside the existing `health-mcp`
image, on the `homelab` Compose network — same pattern as the other services in
`~/docker`.

## Users

One person (Daniel), tracking his own training and eating history. He already logs food
by chatting with the health-mcp MCP server through an AI agent; that works but is slower
than it needs to be for something done multiple times a day. This UI is a faster, more
pleasant front door onto the same data for that one repeated action, not a multi-user
product.

## Product Purpose

A small web app that makes logging food fast and pleasant, backed by the same SQLite
database the health-mcp MCP server reads and writes. Success is: opening the page,
finding or entering a food, and logging it in a few taps — faster than typing a chat
message — while today's intake is visible at a glance right after logging.

v1 scope: food logging (search the Catalog, log grams against a Product or as a one-off,
edit/delete recent entries) plus a "today" snapshot (macro totals so far today, list of
today's Food Log Entries). Browsing/trends over workouts, activities, and steps stay in
the MCP chat surface for now — not built here yet.

## Positioning

Not a new food-tracking app or database of its own — a second front end onto data the
agent already owns and reasons over. A log made through this UI is immediately the same
row the agent sees when it cross-references intake against training volume; there's no
separate silo to sync or reconcile, unlike a general MacroFactor/MyFitnessPal-style app
that has no view into Hevy or Strava data at all.

## Operating Context

- Runs on Daniel's home server as a Docker Compose service, reverse-proxied by the
  existing Caddy instance, resolvable on the LAN as `<name>.verner.home` via AdGuard —
  same pattern as `kuma.verner.home`, `beszel.verner.home`, etc. LAN-only, no login.
- Shares the SQLite file at `data/health.db` with the existing `health-mcp` MCP server
  container (read-write, same volume mount pattern as `.mcp.json`'s `-v .../data:/app/data`).
  The MCP server itself stays stdio-only and untouched by this work — this is a new,
  separate HTTP service, not a change to the MCP transport (see ADR-0005: stdio over SSH
  instead of a public HTTPS endpoint — that decision was about the *agent* transport, not
  a general prohibition on ever adding an HTTP surface for a human).
- Day boundary is 04:00–04:00 Europe/Amsterdam, not midnight — "today" in the snapshot
  must use that rule (`health_mcp.day.day_of`), not a naive calendar date.
- The Catalog is small and hand-curated (not a general food database) — search/typeahead
  should assume tens to low hundreds of Products, not thousands.
- Every Product and Food Log Entry carries a `verified` (off a package label) or
  `estimated` (general knowledge) source — the UI must keep that distinction visible, not
  flatten it, per the domain vocabulary in CONTEXT.md.
- Logging a one-off (no Catalog match) requires per-100g macros (kcal/protein/carbs/fat)
  at log time and is always recorded as `estimated`.

## Capabilities and Constraints

- Reuses `health_mcp.tools.food` directly (`find_product`, `log_food`,
  `delete_food_entry`; `add_product`/`update_product` are in scope if useful for turning a
  one-off into a Catalog Product, though not the primary flow) rather than reimplementing
  logging logic — the new FastAPI service imports the same package the MCP server does.
- No HTTP API exists yet anywhere in this codebase (MCP is stdio-only) — this is new
  surface, built fresh, not an extension of an existing REST layer.
- No auth/login for v1 (LAN-only is the access control). Undecided/open: whether a future
  version ever needs auth if this stops being LAN-only.
- Single SQLite file, single writer assumption already relied on elsewhere in this repo
  (each tool call opens/closes its own connection) — the new service should follow the
  same short-lived-connection pattern rather than holding a long-lived connection open.

## Brand Commitments

None. No existing name, logo, or visual identity beyond the `health-mcp` project name
itself; nothing here is binding.

## Evidence on Hand

No mockups or existing UI to work from — this is the first visual surface for this data.
The real evidence is the SQLite schema and domain vocabulary already documented in
`CONTEXT.md` and `src/health_mcp/migrations/001_init.sql`; future work should treat those,
not invented sample data, as ground truth for what a Product/Food Log Entry actually
contains.

## Product Principles

- Fast entry beats completeness — every added field or step in the logging flow must earn
  its place against "how much slower does this make logging a food I eat often."
- One source of truth — this UI and the MCP agent must never disagree about a Food Log
  Entry; write through the same tool functions and schema, never a parallel table or cache.
- Verified vs. estimated stays visible — a UI that quietly treats both the same
  undermines the one thing that makes rollups trustworthy.
- Built for one specific person's actual Catalog and habits, not a general audience —
  optimize for Daniel's real foods and routine, not hypothetical other users or diets.

## Accessibility & Inclusion

No specific requirement established beyond ordinary good practice (keyboard operable,
legible contrast, works on a phone browser since logging often happens away from a
desktop).
