"""Test helpers — stage bulk on plots when plot logistics applies."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr, MatterResult
from realm.infrastructure.plot_logistics import try_add_plot_output
from realm.production.storage_caps import is_carried_material, party_uses_plot_storage
from realm.world import World
from realm.world.terrain import Terrain


def first_owned_plot(world: World, party: PartyId) -> PlotId | None:
    for p in world.plots.values():
        if p.owner == party:
            return p.plot_id
    return None


def first_unowned_land_plot(world: World) -> PlotId:
    for p in world.plots.values():
        if p.owner is None and p.terrain not in (Terrain.WATER_DEEP, Terrain.WATER_SHALLOW):
            return p.plot_id
    raise AssertionError("no unowned land plot")


def seed_settler_workshop_materials(
    world: World,
    materials: list[tuple[str, int]],
) -> None:
    """Claim land, survey, and seed inputs settlers need when exchange staples are gone."""
    settlers = sorted(
        (p for p in world.parties if str(p).startswith("settler_")),
        key=str,
    )
    land_plots = [
        pid
        for pid, pl in world.plots.items()
        if pl.owner is None
        and pl.terrain not in (Terrain.WATER_DEEP, Terrain.WATER_SHALLOW)
    ]
    for settler, pid in zip(settlers, land_plots):
        claim_plot(world, settler, pid)
        survey_plot(world, settler, pid)
        for mid_s, qty in materials:
            ad = world.inventory.add(settler, MaterialId(mid_s), qty)
            assert not isinstance(ad, MatterErr)
        pick = world.inventory.add(settler, MaterialId("mining_pick"), 1)
        assert not isinstance(pick, MatterErr)


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
