"""GET /recipes — seeded catalog separate from /world/static."""

from __future__ import annotations

from fastapi.testclient import TestClient

from realm.api import app
from realm.production.recipes import RECIPES, recipe_public_list


def test_get_recipes_returns_catalog() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"scenario": "frontier", "seed": 77})
    r = c.get("/recipes")
    assert r.status_code == 200
    body = r.json()
    recipes = body.get("recipes")
    assert isinstance(recipes, list)
    assert len(recipes) == len(RECIPES)
    assert recipes[0]["id"] in RECIPES
    assert recipes == recipe_public_list()


def test_world_static_omits_recipes() -> None:
    c = TestClient(app)
    c.post("/dev/reset", params={"scenario": "frontier", "seed": 78})
    r = c.get("/world/static")
    assert r.status_code == 200
    body = r.json()
    assert "recipes" not in body
    assert "building_catalog" in body
    assert body["ticks_per_game_day"] > 0
