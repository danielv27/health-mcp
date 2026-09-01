"""FastAPI backend for the food-logging UI.

A second, human-facing front door onto the same SQLite file the MCP server
reads and writes (see PRODUCT.md "Positioning") — imports `health_mcp.tools.food`
and `health_mcp.tools.targets` directly rather than reimplementing logging logic.
Each request opens and closes its own connection (db.rw/db.ro), matching the
short-lived-connection pattern the MCP tools already use.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from health_mcp.config import settings as app_settings
from health_mcp.day import day_of, now_utc
from health_mcp.db import migrate, rw
from health_mcp.tools import trends
from health_mcp.tools.chat import send_message
from health_mcp.tools.food import Macros, delete_food_entry, find_product, log_food
from health_mcp.tools.meals import MEAL_TYPES, MealItem, delete_meal, infer_meal_type, log_meal
from health_mcp.tools.settings import get_settings, set_hevy_auto_sync
from health_mcp.tools.targets import get_targets, set_targets
from health_mcp.tools.training import sync_workouts

_log = logging.getLogger("health_mcp.web")

_SYNC_INTERVAL_MINUTES = 30
_scheduler = AsyncIOScheduler()


def _run_auto_sync() -> None:
    conn = rw()
    try:
        if not get_settings(conn)["hevy_auto_sync"]:
            return
        try:
            sync_workouts(conn)
        except Exception:  # noqa: BLE001 — a failed background sync must not crash the app
            _log.exception("background Hevy sync failed")
    finally:
        conn.close()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    migrate()
    _scheduler.add_job(_run_auto_sync, "interval", minutes=_SYNC_INTERVAL_MINUTES)
    _scheduler.start()
    yield
    _scheduler.shutdown(wait=False)


app = FastAPI(title="health-mcp food log", lifespan=_lifespan)


def get_conn() -> Iterator:
    conn = rw()
    try:
        yield conn
    finally:
        conn.close()


def _product_dict(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "brand": row["brand"],
        "source": row["source"],
        "kcal_100g": row["kcal_100g"],
        "protein_100g": row["protein_100g"],
        "carbs_100g": row["carbs_100g"],
        "fat_100g": row["fat_100g"],
    }


def _entry_dict(row) -> dict:
    return {
        "id": row["id"],
        "logged_at": row["logged_at"],
        "product_id": row["product_id"],
        "name": row["name"],
        "source": row["source"],
        "grams": row["grams"],
        "entered_as": row["entered_as"],
        "kcal": row["kcal"],
        "protein": row["protein"],
        "carbs": row["carbs"],
        "fat": row["fat"],
        "meal_id": row["meal_id"],
    }


@app.get("/api/products")
def api_find_products(q: str | None = None, conn=Depends(get_conn)):
    return [_product_dict(r) for r in find_product(conn, q)]


@app.get("/api/products/recent")
def api_recent_products(limit: int = 12, conn=Depends(get_conn)):
    """The most-logged-then-most-recent product/one-off pairs, each carrying the last
    grams logged and per-100g macros derived from that entry, so the frontend can
    replay a "log again" quick action with one tap."""
    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT *,
                COUNT(*) OVER (PARTITION BY COALESCE(product_id, name)) AS freq,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(product_id, name) ORDER BY logged_at DESC
                ) AS rn
            FROM food_log
        )
        SELECT * FROM ranked WHERE rn = 1 ORDER BY freq DESC, logged_at DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        scale = 100.0 / r["grams"] if r["grams"] else 0.0
        out.append(
            {
                "product_id": r["product_id"],
                "name": r["name"],
                "source": r["source"],
                "freq": r["freq"],
                "last_grams": r["grams"],
                "kcal_100g": r["kcal"] * scale,
                "protein_100g": r["protein"] * scale,
                "carbs_100g": r["carbs"] * scale,
                "fat_100g": r["fat"] * scale,
            }
        )
    return out


def _sum_macros(entries: list[dict]) -> dict:
    totals = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    for e in entries:
        for k in totals:
            totals[k] += e[k]
    return totals


@app.get("/api/today")
def api_today(conn=Depends(get_conn)):
    """Entries grouped by the meal they were logged under (newest meal first);
    `ungrouped` holds entries logged before meals existed, or any orphan a future
    migration leaves behind — never hidden, never silently reassigned a meal."""
    date = day_of(now_utc())
    entries = [
        _entry_dict(e)
        for e in conn.execute(
            "SELECT * FROM food_log WHERE date = ? ORDER BY logged_at DESC", (date.isoformat(),)
        ).fetchall()
    ]
    meal_rows = conn.execute(
        "SELECT * FROM meals WHERE date = ? ORDER BY logged_at DESC", (date.isoformat(),)
    ).fetchall()

    by_meal: dict[int, list[dict]] = {}
    ungrouped: list[dict] = []
    for e in entries:
        if e["meal_id"] is None:
            ungrouped.append(e)
        else:
            by_meal.setdefault(e["meal_id"], []).append(e)

    meals = [
        {
            "id": m["id"],
            "meal_type": m["meal_type"],
            "logged_at": m["logged_at"],
            "entries": by_meal[m["id"]],
            "subtotals": _sum_macros(by_meal[m["id"]]),
        }
        for m in meal_rows
        if m["id"] in by_meal  # skip meals left with zero entries — see delete_food_entry
    ]

    targets_row = get_targets(conn)
    targets = (
        {
            "kcal": targets_row["kcal"],
            "protein": targets_row["protein"],
            "carbs": targets_row["carbs"],
            "fat": targets_row["fat"],
        }
        if targets_row
        else None
    )
    return {
        "date": date.isoformat(),
        "totals": _sum_macros(entries),
        "targets": targets,
        "meals": meals,
        "ungrouped": ungrouped,
    }


@app.get("/api/meals/suggested-type")
def api_suggested_meal_type():
    return {"meal_type": infer_meal_type()}


class MealItemRequest(BaseModel):
    grams: float
    product_id: int | None = None
    name: str | None = None
    macros: Macros | None = None
    entered_as: str | None = None


class MealRequest(BaseModel):
    meal_type: str
    items: list[MealItemRequest]


@app.post("/api/meals")
def api_log_meal(body: MealRequest, conn=Depends(get_conn)):
    if body.meal_type not in MEAL_TYPES:
        raise HTTPException(status_code=400, detail=f"meal_type must be one of {MEAL_TYPES}")
    try:
        result = log_meal(
            conn,
            meal_type=body.meal_type,
            items=[
                MealItem(
                    grams=i.grams,
                    product_id=i.product_id,
                    name=i.name,
                    macros=i.macros,
                    entered_as=i.entered_as,
                )
                for i in body.items
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    entries = conn.execute(
        "SELECT * FROM food_log WHERE meal_id = ? ORDER BY id", (result["meal_id"],)
    ).fetchall()
    return {"meal_id": result["meal_id"], "entries": [_entry_dict(e) for e in entries]}


@app.delete("/api/meals/{meal_id}")
def api_delete_meal(meal_id: int, conn=Depends(get_conn)):
    try:
        delete_meal(conn, meal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


class LogRequest(BaseModel):
    grams: float
    product_id: int | None = None
    name: str | None = None
    macros: Macros | None = None
    entered_as: str | None = None
    meal_id: int | None = None


@app.post("/api/log")
def api_log(body: LogRequest, conn=Depends(get_conn)):
    """Used by the "edit entry" flow only — replaces a single entry in place,
    preserving its `meal_id` so editing doesn't orphan it from its meal. New
    entries are always logged through POST /api/meals, never here."""
    try:
        entry_id = log_food(
            conn,
            grams=body.grams,
            product_id=body.product_id,
            name=body.name,
            macros=body.macros,
            entered_as=body.entered_as,
            meal_id=body.meal_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    entry = conn.execute("SELECT * FROM food_log WHERE id = ?", (entry_id,)).fetchone()
    return _entry_dict(entry)


@app.delete("/api/log/{entry_id}")
def api_delete_log(entry_id: int, conn=Depends(get_conn)):
    try:
        delete_food_entry(conn, entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


class TargetsRequest(BaseModel):
    kcal: float
    protein: float
    carbs: float
    fat: float


@app.get("/api/targets")
def api_get_targets(conn=Depends(get_conn)):
    row = get_targets(conn)
    if row is None:
        return None
    return {"kcal": row["kcal"], "protein": row["protein"], "carbs": row["carbs"], "fat": row["fat"]}


@app.put("/api/targets")
def api_set_targets(body: TargetsRequest, conn=Depends(get_conn)):
    row = set_targets(conn, kcal=body.kcal, protein=body.protein, carbs=body.carbs, fat=body.fat)
    return {"kcal": row["kcal"], "protein": row["protein"], "carbs": row["carbs"], "fat": row["fat"]}


@app.get("/api/settings")
def api_get_settings(conn=Depends(get_conn)):
    row = get_settings(conn)
    return {"hevy_auto_sync": bool(row["hevy_auto_sync"])}


class SettingsRequest(BaseModel):
    hevy_auto_sync: bool


@app.put("/api/settings")
def api_set_settings(body: SettingsRequest, conn=Depends(get_conn)):
    row = set_hevy_auto_sync(conn, body.hevy_auto_sync)
    return {"hevy_auto_sync": bool(row["hevy_auto_sync"])}


@app.get("/api/sync/status")
def api_sync_status(conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM sync_state WHERE source = 'hevy'").fetchone()
    return {
        "last_run_at": row["last_run_at"] if row else None,
        "last_status": row["last_status"] if row else None,
        "last_error": row["last_error"] if row else None,
    }


@app.post("/api/sync/hevy")
def api_sync_hevy(conn=Depends(get_conn)):
    """Manual "sync now" — runs the same sync_workouts the background job runs on an
    interval, regardless of whether auto-sync is enabled."""
    try:
        result = sync_workouts(conn)
    except Exception as exc:  # noqa: BLE001 — surfaced to the caller, not a 500 wall
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result


@app.get("/api/trends/food")
def api_trends_food(weeks: int = 12, conn=Depends(get_conn)):
    return trends.food_trends(conn, weeks)


@app.get("/api/trends/workouts")
def api_trends_workouts(weeks: int = 12, conn=Depends(get_conn)):
    return trends.workout_trends(conn, weeks)


@app.get("/api/trends/exercise")
def api_trends_exercise(title: str, weeks: int = 12, conn=Depends(get_conn)):
    return trends.exercise_progression(conn, title, weeks)


@app.get("/api/trends/weight")
def api_trends_weight(weeks: int = 12, conn=Depends(get_conn)):
    return trends.weight_trend(conn, weeks)


@app.get("/api/trends/correlation")
def api_trends_correlation(weeks: int = 12, conn=Depends(get_conn)):
    return trends.intake_vs_training(conn, weeks)


@app.get("/api/chat/status")
def api_chat_status():
    return {"configured": bool(app_settings.anthropic_api_key)}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@app.post("/api/chat")
def api_chat(body: ChatRequest):
    if not app_settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="Chat isn't configured — set HEALTH_MCP_ANTHROPIC_API_KEY on the server.",
        )
    reply = send_message(
        app_settings.anthropic_api_key, [m.model_dump() for m in body.messages]
    )
    return {"role": "assistant", "content": reply}


_DIST = Path(__file__).parent / "static"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        """vue-router uses createWebHistory (real paths, e.g. /trends), so every
        non-API, non-asset path must resolve to the SPA shell — StaticFiles(html=True)
        alone only covers "/", not deep links or a browser refresh on another tab."""
        candidate = _DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
