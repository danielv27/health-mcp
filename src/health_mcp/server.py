"""MCP server: registers the food and training tools over stdio.

Each tool opens its own connection per call rather than holding one open across the
process lifetime.
"""

from datetime import datetime

from mcp.server import MCPServer

from health_mcp import apple_workouts, steps
from health_mcp.db import ro, rw
from health_mcp.tools import apple_workouts as apple_workouts_tools
from health_mcp.tools import food as food_tools
from health_mcp.tools import query as query_tool
from health_mcp.tools import steps as steps_tools
from health_mcp.tools import training as training_tools
from health_mcp.tools.food import Macros

mcp = MCPServer(
    "health-mcp",
    instructions=(
        "Personal training and eating history for one person. Call find_product before "
        "log_food against a Catalog item — product_id is never guessed. For a food with "
        "no Catalog entry, call log_food with name + macros (per 100g); it is recorded "
        "as estimated. Use query for any read not covered by find_product — the schema "
        "is in its description."
    ),
)


@mcp.tool()
def add_product(
    name: str,
    kcal_100g: float,
    protein_100g: float,
    carbs_100g: float,
    fat_100g: float,
    brand: str | None = None,
    source: str = "verified",
    fibre_100g: float | None = None,
    sugar_100g: float | None = None,
    sat_fat_100g: float | None = None,
    salt_100g: float | None = None,
    note: str | None = None,
) -> int:
    """Add a Product to the Catalog. Macros are per 100g. `source` is "verified"
    (transcribed from a package label) or "estimated" (general knowledge) — verified is
    the standard for anything worth trusting. Returns the new product id."""
    conn = rw()
    try:
        return food_tools.add_product(
            conn, name, kcal_100g, protein_100g, carbs_100g, fat_100g,
            brand=brand, source=source, fibre_100g=fibre_100g, sugar_100g=sugar_100g,
            sat_fat_100g=sat_fat_100g, salt_100g=salt_100g, note=note,
        )
    finally:
        conn.close()


@mcp.tool()
def find_product(query: str | None = None) -> list[dict]:
    """Search the Catalog by name or brand (substring match). Omit `query` to list the
    whole Catalog. Call this before log_food against a Catalog Product — the result's
    `id` is the `product_id` log_food expects."""
    conn = ro()
    try:
        return [dict(row) for row in food_tools.find_product(conn, query)]
    finally:
        conn.close()


@mcp.tool()
def log_food(
    grams: float,
    product_id: int | None = None,
    name: str | None = None,
    macros: Macros | None = None,
    entered_as: str | None = None,
    at: datetime | None = None,
) -> int:
    """Log that `grams` of a food were eaten. Pass exactly one of: `product_id` (from
    find_product, for a Catalog item) or `name` + `macros` (per 100g, model-supplied,
    for a one-off — always recorded as estimated). `at` defaults to now; the stored
    `date` is derived via the 04:00 Europe/Amsterdam day rule, not a calendar date.
    Returns the new food_log id."""
    conn = rw()
    try:
        return food_tools.log_food(
            conn, grams, product_id=product_id, name=name, macros=macros,
            entered_as=entered_as, at=at,
        )
    finally:
        conn.close()


@mcp.tool()
def delete_food_entry(id: int) -> None:
    """Delete a Food Log Entry by id."""
    conn = rw()
    try:
        food_tools.delete_food_entry(conn, id)
    finally:
        conn.close()


@mcp.tool()
def sync_workouts(full: bool = False) -> dict:
    """Pull new training data from Hevy into the database. Call this before answering a
    question about recent training — a workout finished after the last sync isn't in the
    database until you do. Delta by default and cheap to call. `full=True` re-fetches
    everything and reconciles deletions; use it only if the data looks wrong, not
    routinely. Also refreshes exercise templates and body measurements."""
    conn = rw()
    try:
        return training_tools.sync_workouts(conn, full=full)
    finally:
        conn.close()


