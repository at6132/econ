"""Plot access helpers — ownership vs active land lease (lessee may operate)."""

from __future__ import annotations

from realm.core.ids import PartyId, PlotId
from realm.world import World


def party_may_operate_plot(world: World, party: PartyId, plot_id: PlotId) -> bool:
    """True if ``party`` owns the plot or holds an active lease granting operate rights."""
    plot = world.plots.get(plot_id)
    if plot is None:
        return False
    if plot.owner == party:
        return True
    raw = world.scenario_state.get("plot_lease_rights")
    if not isinstance(raw, dict):
        return False
    row = raw.get(str(plot_id))
    if not isinstance(row, dict):
        return False
    if str(row.get("lessee", "")) != str(party):
        return False
    exp = int(row.get("expires_tick", 0))
    return int(world.tick) < exp
