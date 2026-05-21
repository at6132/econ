"""HTTP-facing actions for player-defined materials and recipes."""

from __future__ import annotations

from realm.actions._shared import ActionResult
from realm.core.ids import PartyId
from realm.production.custom_content import create_custom_recipe, register_custom_material
from realm.world import World


def register_material_action(
    world: World,
    party: PartyId,
    display_name: str,
    category: str = "processed",
    material_id: str = "",
) -> ActionResult:
    return register_custom_material(world, party, display_name, category, material_id)


def create_custom_recipe_action(
    world: World,
    party: PartyId,
    display_name: str,
    inputs: dict[str, int],
    outputs: dict[str, int],
    duration_ticks: int,
    labor_cents: int,
    requires_building_id: str,
    *,
    is_public: bool = False,
) -> ActionResult:
    return create_custom_recipe(
        world,
        party,
        display_name,
        inputs,
        outputs,
        duration_ticks,
        labor_cents,
        requires_building_id,
        is_public=is_public,
    )
