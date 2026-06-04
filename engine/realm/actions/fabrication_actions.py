"""Fabrication & discovery actions for open-ended player industry."""

from __future__ import annotations

from typing import Any

from realm.actions._shared import ActionResult
from realm.core.ids import PartyId, PlotId
from realm.research.discovery import party_discovery_digest, recipes_available_for_custom_build
from realm.research.fabrication import fabrication_status
from realm.research.research_lab import (
    _completed_for_party,
    _era_unlocked_for_party,
    _party_has_research_lab,
    start_research,
)
from realm.research.tech_tree import ERAS, TECH_NODES
from realm.research.workshop_focus import clear_workshop_focus, set_workshop_focus
from realm.world import World


def research_catalog_for_party(world: World, party: PartyId) -> dict[str, Any]:
    """Tech tree with per-node eligibility for this party."""
    completed = _completed_for_party(world, party)
    has_lab = _party_has_research_lab(world, party)
    active_raw = (world.scenario_state.get("active_research") or {}).get(str(party))
    active_nid = (
        str(active_raw.get("node_id", ""))
        if isinstance(active_raw, dict)
        else ""
    )
    nodes_out: dict[str, Any] = {}
    for nid, spec in TECH_NODES.items():
        era_id = str(spec["era"])
        blocked: list[str] = []
        if nid in completed:
            state = "completed"
        elif active_nid == nid:
            state = "in_progress"
        else:
            state = "available"
        if not has_lab:
            blocked.append("need research_lab")
        if not _era_unlocked_for_party(world, party, era_id):
            blocked.append(f"era {era_id} locked")
        for prereq in spec.get("prereq_nodes", []):
            if str(prereq) not in completed:
                blocked.append(f"needs {prereq}")
        if state == "completed":
            blocked = []
        can_start = state == "available" and not blocked
        nodes_out[nid] = {
            **spec,
            "node_id": nid,
            "state": state,
            "can_start": can_start,
            "blocked_reasons": blocked,
        }
    return {
        "eras": dict(ERAS),
        "nodes": nodes_out,
        "has_research_lab": has_lab,
    }


def start_research_action(world: World, party: PartyId, node_id: str) -> ActionResult:
    return start_research(world, party, node_id)


def set_workshop_focus_action(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    recipe_id: str,
) -> ActionResult:
    return set_workshop_focus(world, party, plot_id, recipe_id)


def clear_workshop_focus_action(
    world: World, party: PartyId, plot_id: PlotId
) -> ActionResult:
    return clear_workshop_focus(world, party, plot_id)


def discovery_digest_action(world: World, party: PartyId) -> dict[str, Any]:
    return party_discovery_digest(world, party)


def fabrication_status_action(world: World, party: PartyId) -> dict[str, Any]:
    return fabrication_status(world, party)


def buildable_recipes_action(world: World, party: PartyId) -> dict[str, Any]:
    return {
        "recipe_ids": recipes_available_for_custom_build(world, party),
    }
