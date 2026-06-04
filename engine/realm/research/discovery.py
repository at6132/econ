"""Unified discovery digest — assay, research, patents, and player-authored content."""

from __future__ import annotations

from typing import Any

from realm.actions.assay_actions import party_recipe_book_summary
from realm.core.ids import PartyId
from realm.production.custom_content import custom_materials_public, custom_recipes_for_party
from realm.research.capabilities import capabilities_public, party_capability_ids
from realm.research.patents import party_patent_ids
from realm.research.research_lab import party_research_summary
from realm.research.workshop_focus import party_workshop_focuses
from realm.world import World


def recipes_available_for_custom_build(world: World, party: PartyId) -> list[str]:
    """Recipe ids the party may attach to a custom blueprint or focus."""
    book = world.party_recipe_books.get(str(party), set())
    from realm.production.recipes import RECIPES

    out = sorted(rid for rid in book if rid in RECIPES or rid.startswith("custom_recipe_"))
    for row in custom_recipes_for_party(world, party):
        rid = str(row.get("recipe_id", ""))
        if rid and rid not in out:
            out.append(rid)
    return sorted(out)


def party_blueprints_authored(world: World, party: PartyId) -> list[dict[str, Any]]:
    ps = str(party)
    rows: list[dict[str, Any]] = []
    from realm.production.blueprints import blueprint_public_dict

    for bid, bp in sorted(world.blueprints.items()):
        if str(getattr(bp, "creator_party", "") or "") != ps:
            continue
        rows.append(blueprint_public_dict(bp))
    return rows


def party_discovery_digest(world: World, party: PartyId) -> dict[str, Any]:
    """Single payload for Science / Fabrication UI."""
    assay = party_recipe_book_summary(world, party)
    research = party_research_summary(world, party)
    custom_mats = [
        m
        for m in custom_materials_public(world)
        if str(m.get("creator_party", "")) == str(party)
    ]
    return {
        "capabilities": capabilities_public(world, party),
        "capability_ids": sorted(party_capability_ids(world, party)),
        "max_blueprint_cells": _max_cells(world, party),
        "buildable_recipe_ids": recipes_available_for_custom_build(world, party),
        "workshop_focuses": party_workshop_focuses(world, party),
        "assay": {
            "known_recipe_count": len(assay.get("known", [])),
            "progress": assay.get("progress", []),
            "active_jobs": assay.get("active_jobs", []),
        },
        "research": research,
        "patents": party_patent_ids(world, party),
        "custom_materials": custom_mats,
        "custom_recipes": custom_recipes_for_party(world, party),
        "blueprints_authored": party_blueprints_authored(world, party),
        "recipe_book_size": len(world.party_recipe_books.get(str(party), set())),
        "machines_catalog": _machines_catalog(world, party),
    }


def _machines_catalog(world: World, party: PartyId) -> list[dict[str, Any]]:
    from realm.production.factory_design import machines_catalog_for_party

    return machines_catalog_for_party(world, party)


def _max_cells(world: World, party: PartyId) -> int:
    from realm.research.capabilities import party_max_blueprint_cells

    return party_max_blueprint_cells(world, party)
