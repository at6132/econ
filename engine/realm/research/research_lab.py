"""Research lab actions — era tech tree progress (parallel to assay discovery)."""

from __future__ import annotations

import math
from typing import Any, Final

from realm.actions._shared import ActionResult
from realm.core.ids import PartyId
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event
from realm.production.recipes import RECIPES
from realm.research.capabilities import grant_capabilities
from realm.research.patents import party_patent_ids, try_award_patent
from realm.research.tech_tree import ERAS, TECH_NODES, era_node_ids, era_spec, node_spec
from realm.world import World, ensure_party_recipe_book

RESEARCHER_SKILL_THRESHOLD: Final[int] = 60
"""Employed laborers at or above this skill level count as researchers."""

_ACTIVE_KEY: Final[str] = "active_research"
_COMPLETED_KEY: Final[str] = "research_completed"
_BONUSES_KEY: Final[str] = "research_bonuses"
_ERAS_UNLOCKED_KEY: Final[str] = "research_eras_unlocked"


def _active_research(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault(_ACTIVE_KEY, {})
    if not isinstance(raw, dict):
        world.scenario_state[_ACTIVE_KEY] = {}
        raw = world.scenario_state[_ACTIVE_KEY]
    return raw  # type: ignore[return-value]


def _completed_for_party(world: World, party: PartyId) -> set[str]:
    root = world.scenario_state.setdefault(_COMPLETED_KEY, {})
    if not isinstance(root, dict):
        world.scenario_state[_COMPLETED_KEY] = {}
        root = world.scenario_state[_COMPLETED_KEY]
    raw = root.get(str(party), [])
    if isinstance(raw, set):
        return {str(x) for x in raw}
    if isinstance(raw, list):
        return {str(x) for x in raw}
    return set()


def _set_completed(world: World, party: PartyId, completed: set[str]) -> None:
    root = world.scenario_state.setdefault(_COMPLETED_KEY, {})
    if not isinstance(root, dict):
        world.scenario_state[_COMPLETED_KEY] = {}
        root = world.scenario_state[_COMPLETED_KEY]
    root[str(party)] = sorted(completed)


def _party_bonuses(world: World, party: PartyId) -> dict[str, float]:
    root = world.scenario_state.setdefault(_BONUSES_KEY, {})
    if not isinstance(root, dict):
        world.scenario_state[_BONUSES_KEY] = {}
        root = world.scenario_state[_BONUSES_KEY]
    raw = root.get(str(party), {})
    if not isinstance(raw, dict):
        root[str(party)] = {}
        raw = root[str(party)]
    return {str(k): float(v) for k, v in raw.items()}


def _eras_unlocked_for_party(world: World, party: PartyId) -> set[str]:
    root = world.scenario_state.setdefault(_ERAS_UNLOCKED_KEY, {})
    if not isinstance(root, dict):
        world.scenario_state[_ERAS_UNLOCKED_KEY] = {}
        root = world.scenario_state[_ERAS_UNLOCKED_KEY]
    raw = root.get(str(party), [])
    out: set[str] = set()
    if isinstance(raw, list):
        out = {str(x) for x in raw}
    for era_id, spec in ERAS.items():
        if spec["unlocked_at_boot"]:
            out.add(era_id)
    return out


def _set_eras_unlocked(world: World, party: PartyId, eras: set[str]) -> None:
    root = world.scenario_state.setdefault(_ERAS_UNLOCKED_KEY, {})
    if not isinstance(root, dict):
        world.scenario_state[_ERAS_UNLOCKED_KEY] = {}
        root = world.scenario_state[_ERAS_UNLOCKED_KEY]
    root[str(party)] = sorted(eras)


def count_party_researchers(world: World, party: PartyId) -> int:
    """Employed laborers with skill ≥ :data:`RESEARCHER_SKILL_THRESHOLD`."""
    n = 0
    for lab in world.laborers.values():
        if lab.employer != party:
            continue
        if float(lab.skill_level) >= RESEARCHER_SKILL_THRESHOLD:
            n += 1
    return n


def research_daily_bonus(researcher_count: int) -> float:
    """+0.5 per researcher above 1, capped at +3.0."""
    if researcher_count <= 1:
        return 0.0
    return min(3.0, 0.5 * float(researcher_count - 1))


def _party_has_research_lab(world: World, party: PartyId) -> bool:
    from realm.production.decay import building_effective_for_bonuses
    from realm.core.time_scale import building_operational

    for b in world.plot_buildings:
        if b.get("party") != str(party):
            continue
        if b.get("building_id") != "research_lab":
            continue
        if not building_operational(b, at_tick=world.tick):
            continue
        if not building_effective_for_bonuses(b):
            continue
        return True
    return False


def _era_unlocked_for_party(world: World, party: PartyId, era_id: str) -> bool:
    spec = era_spec(era_id)
    if spec is None:
        return False
    if spec["unlocked_at_boot"]:
        return True
    stored = _eras_unlocked_for_party(world, party)
    if era_id in stored:
        return True
    prereq = spec.get("prereq")
    if prereq is not None and not _era_unlocked_for_party(world, party, str(prereq)):
        return False
    if prereq is not None:
        completed = _completed_for_party(world, party)
        if not all(nid in completed for nid in era_node_ids(str(prereq))):
            return False
    return True


def _unlock_child_eras(world: World, party: PartyId, completed_era: str) -> None:
    """After finishing all nodes in an era, unlock direct child eras."""
    eras = _eras_unlocked_for_party(world, party)
    completed = _completed_for_party(world, party)
    nodes_in_era = era_node_ids(completed_era)
    if nodes_in_era and not all(nid in completed for nid in nodes_in_era):
        return
    for era_id, spec in ERAS.items():
        if spec.get("prereq") == completed_era:
            eras.add(era_id)
    _set_eras_unlocked(world, party, eras)


def _apply_efficiency_bonus(world: World, party: PartyId, bonus: dict[str, float]) -> None:
    if not bonus:
        return
    root = world.scenario_state.setdefault(_BONUSES_KEY, {})
    if not isinstance(root, dict):
        world.scenario_state[_BONUSES_KEY] = {}
        root = world.scenario_state[_BONUSES_KEY]
    existing = _party_bonuses(world, party)
    for key, val in bonus.items():
        existing[str(key)] = float(existing.get(str(key), 0.0)) + float(val)
    root[str(party)] = existing


def start_research(world: World, party: PartyId, node_id: str) -> ActionResult:
    """Begin researching a tech node (requires operational ``research_lab``)."""
    if party not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    node = node_spec(node_id)
    if node is None:
        return {"ok": False, "reason": "unknown tech node"}
    if not _party_has_research_lab(world, party):
        return {"ok": False, "reason": "no operational research_lab"}
    era_id = str(node["era"])
    if not _era_unlocked_for_party(world, party, era_id):
        return {"ok": False, "reason": f"era {era_id} not unlocked"}
    completed = _completed_for_party(world, party)
    if node_id in completed:
        return {"ok": False, "reason": "research already completed"}
    for prereq in node.get("prereq_nodes", []):
        if str(prereq) not in completed:
            return {"ok": False, "reason": f"prerequisite not met: {prereq}"}
    active = _active_research(world)
    if str(party) in active:
        return {"ok": False, "reason": "research already in progress"}
    researchers = count_party_researchers(world, party)
    base_days = int(node["research_cost_days"])
    effective_days = max(1, int(math.ceil(base_days / max(1, researchers))))
    active[str(party)] = {
        "node_id": node_id,
        "progress_days": 0.0,
        "started_tick": int(world.tick),
        "research_cost_days": effective_days,
        "base_cost_days": base_days,
        "researcher_count_at_start": researchers,
    }
    log_event(
        world,
        "research_started",
        f"{party} began research on {node_id} "
        f"({effective_days} effective days, {researchers} researcher(s))",
        party=str(party),
        node_id=node_id,
        effective_days=effective_days,
        researchers=researchers,
    )
    return {
        "ok": True,
        "node_id": node_id,
        "research_cost_days": effective_days,
        "researchers": researchers,
    }


def complete_research(world: World, party: PartyId, node_id: str) -> ActionResult:
    """Finalize a tech node: recipes, bonuses, feed, patent."""
    node = node_spec(node_id)
    if node is None:
        return {"ok": False, "reason": "unknown tech node"}
    completed = _completed_for_party(world, party)
    if node_id in completed:
        return {"ok": False, "reason": "already completed"}
    book = ensure_party_recipe_book(world, party)
    new_recipes: list[str] = []
    for rid in node.get("unlocks_recipes", []):
        rid_s = str(rid)
        if rid_s not in RECIPES:
            continue
        if rid_s not in book:
            book.add(rid_s)
            new_recipes.append(rid_s)
    completed.add(node_id)
    _set_completed(world, party, completed)
    _apply_efficiency_bonus(world, party, dict(node.get("efficiency_bonus", {})))
    new_caps = grant_capabilities(
        world, party, list(node.get("unlocks_capabilities", []))
    )
    _unlock_child_eras(world, party, str(node["era"]))
    active = _active_research(world)
    active.pop(str(party), None)
    unlocks_display = ", ".join(node.get("unlocks_recipes", [])) or "none"
    log_event(
        world,
        "world_feed",
        f"{party} completed research on {node_id} — {unlocks_display} now available.",
        feed_source="research_complete",
        party=str(party),
        node_id=node_id,
        unlocks=unlocks_display,
    )
    log_event(
        world,
        "research_complete",
        f"{party} completed {node_id} (+{len(new_recipes)} recipe(s))",
        party=str(party),
        node_id=node_id,
        new_recipe_count=len(new_recipes),
    )
    patented = try_award_patent(world, party, node_id)
    if new_caps:
        log_event(
            world,
            "world_feed",
            f"{party} unlocked capabilities: {', '.join(new_caps)}",
            feed_source="research_capability",
            party=str(party),
            capabilities=",".join(new_caps),
        )
    return {
        "ok": True,
        "node_id": node_id,
        "new_recipes": new_recipes,
        "new_capabilities": new_caps,
        "patent_awarded": patented,
    }


def tick_research_progress(world: World) -> None:
    """Advance active research once per game-day."""
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return
    active = _active_research(world)
    if not active:
        return
    for party_s, job in list(active.items()):
        if not isinstance(job, dict):
            active.pop(party_s, None)
            continue
        node_id = str(job.get("node_id", ""))
        node = node_spec(node_id)
        if node is None:
            active.pop(party_s, None)
            continue
        party = PartyId(party_s)
        researchers = count_party_researchers(world, party)
        bonus = research_daily_bonus(researchers)
        progress = float(job.get("progress_days", 0.0)) + 1.0 + bonus
        job["progress_days"] = progress
        cost = int(job.get("research_cost_days", node["research_cost_days"]))
        if progress >= float(cost):
            complete_research(world, party, node_id)


def party_research_summary(world: World, party: PartyId) -> dict[str, Any]:
    """Public snapshot for API / UI."""
    completed = sorted(_completed_for_party(world, party))
    job = _active_research(world).get(str(party))
    return {
        "completed": completed,
        "active": dict(job) if isinstance(job, dict) else None,
        "eras_unlocked": sorted(_eras_unlocked_for_party(world, party)),
        "efficiency_bonuses": dict(_party_bonuses(world, party)),
        "patents": party_patent_ids(world, party),
        "researchers": count_party_researchers(world, party),
    }
