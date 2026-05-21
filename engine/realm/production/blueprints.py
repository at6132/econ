"""Building blueprints — footprints, construction, licensing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from realm.core.time_scale import BUILD_CONTRACTED_TICKS, BUILD_SIMPLE_TICKS
from realm.production.buildings import BUILDINGS
from realm.production.recipes import RECIPES

# Footprint (cells wide × tall) for seeded workshop blueprints.
_SEEDED_FOOTPRINTS: Final[dict[str, tuple[int, int]]] = {
    "strip_mine": (6, 4),
    "foundry": (4, 4),
    "timber_yard": (5, 3),
    "grain_row": (8, 4),
    "gristmill": (3, 3),
    "power_shed": (2, 2),
    "wood_shop": (3, 3),
    "stone_works": (4, 3),
    "kiln_shed": (3, 3),
    "residence": (2, 2),
    "store": (3, 2),
    "dock": (4, 2),
    "waystation": (2, 2),
    "tidal_mill": (3, 2),
    "apothecary": (2, 2),
    "laboratory": (4, 3),
    "blast_furnace": (5, 4),
    "forge_press": (3, 3),
    "tool_workshop": (3, 3),
    "assay_lab": (3, 2),
    "bank_building": (4, 3),
    "chemical_works": (4, 3),
    "machine_shop": (4, 4),
    "drill_rig": (3, 3),
    "shipyard": (5, 3),
    "field_stockade": (2, 2),
    "road_segment": (1, 1),
    "tool_cache": (2, 2),
    "watch_hut": (2, 2),
    "warehouse": (4, 4),
    "battery_bank": (2, 2),
}


def _recipes_for_building(building_id: str) -> list[str]:
    return [
        rid
        for rid, r in RECIPES.items()
        if str(getattr(r, "requires_building_id", "") or "") == building_id
    ]


def _category_for(building_id: str) -> str:
    if building_id in ("strip_mine", "timber_yard", "grain_row", "drill_rig"):
        return "extraction"
    if building_id in (
        "foundry",
        "wood_shop",
        "stone_works",
        "kiln_shed",
        "gristmill",
        "blast_furnace",
        "chemical_works",
        "forge_press",
        "tool_workshop",
        "machine_shop",
        "shipyard",
    ):
        return "processing"
    if building_id in (
        "power_shed",
        "tidal_mill",
        "dock",
        "waystation",
        "road_segment",
        "warehouse",
        "battery_bank",
    ):
        return "infrastructure"
    if building_id in ("store", "bank_building", "apothecary"):
        return "commerce"
    if building_id in ("residence",):
        return "population"
    if building_id in ("assay_lab", "laboratory"):
        return "research"
    return "custom"


def _blueprint_from_building_spec(bid: str, spec: dict) -> Blueprint:
    fw, fh = _SEEDED_FOOTPRINTS.get(bid, (3, 3))
    kind = str(spec.get("kind", "simple"))
    if kind == "simple":
        mats: dict[str, int] = {
            str(k): int(v) for k, v in (spec.get("material_inputs") or {}).items()
        }
        labor = int(spec.get("cost_cents", 0))
        ticks = int(spec.get("construction_ticks", BUILD_SIMPLE_TICKS))
    else:
        mats = {str(k): int(v) for k, v in (spec.get("self_materials") or {}).items()}
        labor = int(spec.get("self_shell_cents", 0)) + int(
            spec.get("self_contractor_fee_cents", 0)
        )
        ticks = int(spec.get("construction_ticks", BUILD_CONTRACTED_TICKS))
    desc = str(spec.get("description") or spec.get("label", bid))
    sched = spec.get("maintenance_schedule") or {}
    maint_mats = {
        str(k): int(v) for k, v in (sched.get("materials") or {}).items()
    }
    terrain_req = spec.get("terrain_required")
    if terrain_req:
        terr_list = (
            list(terrain_req)
            if not isinstance(terrain_req, str)
            else [str(terrain_req)]
        )
    else:
        terr_list = []
    requires_coastal = "coastal" in terr_list
    return Blueprint(
        blueprint_id=bid,
        name=str(spec.get("label", bid)),
        description=desc,
        footprint_w=fw,
        footprint_h=fh,
        construction_materials=mats,
        construction_labor_cents=labor,
        construction_ticks=ticks,
        enabled_recipe_ids=_recipes_for_building(bid),
        maintenance_interval_ticks=int(sched.get("interval_ticks", 0)),
        maintenance_materials=maint_mats,
        maintenance_grace_ticks=int(sched.get("grace_ticks", 0)),
        is_seeded=True,
        creator_party=None,
        is_public=True,
        license_fee_cents=0,
        license_contract_id=None,
        category=_category_for(bid),
        terrain_requirements=[t for t in terr_list if t != "coastal"],
        requires_coastal=requires_coastal,
        requires_power=False,
    )


@dataclass
class Blueprint:
    blueprint_id: str
    name: str
    description: str
    footprint_w: int
    footprint_h: int
    construction_materials: dict[str, int]
    construction_labor_cents: int
    construction_ticks: int
    enabled_recipe_ids: list[str]
    maintenance_interval_ticks: int
    maintenance_materials: dict[str, int]
    maintenance_grace_ticks: int
    is_seeded: bool
    creator_party: str | None
    is_public: bool
    license_fee_cents: int
    license_contract_id: str | None
    category: str
    terrain_requirements: list[str]
    requires_coastal: bool
    requires_power: bool


SEEDED_BLUEPRINTS: Final[dict[str, Blueprint]] = {
    bid: _blueprint_from_building_spec(bid, spec)
    for bid, spec in BUILDINGS.items()
}


def seed_world_blueprints(world: object) -> None:
    """Populate ``world.blueprints`` from seeded catalog (idempotent)."""
    from realm.world.world import World

    assert isinstance(world, World)
    if not world.blueprints:
        world.blueprints.update(SEEDED_BLUEPRINTS)


def blueprint_public_dict(bp: Blueprint) -> dict:
    return {
        "blueprint_id": bp.blueprint_id,
        "name": bp.name,
        "description": bp.description,
        "footprint_w": bp.footprint_w,
        "footprint_h": bp.footprint_h,
        "construction_materials": dict(bp.construction_materials),
        "construction_labor_cents": bp.construction_labor_cents,
        "construction_ticks": bp.construction_ticks,
        "enabled_recipe_ids": list(bp.enabled_recipe_ids),
        "maintenance_interval_ticks": bp.maintenance_interval_ticks,
        "maintenance_materials": dict(bp.maintenance_materials),
        "maintenance_grace_ticks": bp.maintenance_grace_ticks,
        "is_seeded": bp.is_seeded,
        "creator_party": bp.creator_party,
        "is_public": bp.is_public,
        "license_fee_cents": bp.license_fee_cents,
        "category": bp.category,
        "terrain_requirements": list(bp.terrain_requirements),
        "requires_coastal": bp.requires_coastal,
        "requires_power": bp.requires_power,
    }
