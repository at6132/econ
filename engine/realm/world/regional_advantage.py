"""Deterministic regional production efficiency modifiers (comparative advantage)."""

from __future__ import annotations

from typing import Final

from realm.core.ids import PlotId
from realm.core.rng import make_rng
from realm.world import World

ADVANTAGE_CATEGORIES: Final[list[str]] = [
    "mining",
    "agriculture",
    "manufacturing",
    "chemical",
    "timber",
    "construction",
]


def generate_regional_advantages(seed: int, n_landmasses: int) -> dict[int, dict[str, float]]:
    rng = make_rng(int(seed), "regional_advantage")
    advantages: dict[int, dict[str, float]] = {}
    for lm_id in range(int(n_landmasses)):
        mods: dict[str, float] = {}
        for cat in ADVANTAGE_CATEGORIES:
            mods[cat] = float(rng.uniform(0.80, 1.30))
        advantages[int(lm_id)] = mods
    return advantages


def seed_regional_advantages(world: World) -> None:
    if world.regional_advantages:
        return
    ids = {int(v) for v in world.landmass_id.values() if int(v) >= 0}
    if not ids:
        return
    n = max(ids) + 1
    world.regional_advantages = generate_regional_advantages(int(world.seed), n)


def _recipe_category(recipe_id: str) -> str:
    rid = str(recipe_id)
    if rid.startswith("mine_"):
        return "mining"
    if rid.startswith("grow_") or rid == "fishing":
        return "agriculture"
    if rid.startswith(("forge_", "smelt_", "assemble_")):
        return "manufacturing"
    if rid.startswith(("make_", "refine_", "process_")):
        return "chemical"
    if rid.startswith("chop_") or rid == "hand_chop":
        return "timber"
    if rid.startswith("build_"):
        return "construction"
    return "manufacturing"


def regional_advantage_modifier(world: World, plot_id: PlotId, recipe_id: str) -> float:
    plot = world.plots.get(plot_id)
    if plot is None:
        return 1.0
    lm_id = int(world.landmass_id.get(str(plot.plot_id), -1))
    if lm_id < 0:
        return 1.0
    adv = world.regional_advantages.get(lm_id) or {}
    cat = _recipe_category(recipe_id)
    return float(adv.get(cat, 1.0))


def qualitative_band(mod: float) -> str:
    if mod >= 1.2:
        return "Excellent"
    if mod >= 1.05:
        return "Good"
    if mod >= 0.95:
        return "Average"
    return "Poor"
