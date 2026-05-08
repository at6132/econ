"""Hand-authored recipe templates (Primitive 6) — Phase 1 starter set."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping

from realm.ids import MaterialId


@dataclass(frozen=True, slots=True)
class Recipe:
    recipe_id: str
    display_name: str
    inputs: dict[MaterialId, int]
    outputs: dict[MaterialId, int]
    duration_ticks: int
    labor_cents: int  # paid to system reserve at production start (wage reserve)


RECIPES: Final[Mapping[str, Recipe]] = {
    "sawmill": Recipe(
        recipe_id="sawmill",
        display_name="Sawmill (timber → lumber)",
        inputs={MaterialId("timber"): 2, MaterialId("electricity"): 1},
        outputs={MaterialId("lumber"): 1},
        duration_ticks=2,
        labor_cents=5_00,
    ),
    "smelt_iron": Recipe(
        recipe_id="smelt_iron",
        display_name="Smelt iron",
        inputs={
            MaterialId("iron_ore"): 1,
            MaterialId("coal"): 1,
            MaterialId("electricity"): 1,
        },
        outputs={MaterialId("iron_ingot"): 1},
        duration_ticks=3,
        labor_cents=8_00,
    ),
    "smelt_copper": Recipe(
        recipe_id="smelt_copper",
        display_name="Smelt copper",
        inputs={
            MaterialId("copper_ore"): 1,
            MaterialId("coal"): 1,
            MaterialId("electricity"): 1,
        },
        outputs={MaterialId("copper_ingot"): 1},
        duration_ticks=3,
        labor_cents=8_00,
    ),
    "coal_generator": Recipe(
        recipe_id="coal_generator",
        display_name="Generator (coal → electricity)",
        inputs={MaterialId("coal"): 1},
        outputs={MaterialId("electricity"): 2},
        duration_ticks=2,
        labor_cents=2_00,
    ),
    "kiln_brick": Recipe(
        recipe_id="kiln_brick",
        display_name="Kiln (clay → brick)",
        inputs={
            MaterialId("clay"): 2,
            MaterialId("coal"): 1,
            MaterialId("electricity"): 1,
        },
        outputs={MaterialId("brick"): 2},
        duration_ticks=4,
        labor_cents=6_00,
    ),
}


def recipe_public_list() -> list[dict]:
    out: list[dict] = []
    for r in RECIPES.values():
        out.append(
            {
                "id": r.recipe_id,
                "display_name": r.display_name,
                "inputs": {str(k): v for k, v in r.inputs.items()},
                "outputs": {str(k): v for k, v in r.outputs.items()},
                "duration_ticks": r.duration_ticks,
                "labor_cents": r.labor_cents,
            }
        )
    return out
