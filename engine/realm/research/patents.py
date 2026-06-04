"""Global-first research completions — patent awards."""

from __future__ import annotations

from realm.core.ids import PartyId
from realm.events.event_log import log_event
from realm.research.tech_tree import TECH_NODES
from realm.world import World


def _global_first(world: World) -> dict[str, str]:
    raw = world.scenario_state.setdefault("research_global_first", {})
    if not isinstance(raw, dict):
        world.scenario_state["research_global_first"] = {}
        raw = world.scenario_state["research_global_first"]
    return raw


def _party_patents(world: World) -> dict[str, list[str]]:
    raw = world.scenario_state.setdefault("patents", {})
    if not isinstance(raw, dict):
        world.scenario_state["patents"] = {}
        raw = world.scenario_state["patents"]
    return raw  # type: ignore[return-value]


def try_award_patent(world: World, party: PartyId, node_id: str) -> bool:
    """If ``party`` is the first globally to complete ``node_id``, record a patent.

    Returns True when a new patent was granted.
    """
    first = _global_first(world)
    if node_id in first:
        return False
    first[node_id] = str(party)
    plist = _party_patents(world).setdefault(str(party), [])
    if not isinstance(plist, list):
        _party_patents(world)[str(party)] = []
        plist = _party_patents(world)[str(party)]
    if node_id not in plist:
        plist.append(node_id)
    node = TECH_NODES.get(node_id, {})
    log_event(
        world,
        "world_feed",
        f"PATENT: {party} was first to complete research on {node_id} — global recognition.",
        feed_source="research_patent",
        party=str(party),
        node_id=node_id,
        era=str(node.get("era", "")),
    )
    log_event(
        world,
        "research_patent",
        f"{party} awarded patent for {node_id}",
        party=str(party),
        node_id=node_id,
    )
    return True


def party_patent_ids(world: World, party: PartyId) -> list[str]:
    raw = _party_patents(world).get(str(party), [])
    if not isinstance(raw, list):
        return []
    return sorted(str(x) for x in raw)
