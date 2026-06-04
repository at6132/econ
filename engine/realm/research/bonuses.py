"""Research efficiency bonuses applied at production completion."""

from __future__ import annotations

from realm.core.ids import PartyId, PlotId
from realm.world import World


def _party_bonus_map(world: World, party: PartyId) -> dict[str, float]:
    root = world.scenario_state.get("research_bonuses")
    if not isinstance(root, dict):
        return {}
    raw = root.get(str(party))
    if not isinstance(raw, dict):
        return {}
    return {str(k): float(v) for k, v in raw.items()}


def research_output_multiplier(
    world: World,
    party: PartyId,
    recipe_id: str,
    *,
    plot_id: PlotId | None = None,
) -> float:
    """Composes per-recipe, ``all``, and optional workshop-focus bonuses."""
    bonuses = _party_bonus_map(world, party)
    mult = 1.0
    if bonuses:
        if "all" in bonuses:
            mult += float(bonuses["all"])
        rid = str(recipe_id)
        if rid in bonuses:
            mult += float(bonuses[rid])
    if plot_id is not None:
        from realm.research.workshop_focus import workshop_focus_multiplier

        mult *= workshop_focus_multiplier(world, party, plot_id, str(recipe_id))
    return max(0.0, mult)
