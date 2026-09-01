"""Smoke tests for the food-logging web API (src/health_mcp/web/app.py)."""

import pytest
from fastapi.testclient import TestClient

from health_mcp.config import settings
from health_mcp.db import migrate


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "health.db"
    migrate(db_path)
    monkeypatch.setattr(settings, "db_path", db_path)

    from health_mcp.web.app import app

    return TestClient(app)


def log_meal(client, meal_type="lunch", items=None):
    items = items or [
        {
            "grams": 150,
            "name": "Rice, cooked",
            "macros": {"kcal_100g": 130, "protein_100g": 2.7, "carbs_100g": 28, "fat_100g": 0.3},
        }
    ]
    resp = client.post("/api/meals", json={"meal_type": meal_type, "items": items})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_today_empty(client):
    resp = client.get("/api/today")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"] == {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    assert body["meals"] == []
    assert body["ungrouped"] == []
    assert body["targets"] is None


def test_log_meal_appears_grouped_in_today(client):
    result = log_meal(client, meal_type="breakfast")
    assert len(result["entries"]) == 1

    today = client.get("/api/today").json()
    assert len(today["meals"]) == 1
    assert today["meals"][0]["meal_type"] == "breakfast"
    assert len(today["meals"][0]["entries"]) == 1
    assert today["meals"][0]["subtotals"]["kcal"] == pytest.approx(195.0)
    assert today["totals"]["kcal"] == pytest.approx(195.0)
    assert today["ungrouped"] == []


def test_log_meal_with_multiple_items_is_one_commit(client):
    result = log_meal(
        client,
        meal_type="dinner",
        items=[
            {"grams": 200, "name": "Chicken", "macros": {"kcal_100g": 165, "protein_100g": 31, "carbs_100g": 0, "fat_100g": 3.6}},
            {"grams": 100, "name": "Rice", "macros": {"kcal_100g": 130, "protein_100g": 2.7, "carbs_100g": 28, "fat_100g": 0.3}},
        ],
    )
    assert len(result["entries"]) == 2

    today = client.get("/api/today").json()
    assert len(today["meals"]) == 1
    assert len(today["meals"][0]["entries"]) == 2


def test_log_meal_rejects_unknown_meal_type(client):
    resp = client.post(
        "/api/meals",
        json={
            "meal_type": "brunch",
            "items": [{"grams": 100, "name": "x", "macros": {"kcal_100g": 1, "protein_100g": 1, "carbs_100g": 1, "fat_100g": 1}}],
        },
    )
    assert resp.status_code == 400
    assert client.get("/api/today").json()["meals"] == []


def test_suggested_meal_type_returns_a_valid_type(client):
    resp = client.get("/api/meals/suggested-type")
    assert resp.status_code == 200
    assert resp.json()["meal_type"] in {"breakfast", "lunch", "dinner", "snack"}


def test_delete_meal_removes_it_from_today(client):
    result = log_meal(client)
    resp = client.delete(f"/api/meals/{result['meal_id']}")
    assert resp.status_code == 200

    today = client.get("/api/today").json()
    assert today["meals"] == []
    assert today["totals"]["kcal"] == 0.0


def test_delete_missing_meal_404s(client):
    resp = client.delete("/api/meals/999")
    assert resp.status_code == 404


def test_edit_entry_via_log_preserves_meal_grouping(client):
    """The edit flow deletes then re-logs a single entry through POST /api/log
    (not /api/meals) — it must pass the original meal_id through so the entry
    stays under its meal rather than becoming ungrouped."""
    result = log_meal(client)
    entry = result["entries"][0]

    client.delete(f"/api/log/{entry['id']}")
    resp = client.post(
        "/api/log",
        json={
            "grams": 200,
            "name": entry["name"],
            "macros": {"kcal_100g": 130, "protein_100g": 2.7, "carbs_100g": 28, "fat_100g": 0.3},
            "meal_id": entry["meal_id"],
        },
    )
    assert resp.status_code == 200

    today = client.get("/api/today").json()
    assert len(today["meals"]) == 1
    assert len(today["meals"][0]["entries"]) == 1
    assert today["ungrouped"] == []


def test_deleting_last_entry_of_meal_removes_the_meal(client):
    result = log_meal(client)
    entry_id = result["entries"][0]["id"]

    client.delete(f"/api/log/{entry_id}")

    today = client.get("/api/today").json()
    assert today["meals"] == []


def test_ungrouped_entry_via_bare_log_endpoint(client):
    """POST /api/log with no meal_id is the legacy/edit-only path; it must not
    silently create a phantom meal — the entry stays in `ungrouped`."""
    resp = client.post(
        "/api/log",
        json={
            "grams": 100,
            "name": "Apple",
            "macros": {"kcal_100g": 52, "protein_100g": 0.3, "carbs_100g": 14, "fat_100g": 0.2},
        },
    )
    assert resp.status_code == 200

    today = client.get("/api/today").json()
    assert today["meals"] == []
    assert len(today["ungrouped"]) == 1

    resp = client.delete(f"/api/log/{resp.json()['id']}")
    assert resp.status_code == 200
    assert client.get("/api/today").json()["ungrouped"] == []


def test_targets_roundtrip(client):
    assert client.get("/api/targets").json() is None

    resp = client.put("/api/targets", json={"kcal": 2400, "protein": 180, "carbs": 250, "fat": 80})
    assert resp.status_code == 200
    assert resp.json()["kcal"] == 2400

    assert client.get("/api/targets").json()["protein"] == 180


def test_recent_products_orders_by_frequency(client):
    for _ in range(3):
        log_meal(
            client,
            items=[
                {
                    "grams": 100,
                    "name": "Oats",
                    "macros": {"kcal_100g": 389, "protein_100g": 17, "carbs_100g": 66, "fat_100g": 7},
                }
            ],
        )
    log_meal(
        client,
        items=[
            {
                "grams": 100,
                "name": "Banana",
                "macros": {"kcal_100g": 89, "protein_100g": 1.1, "carbs_100g": 23, "fat_100g": 0.3},
            }
        ],
    )

    recent = client.get("/api/products/recent").json()
    assert recent[0]["name"] == "Oats"
    assert recent[0]["freq"] == 3
    assert recent[0]["last_grams"] == 100
