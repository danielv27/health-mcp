"""Backend-proxied chat with Claude, scoped to this person's own health data.

Mirrors the MCP server's own philosophy (docs/adr/0006): the model gets exactly one
data tool, read-only SQL via `query`, never a bespoke tool per question. The API key
lives only in the server process (HEALTH_MCP_ANTHROPIC_API_KEY) — it never reaches the
browser, and the browser only ever sees the assistant's text.
"""

import json

from anthropic import Anthropic

from health_mcp.db import ro
from health_mcp.tools import query as query_tool

_SYSTEM_PROMPT = """You are the assistant embedded in a personal health-tracking app \
for one person (Daniel): food logging, Hevy workout data, weight, and steps, all in one \
SQLite database. Answer questions about his training and eating history using the \
query_health_db tool — never guess numbers you can look up. Keep answers short and \
direct; this is a chat panel next to his dashboards, not a report. Day boundary is \
04:00 Europe/Amsterdam, already baked into every `date` column — group by `date`."""

_SCHEMA = """Schema:
  products(id, name, brand, source, kcal_100g, protein_100g, carbs_100g, fat_100g,
           fibre_100g, sugar_100g, sat_fat_100g, salt_100g, note, created_at)
  food_log(id, logged_at, date, product_id, name, source, grams, entered_as,
           kcal, protein, carbs, fat, note, meal_id)
  meals(id, date, meal_type, logged_at)
  workouts(id, title, start_time, end_time, date, updated_at, raw)
  exercise_templates(id, title, primary_muscle_group, secondary_muscle_groups, equipment)
  workout_exercises(id, workout_id, idx, exercise_template_id, title)
  workout_sets(id, workout_exercise_id, idx, type, weight_kg, reps, rpe, duration_s, distance_m)
  body_measurements(date, weight_kg, fat_percent)
  daily_steps(date, steps, source)
  sync_state(source, cursor, last_run_at, last_status, last_error)"""

_TOOLS = [
    {
        "name": "query_health_db",
        "description": f"Read-only SQL against the health database. Must be a single "
        f"SELECT or WITH statement.\n\n{_SCHEMA}",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
        },
    }
]

_MODEL = "claude-sonnet-5"
_MAX_TOOL_ROUNDS = 6


def _run_query_tool(sql: str) -> str:
    conn = ro()
    try:
        rows = query_tool.query(conn, sql)
        return json.dumps([dict(r) for r in rows], default=str)
    except Exception as exc:  # noqa: BLE001 — surfaced to the model, not raised
        return json.dumps({"error": str(exc)})
    finally:
        conn.close()


def send_message(api_key: str, history: list[dict]) -> str:
    """`history` is [{role: "user"|"assistant", content: str}, ...] ending in a user
    turn. Returns the assistant's final text reply after resolving any tool calls."""
    client = Anthropic(api_key=api_key)
    messages: list[dict] = [{"role": m["role"], "content": m["content"]} for m in history]

    for _ in range(_MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            tools=_TOOLS,
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text").strip()

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = _run_query_tool(block.input.get("sql", ""))
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": result}
            )
        messages.append({"role": "user", "content": tool_results})

    return "I couldn't get a clean answer in time — try narrowing the question."