@mcp.tool()
def sync_activities(full: bool = False) -> dict:
    """Pull new cardio activities (runs, rides, etc.) from Strava into the database. Call
    this before answering a question about recent cardio. Delta by default: it only sees
    activities that *started* after the last sync, so an activity edited afterward, or
    uploaded later with a back-dated start time, won't show up until `full=True` re-fetches
    everything and reconciles deletions — use `full` if the data looks wrong, not
    routinely. Fails with a clear error if Strava hasn't been connected yet (run
    `health-mcp strava-auth` first, outside the agent)."""
    conn = rw()
    try:
        return training_tools.sync_activities(conn, full=full)
    finally:
        conn.close()


@mcp.tool()
def import_steps(path: str) -> dict:
    """Import an Apple Health step-count CSV export (e.g. from the "Simple Health Export
    CSV" app) into the database. Call this when the user shares a fresh export in chat —
    pass the local file path it landed at. Always reprocesses the whole file and upserts
    by day, so re-importing an overlapping or repeated export is harmless; there's no
    delta/cursor concept here, unlike sync_workouts/sync_activities. A day with samples
    from multiple sources (phone and watch, say) is deduplicated by taking the larger of
    each source's daily total, not summing across sources — see docs/adr/0010."""
    conn = rw()
    try:
        return steps_tools.import_steps(conn, path)
    except steps.StepsError as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        conn.close()


@mcp.tool()
def import_workouts(paths: list[str]) -> dict:
    """Import Apple Health workout CSV export(s) — one file per HealthKit workout type
    (Running, Cycling, Walking, ...), so this usually means several paths at once. Call
    this when the user shares fresh exports in chat — pass the local file paths they
    landed at. Rows sourced from Hevy are dropped, not stored: Hevy already syncs directly
    via sync_workouts, and keeping both would double-count that training. Rows sourced
    from Strava are kept (there's no live Strava sync connected yet, see sync_activities) —
    once Strava is connected, the same sessions may appear in both `activities` and here;
    prefer `activities` for anything after that point. Always reprocesses and upserts by
    a synthetic id, so re-importing an overlapping export is harmless."""
    conn = rw()
    try:
        return apple_workouts_tools.import_workouts(conn, paths)
    except apple_workouts.AppleWorkoutError as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        conn.close()


@mcp.tool()
def query(sql: str) -> list[dict]:
    """Read-only SQL against the health database. Must be a single SELECT or WITH
    statement.

    Schema:
      products(id, name, brand, source, kcal_100g, protein_100g, carbs_100g, fat_100g,
               fibre_100g, sugar_100g, sat_fat_100g, salt_100g, note, created_at)
      food_log(id, logged_at, date, product_id, name, source, grams, entered_as,
               kcal, protein, carbs, fat, note)
      workouts(id, title, start_time, end_time, date, updated_at, raw)
      exercise_templates(id, title, primary_muscle_group, secondary_muscle_groups,
               equipment)
      workout_exercises(id, workout_id, idx, exercise_template_id, title)
      workout_sets(id, workout_exercise_id, idx, type, weight_kg, reps, rpe,
               duration_s, distance_m)
      body_measurements(date, weight_kg, fat_percent)
      activities(id, name, type, sport_type, start_date, date, elapsed_time_s,
               moving_time_s, distance_m, total_elevation_gain_m, average_speed_mps,
               max_speed_mps, average_heartrate, max_heartrate)
      daily_steps(date, steps, source)
      apple_workouts(id, source, workout_type, start_date, end_date, date, duration_s,
               energy_kcal, distance_m)
      sync_state(source, cursor, last_run_at, last_status, last_error)

    `date` columns are always the 04:00 Europe/Amsterdam day, computed at write time —
    group by `date`, not by a calendar date derived from a timestamp.
    """
    conn = ro()
    try:
        return [dict(row) for row in query_tool.query(conn, sql)]
    finally:
        conn.close()
