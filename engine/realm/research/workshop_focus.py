"""Per-plot workshop focus — player chooses which recipe the site optimizes for."""

from __future__ import annotations

from typing import Any, Final

from realm.actions._shared import ActionResult
from realm.core.ids import PartyId, PlotId
from realm.events.event_log import log_event
from realm.research.capabilities import party_has_capability
from realm.world import World

_FOCUS_KEY: Final[str] = "workshop_focus"
_FOCUS_MATCH_BONUS: Final[float] = 0.15
_FOCUS_OFFSITE_PENALTY: Final[float] = 0.03


def _focus_root(world: World) -> dict[str, dict[str, str]]:
    raw = world.scenario_state.setdefault(_FOCUS_KEY, {})
    if not isinstance(raw, dict):
        world.scenario_state[_FOCUS_KEY] = {}
        raw = world.scenario_state[_FOCUS_KEY]
    return raw  # type: ignore[return-value]


def get_plot_workshop_focus(world: World, party: PartyId, plot_id: PlotId) -> str | None:
    party_map = _focus_root(world).get(str(party), {})
    if not isinstance(party_map, dict):
        return None
    rid = party_map.get(str(plot_id))
    return str(rid) if rid else None


def party_workshop_focuses(world: World, party: PartyId) -> dict[str, str]:
    party_map = _focus_root(world).get(str(party), {})
    if not isinstance(party_map, dict):
        return {}
    return {str(k): str(v) for k, v in party_map.items()}


def workshop_focus_multiplier(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    recipe_id: str,
) -> float:
    """Applied at production completion on ``plot_id``."""
    if not party_has_capability(world, party, "workshop_focus"):
        return 1.0
    focused = get_plot_workshop_focus(world, party, plot_id)
    if not focused:
        return 1.0
    if str(recipe_id) == focused:
        return 1.0 + _FOCUS_MATCH_BONUS
    return 1.0 - _FOCUS_OFFSITE_PENALTY


def set_workshop_focus(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    recipe_id: str,
) -> ActionResult:
    if not party_has_capability(world, party, "workshop_focus"):
        return {"ok": False, "reason": "workshop focus not unlocked — research electric motors"}
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    if not plot.surveyed:
        return {"ok": False, "reason": "plot not surveyed"}
    rid = str(recipe_id).strip()
    if not rid:
        return clear_workshop_focus(world, party, plot_id)
    from realm.production.custom_content import get_recipe

    if get_recipe(world, rid) is None:
        return {"ok": False, "reason": "unknown recipe"}
    if not world.can_party_run_recipe(party, rid):
        return {"ok": False, "reason": "recipe not in your discovery book"}
    root = _focus_root(world)
    party_map = root.setdefault(str(party), {})
    if not isinstance(party_map, dict):
        root[str(party)] = {}
        party_map = root[str(party)]
    party_map[str(plot_id)] = rid
    log_event(
        world,
        "workshop_focus_set",
        f"{party} focused {plot_id} on {rid}",
        party=str(party),
        plot_id=str(plot_id),
        recipe_id=rid,
    )
    return {"ok": True, "plot_id": str(plot_id), "recipe_id": rid}


def clear_workshop_focus(
    world: World,
    party: PartyId,
    plot_id: PlotId,
) -> ActionResult:
    root = _focus_root(world)
    party_map = root.get(str(party))
    if isinstance(party_map, dict):
        party_map.pop(str(plot_id), None)
    return {"ok": True, "plot_id": str(plot_id), "recipe_id": None}
