"""Phase 2 content bar: material and recipe catalog sizes (doc 18 C2–C3)."""

from __future__ import annotations

from realm.materials import MATERIALS
from realm.production.recipes import RECIPES


def test_material_catalog_meets_phase2_bar() -> None:
    assert len(MATERIALS) >= 25


def test_recipe_catalog_meets_phase2_bar() -> None:
    assert len(RECIPES) >= 15
