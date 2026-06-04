"""Fabrication gates — ties capabilities to custom content and blueprints."""

from __future__ import annotations

from typing import Any

from realm.core.ids import PartyId
from realm.research.capabilities import (
    CAPABILITY_SPECS,
    party_has_capability,
    party_max_blueprint_cells,
)
from realm.research.discovery import party_discovery_digest, recipes_available_for_custom_build
from realm.world import World


def validate_custom_material_registration(world: World, party: PartyId) -> str | None:
    if not party_has_capability(world, party, "custom_material"):
        return "custom materials not unlocked"
    return None


def validate_custom_recipe_creation(world: World, party: PartyId) -> str | None:
    if not party_has_capability(world, party, "custom_recipe"):
        return "custom recipes not unlocked — research Precision tooling at a research lab"
    return None


def validate_custom_recipe_public(world: World, party: PartyId) -> str | None:
    if not party_has_capability(world, party, "public_custom_recipes"):
        return "public custom recipes not unlocked — research Computers"
    return None


def validate_blueprint_registration(
    world: World,
    party: PartyId,
    footprint_w: int,
    footprint_h: int,
    enabled_recipe_ids: list[str],
) -> str | None:
    cells = int(footprint_w) * int(footprint_h)
    max_cells = party_max_blueprint_cells(world, party)
    if max_cells <= 0:
        return "custom blueprints not unlocked — research Workshop engineering"
    if cells > max_cells:
        return f"footprint {footprint_w}×{footprint_h} exceeds your limit ({max_cells} cells)"
    from realm.production.custom_content import custom_recipes_store

    allowed = set(recipes_available_for_custom_build(world, party))
    for rid in enabled_recipe_ids:
        if str(rid) in allowed:
            continue
        row = custom_recipes_store(world).get(str(rid))
        if isinstance(row, dict) and str(row.get("creator_party", "")) == str(party):
            continue
        return f"recipe '{rid}' is not in your discovery book"
    return None


def validate_blueprint_public_license(world: World, party: PartyId, is_public: bool) -> str | None:
    if is_public and not party_has_capability(world, party, "blueprint_public_license"):
        return "public blueprint licensing not unlocked — research Molecular assembly"
    return None


def fabrication_status(world: World, party: PartyId) -> dict[str, Any]:
    digest = party_discovery_digest(world, party)
    digest["capability_specs"] = {
        cid: {
            "label": spec["label"],
            "description": spec.get("description", ""),
        }
        for cid, spec in CAPABILITY_SPECS.items()
    }
    return digest
