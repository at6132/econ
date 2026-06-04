"""Player research actions — technology tree (parallel to assay)."""

from __future__ import annotations

from typing import Any

from realm.actions._shared import ActionResult
from realm.actions.fabrication_actions import research_catalog_for_party
from realm.core.ids import PartyId
from realm.research.research_lab import party_research_summary, start_research
from realm.world import World


def research_catalog_public(world: World, party: PartyId) -> dict[str, Any]:
    return research_catalog_for_party(world, party)


def start_research_action(
    world: World, party: PartyId, node_id: str
) -> ActionResult:
    return start_research(world, party, node_id)


def party_research_status(world: World, party: PartyId) -> dict[str, Any]:
    return party_research_summary(world, party)
