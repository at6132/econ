"""Hand-authored recipe templates (Primitive 6) — Phase 1 starter set."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping

from realm.ids import MaterialId
from realm.time_scale import legacy_scaled


@dataclass(frozen=True, slots=True)
class Recipe:
    recipe_id: str
    display_name: str
    inputs: dict[MaterialId, int]
    outputs: dict[MaterialId, int]
    duration_ticks: int
    labor_cents: int  # paid to system reserve at production start (wage reserve)
    requires_building_id: str  # plot must have this building_id (effective) to run recipe
    # Optional extraction gates: surveyed plot subsurface field must be >= min (0..1 rolls).
    requires_subsurface: tuple[tuple[str, float], ...] = ()
    # If set, scales that output material quantity by subsurface grade (field must match a gate).
    scaled_output: tuple[str, MaterialId] | None = None


RECIPES: Final[Mapping[str, Recipe]] = {
    "sawmill": Recipe(
        recipe_id="sawmill",
        display_name="Sawmill (timber → lumber)",
        inputs={MaterialId("timber"): 2, MaterialId("electricity"): 1},
        outputs={MaterialId("lumber"): 1},
        duration_ticks=legacy_scaled(2),
        labor_cents=5_00,
        requires_building_id="wood_shop",
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
        duration_ticks=legacy_scaled(3),
        labor_cents=8_00,
        requires_building_id="foundry",
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
        duration_ticks=legacy_scaled(3),
        labor_cents=8_00,
        requires_building_id="foundry",
    ),
    "coal_generator": Recipe(
        recipe_id="coal_generator",
        display_name="Generator (coal → electricity)",
        inputs={MaterialId("coal"): 1},
        outputs={MaterialId("electricity"): 2},
        duration_ticks=legacy_scaled(2),
        labor_cents=2_00,
        requires_building_id="power_shed",
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
        duration_ticks=legacy_scaled(4),
        labor_cents=6_00,
        requires_building_id="kiln_shed",
    ),
    "mine_stone": Recipe(
        recipe_id="mine_stone",
        display_name="Strip & crush (timber + power → stone)",
        inputs={MaterialId("timber"): 1, MaterialId("electricity"): 1},
        outputs={MaterialId("stone"): 2},
        duration_ticks=legacy_scaled(2),
        labor_cents=3_00,
        requires_building_id="stone_works",
    ),
    "wash_sand": Recipe(
        recipe_id="wash_sand",
        display_name="Wash & grade (stone + power → sand)",
        inputs={MaterialId("stone"): 2, MaterialId("electricity"): 1},
        outputs={MaterialId("sand"): 3},
        duration_ticks=legacy_scaled(2),
        labor_cents=3_00,
        requires_building_id="stone_works",
    ),
    "crush_limestone": Recipe(
        recipe_id="crush_limestone",
        display_name="Crush & calcine prep (stone → limestone + slag)",
        inputs={MaterialId("stone"): 3, MaterialId("electricity"): 1},
        outputs={MaterialId("limestone"): 2, MaterialId("slag"): 2},
        duration_ticks=legacy_scaled(3),
        labor_cents=4_00,
        requires_building_id="stone_works",
    ),
    "lime_burn": Recipe(
        recipe_id="lime_burn",
        display_name="Lime kiln (limestone + coal + power → quicklime + slag)",
        inputs={
            MaterialId("limestone"): 2,
            MaterialId("coal"): 1,
            MaterialId("electricity"): 1,
        },
        outputs={MaterialId("quicklime"): 1, MaterialId("slag"): 3},
        duration_ticks=legacy_scaled(4),
        labor_cents=6_00,
        requires_building_id="stone_works",
    ),
    "mortar_mix": Recipe(
        recipe_id="mortar_mix",
        display_name="Mortar (quicklime + sand + power → mortar + slag)",
        inputs={
            MaterialId("quicklime"): 1,
            MaterialId("sand"): 2,
            MaterialId("electricity"): 1,
        },
        outputs={MaterialId("mortar"): 2, MaterialId("slag"): 2},
        duration_ticks=legacy_scaled(2),
        labor_cents=3_00,
        requires_building_id="stone_works",
    ),
    "glass_blow": Recipe(
        recipe_id="glass_blow",
        display_name="Glass furnace (sand + coal + power → glass + slag)",
        inputs={
            MaterialId("sand"): 2,
            MaterialId("coal"): 1,
            MaterialId("electricity"): 1,
        },
        outputs={MaterialId("glass"): 1, MaterialId("slag"): 3},
        duration_ticks=legacy_scaled(4),
        labor_cents=7_00,
        requires_building_id="stone_works",
    ),
    "steel_alloy": Recipe(
        recipe_id="steel_alloy",
        display_name="Steel (iron + coal + power → steel + slag)",
        inputs={
            MaterialId("iron_ingot"): 1,
            MaterialId("coal"): 1,
            MaterialId("electricity"): 1,
        },
        outputs={MaterialId("steel_ingot"): 1, MaterialId("slag"): 2},
        duration_ticks=legacy_scaled(4),
        labor_cents=10_00,
        requires_building_id="foundry",
    ),
    "wire_draw": Recipe(
        recipe_id="wire_draw",
        display_name="Wire draw (copper ingot + power → wire)",
        inputs={MaterialId("copper_ingot"): 1, MaterialId("electricity"): 1},
        outputs={MaterialId("copper_wire"): 2},
        duration_ticks=legacy_scaled(2),
        labor_cents=4_00,
        requires_building_id="foundry",
    ),
    "charcoal_burn": Recipe(
        recipe_id="charcoal_burn",
        display_name="Charcoal retort (timber + power → charcoal + slag)",
        inputs={MaterialId("timber"): 2, MaterialId("electricity"): 1},
        outputs={MaterialId("charcoal"): 2, MaterialId("slag"): 1},
        duration_ticks=legacy_scaled(5),
        labor_cents=2_00,
        requires_building_id="wood_shop",
    ),
    "pottery_kiln": Recipe(
        recipe_id="pottery_kiln",
        display_name="Pottery (clay + coal + power → pottery + slag)",
        inputs={
            MaterialId("clay"): 2,
            MaterialId("coal"): 1,
            MaterialId("electricity"): 1,
        },
        outputs={MaterialId("pottery"): 2, MaterialId("slag"): 2},
        duration_ticks=legacy_scaled(4),
        labor_cents=5_00,
        requires_building_id="kiln_shed",
    ),
    "mill_flour": Recipe(
        recipe_id="mill_flour",
        display_name="Mill (grain + power → flour)",
        inputs={MaterialId("grain"): 2, MaterialId("electricity"): 2},
        outputs={MaterialId("flour"): 4},
        duration_ticks=legacy_scaled(2),
        labor_cents=3_00,
        requires_building_id="gristmill",
    ),
    "bake_bread": Recipe(
        recipe_id="bake_bread",
        display_name="Bake (flour + power → bread)",
        inputs={MaterialId("flour"): 2, MaterialId("electricity"): 2},
        outputs={MaterialId("bread"): 4},
        duration_ticks=legacy_scaled(3),
        labor_cents=4_00,
        requires_building_id="gristmill",
    ),
    "twist_rope": Recipe(
        recipe_id="twist_rope",
        display_name="Twist cordage (timber + power → rope)",
        inputs={MaterialId("timber"): 1, MaterialId("electricity"): 1},
        outputs={MaterialId("rope"): 3},
        duration_ticks=legacy_scaled(2),
        labor_cents=2_00,
        requires_building_id="wood_shop",
    ),
    "build_ladder": Recipe(
        recipe_id="build_ladder",
        display_name="Assemble ladder (lumber + rope + power)",
        inputs={
            MaterialId("lumber"): 2,
            MaterialId("rope"): 2,
            MaterialId("electricity"): 1,
        },
        outputs={MaterialId("ladder"): 1},
        duration_ticks=legacy_scaled(3),
        labor_cents=6_00,
        requires_building_id="wood_shop",
    ),
    # Extraction / primary sector — subsurface grades matter once surveyed (Genesis + Frontier).
    "mine_iron_ore": Recipe(
        recipe_id="mine_iron_ore",
        display_name="Mine iron ore (power + labor)",
        inputs={MaterialId("electricity"): 2},
        outputs={MaterialId("iron_ore"): 2},
        duration_ticks=legacy_scaled(3),
        labor_cents=6_00,
        requires_building_id="strip_mine",
        requires_subsurface=(("iron_ore_grade", 0.3),),
        scaled_output=("iron_ore_grade", MaterialId("iron_ore")),
    ),
    "mine_copper_ore": Recipe(
        recipe_id="mine_copper_ore",
        display_name="Mine copper ore (power + labor)",
        inputs={MaterialId("electricity"): 2},
        outputs={MaterialId("copper_ore"): 2},
        duration_ticks=legacy_scaled(3),
        labor_cents=6_00,
        requires_building_id="strip_mine",
        requires_subsurface=(("copper_ore_grade", 0.3),),
        scaled_output=("copper_ore_grade", MaterialId("copper_ore")),
    ),
    "mine_coal": Recipe(
        recipe_id="mine_coal",
        display_name="Mine coal (power + labor)",
        inputs={MaterialId("electricity"): 2},
        outputs={MaterialId("coal"): 2},
        duration_ticks=legacy_scaled(3),
        labor_cents=5_00,
        requires_building_id="strip_mine",
        requires_subsurface=(("coal_grade", 0.3),),
        scaled_output=("coal_grade", MaterialId("coal")),
    ),
    "dig_clay": Recipe(
        recipe_id="dig_clay",
        display_name="Dig clay (power + labor)",
        inputs={MaterialId("electricity"): 1},
        outputs={MaterialId("clay"): 2},
        duration_ticks=legacy_scaled(2),
        labor_cents=4_00,
        requires_building_id="strip_mine",
        requires_subsurface=(("clay_grade", 0.3),),
        scaled_output=("clay_grade", MaterialId("clay")),
    ),
    "chop_timber": Recipe(
        recipe_id="chop_timber",
        display_name="Chop timber (labor + power)",
        inputs={MaterialId("electricity"): 1},
        outputs={MaterialId("timber"): 2},
        duration_ticks=legacy_scaled(2),
        labor_cents=3_00,
        requires_building_id="timber_yard",
    ),
    "grow_grain": Recipe(
        recipe_id="grow_grain",
        display_name="Grow grain (irrigated row — power + labor)",
        inputs={MaterialId("electricity"): 2},
        outputs={MaterialId("grain"): 3},
        duration_ticks=legacy_scaled(5),
        labor_cents=4_00,
        requires_building_id="grain_row",
    ),
}


def recipe_public_list() -> list[dict]:
    out: list[dict] = []
    for r in RECIPES.values():
        row: dict = {
            "id": r.recipe_id,
            "display_name": r.display_name,
            "inputs": {str(k): v for k, v in r.inputs.items()},
            "outputs": {str(k): v for k, v in r.outputs.items()},
            "duration_ticks": r.duration_ticks,
            "labor_cents": r.labor_cents,
            "requires_building_id": r.requires_building_id,
        }
        if r.requires_subsurface:
            row["requires_subsurface"] = [{"field": f, "min": m} for f, m in r.requires_subsurface]
        if r.scaled_output is not None:
            fld, mid = r.scaled_output
            row["scaled_output"] = {"field": fld, "material": str(mid)}
        out.append(row)
    return out
