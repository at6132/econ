"""Road connectivity gates for production after the grace period."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import Inventory, MatterErr
from realm.core.ledger import Ledger, MoneyErr, party_cash_account, system_reserve_account
from realm.infrastructure.road_connectivity import (
    ROAD_REQUIREMENT_GRACE_TICKS,
    is_road_accessible,
    invalidate_road_cache,
    plot_site_roads_connect_workshops,
)
from realm.world.placed_buildings import PlacedBuilding, register_placed_building
from realm.infrastructure.roads import build_road
from realm.production import start_production
from realm.world.terrain import Terrain
from realm.world import Plot, SubsurfaceRoll, World


def _build_world() -> tuple[World, PartyId]:
    sub = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.5,
        coal_grade=0.5,
    )
    plots: dict[PlotId, Plot] = {}
    for y in range(12):
        for x in range(12):
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
        seed=7,
        tick=0,
        plots=plots,
        ledger=Ledger(),
        inventory=Inventory(),
        parties=set(),
        scenario_id="testbed",
    )
    assert not isinstance(world.ledger.seed_system_reserve(10_000_000_000), MoneyErr)
    player = PartyId("player")
    world.parties.add(player)
    world.ledger.ensure_account(party_cash_account(player))
    world.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(player),
        amount_cents=1_000_000,
    )
    return world, player


def _claim(world: World, party: PartyId, plot_id: PlotId) -> None:
    world.plots[plot_id].owner = party
    world.plots[plot_id].surveyed = True


def _install_strip_mine(world: World, party: PartyId, plot_id: PlotId) -> None:
    world.next_building_instance_seq += 1
    iid = f"b{world.next_building_instance_seq:06d}"
    world.plot_buildings.append(
        {
            "instance_id": iid,
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": "strip_mine",
            "completes_at_tick": 0,
        }
    )
    world.building_maintenance[iid] = {"efficiency_pct": 100, "missed_cycles": 0, "due_at_tick": 0}


def _give_electricity(world: World, party: PartyId, qty: int) -> None:
    res = world.inventory.add(party, MaterialId("electricity"), qty)
    assert not isinstance(res, MatterErr)


def test_production_blocked_without_road_after_grace_period() -> None:
    world, player = _build_world()
    isolated = PlotId("p-8-8")
    _claim(world, player, isolated)
    _install_strip_mine(world, player, isolated)
    _give_electricity(world, player, 4)
    world.tick = ROAD_REQUIREMENT_GRACE_TICKS + 1
    r = start_production(world, player, isolated, "mine_coal", run_count=1)
    assert not r["ok"], r
    assert "road" in r["reason"].lower()


def test_production_allowed_during_grace_period() -> None:
    world, player = _build_world()
    pid = PlotId("p-3-3")
    _claim(world, player, pid)
    _install_strip_mine(world, player, pid)
    _give_electricity(world, player, 4)
    world.tick = 0
    r = start_production(world, player, pid, "mine_coal", run_count=1)
    if not r["ok"]:
        assert "road" not in r["reason"].lower()


def test_adjacent_road_counts_as_access() -> None:
    world, player = _build_world()
    road_plot = PlotId("p-2-2")
    adjacent = PlotId("p-3-2")
    _claim(world, player, road_plot)
    world.inventory.add(player, MaterialId("lumber"), 4)
    world.inventory.add(player, MaterialId("stone"), 4)
    assert build_road(world, player, road_plot, PlotId("p-2-3"))["ok"]
    invalidate_road_cache()
    assert is_road_accessible(world, road_plot)
    assert is_road_accessible(world, adjacent)


def test_hand_mining_exempt_from_road_requirement() -> None:
    world, player = _build_world()
    isolated = PlotId("p-9-9")
    _claim(world, player, isolated)
    world.tick = ROAD_REQUIREMENT_GRACE_TICKS + 1000
    r = start_production(world, player, isolated, "hand_mine_coal", run_count=1)
    if not r["ok"]:
        assert "road" not in r["reason"].lower()


def test_generator_exempt_from_road_requirement() -> None:
    world, player = _build_world()
    pid = PlotId("p-4-4")
    _claim(world, player, pid)
    world.next_building_instance_seq += 1
    iid = f"b{world.next_building_instance_seq:06d}"
    world.plot_buildings.append(
        {
            "instance_id": iid,
            "plot_id": str(pid),
            "party": str(player),
            "building_id": "power_shed",
            "completes_at_tick": 0,
        }
    )
    world.building_maintenance[iid] = {"efficiency_pct": 100, "missed_cycles": 0, "due_at_tick": 0}
    world.inventory.add(player, MaterialId("coal"), 4)
    world.tick = ROAD_REQUIREMENT_GRACE_TICKS + 5000
    r = start_production(world, player, pid, "coal_generator", run_count=1)
    if not r["ok"]:
        assert "road" not in r["reason"].lower()


def test_site_road_adjacent_to_workshop_allows_production() -> None:
    world, player = _build_world()
    pid = PlotId("p-5-5")
    _claim(world, player, pid)
    world.tick = ROAD_REQUIREMENT_GRACE_TICKS + 1
    from realm.production.blueprints import seed_world_blueprints

    seed_world_blueprints(world)
    world.next_building_instance_seq += 1
    register_placed_building(
        world,
        PlacedBuilding(
            instance_id="b000010",
            blueprint_id="strip_mine",
            plot_id=str(pid),
            grid_x=2,
            grid_y=2,
            built_at_tick=0,
            built_by=str(player),
            status="active",
            efficiency_pct=100,
            missed_maintenance_cycles=0,
            due_at_tick=0,
        ),
    )
    # Road east of 6×4 strip_mine footprint (not overlapping).
    register_placed_building(
        world,
        PlacedBuilding(
            instance_id="b000011",
            blueprint_id="road_segment",
            plot_id=str(pid),
            grid_x=8,
            grid_y=2,
            built_at_tick=0,
            built_by=str(player),
            status="active",
            efficiency_pct=100,
            missed_maintenance_cycles=0,
            due_at_tick=0,
        ),
    )
    assert plot_site_roads_connect_workshops(world, pid)
    assert not is_road_accessible(world, pid)
    _give_electricity(world, player, 4)
    r = start_production(world, player, pid, "mine_coal", run_count=1)
    assert r["ok"], r.get("reason", "")


def test_road_cache_invalidates_on_new_road() -> None:
    world, player = _build_world()
    a = PlotId("p-1-1")
    b = PlotId("p-2-1")
    _claim(world, player, a)
    assert not is_road_accessible(world, b)
    world.inventory.add(player, MaterialId("lumber"), 4)
    world.inventory.add(player, MaterialId("stone"), 4)
    assert build_road(world, player, a, b)["ok"]
    assert is_road_accessible(world, b)
