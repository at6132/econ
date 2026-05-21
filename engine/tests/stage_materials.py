"""Test helpers — stage bulk on plots when plot logistics applies."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr, MatterResult
from realm.infrastructure.plot_logistics import try_add_plot_output
from realm.production.storage_caps import is_carried_material, party_uses_plot_storage
from realm.world import World


def first_owned_plot(world: World, party: PartyId) -> PlotId | None:
    for p in world.plots.values():
        if p.owner == party:
            return p.plot_id
    return None


def stage_material(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    *,
    plot_id: PlotId | None = None,
) -> MatterResult:
    """Add units to plot bulk or personal carry, matching production rules."""
    if party_uses_plot_storage(world, party) and not is_carried_material(material):
        pid = plot_id or first_owned_plot(world, party)
        if pid is None:
            return MatterErr(reason="no owned plot for bulk staging")
        return try_add_plot_output(world, pid, party, material, qty)
    return world.inventory.add(party, material, qty)
