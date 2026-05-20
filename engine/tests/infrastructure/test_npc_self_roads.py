"""NPC self-build road connectivity."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import Inventory, MatterErr
from realm.core.ledger import Ledger, MoneyErr, party_cash_account, system_reserve_account
from realm.infrastructure.road_connectivity import ROAD_REQUIREMENT_GRACE_TICKS, is_road_accessible
from realm.infrastructure.npc_self_roads import (
    pick_road_edge,
    plot_needs_road_access,
    try_connect_plot_with_road,
)
from realm.infrastructure.roads import build_road
from realm.world.terrain import Terrain
from realm.world import Plot, SubsurfaceRoll, World


def _grid_world() -> tuple[World, PartyId, PlotId]:
    sub = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.4,
        coal_grade=0.6,
    )
    plots: dict[PlotId, Plot] = {}
    for y in range(8):
        for x in range(8):
            pid = PlotId(f"p-{x}-{y}")
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=Terrain.PLAINS,
                owner=None,
                subsurface=sub,
                surveyed=True,
            )
    world = World(
        seed=11,
        tick=ROAD_REQUIREMENT_GRACE_TICKS + 100,
        plots=plots,
        ledger=Ledger(),
        inventory=Inventory(),
        parties=set(),
        scenario_id="genesis",
    )
    assert not isinstance(world.ledger.seed_system_reserve(10_000_000_000), MoneyErr)
    npc = PartyId("settler_0")
    world.parties.add(npc)
    cash = party_cash_account(npc)
    world.ledger.ensure_account(cash)
    world.ledger.transfer(
        debit=system_reserve_account(),
        credit=cash,
        amount_cents=500_000,
    )
    for mat, qty in (("lumber", 10), ("stone", 10)):
        assert not isinstance(world.inventory.add(npc, MaterialId(mat), qty), MatterErr)
    workshop_plot = PlotId("p-4-4")
    world.plots[workshop_plot].owner = npc
    world.next_building_instance_seq += 1
    world.plot_buildings.append(
        {
            "instance_id": "b000001",
            "plot_id": str(workshop_plot),
            "party": str(npc),
            "building_id": "strip_mine",
            "completes_at_tick": 0,
        }
    )
    return world, npc, workshop_plot


def test_plot_needs_road_when_workshop_isolated() -> None:
    world, npc, pid = _grid_world()
    assert plot_needs_road_access(world, npc, pid)
    assert not is_road_accessible(world, pid)


def test_npc_builds_road_on_adjacent_edge() -> None:
    world, npc, pid = _grid_world()
    edge = pick_road_edge(world, pid)
    assert edge is not None
    assert try_connect_plot_with_road(world, npc, pid)
    assert len(world.road_segments) == 1
    assert is_road_accessible(world, pid)


def test_npc_extends_chain_toward_existing_segment() -> None:
    world, npc, pid = _grid_world()
    hub = PlotId("p-6-6")
    assert build_road(world, npc, hub, PlotId("p-7-6"))["ok"]
    assert not is_road_accessible(world, pid)
    edge = pick_road_edge(world, pid)
    assert edge is not None
    assert try_connect_plot_with_road(world, npc, pid)
    assert is_road_accessible(world, pid)
    assert len(world.road_segments) >= 2
