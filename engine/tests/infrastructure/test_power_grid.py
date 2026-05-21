"""Regional power grid — electricity always costs; road-linked market clearing."""

from __future__ import annotations

from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import Inventory, MatterErr
from realm.core.ledger import Ledger, MoneyErr, party_cash_account, system_reserve_account
from realm.infrastructure.power_grid import (
    compute_grid_regions,
    get_plot_power_info,
    record_electricity_consumed,
    tick_power_grid,
)
from realm.infrastructure.roads import build_road
from realm.production import start_production
from realm.world.terrain import Terrain
from realm.world import Plot, SubsurfaceRoll, World
from realm.world.tick import advance_tick


def _build_world(*, width: int = 20, height: int = 20) -> tuple[World, PartyId, PartyId]:
    sub = SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.5,
        coal_grade=0.5,
    )
    plots: dict[PlotId, Plot] = {}
    for y in range(height):
        for x in range(width):
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
        seed=42,
        tick=0,
        plots=plots,
        ledger=Ledger(),
        inventory=Inventory(),
        parties=set(),
        scenario_id="testbed",
        use_plot_output_logistics=True,
    )
    assert not isinstance(world.ledger.seed_system_reserve(10_000_000_000), MoneyErr)
    gen = PartyId("generator")
    consumer = PartyId("consumer")
    for p in (gen, consumer):
        world.parties.add(p)
        world.ledger.ensure_account(party_cash_account(p))
        world.ledger.transfer(
            debit=system_reserve_account(),
            credit=party_cash_account(p),
            amount_cents=500_000,
        )
    return world, gen, consumer


def _claim(world: World, party: PartyId, plot_id: PlotId) -> None:
    world.plots[plot_id].owner = party
    world.plots[plot_id].surveyed = True


def _install_building(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    building_id: str,
) -> str:
    world.next_building_instance_seq += 1
    iid = f"b{world.next_building_instance_seq:06d}"
    world.plot_buildings.append(
        {
            "instance_id": iid,
            "condition_bps": 10_000,
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": building_id,
            "label": building_id,
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    world.building_maintenance[iid] = {
        "due_at_tick": 9_999_999,
        "missed_cycles": 0,
        "efficiency_pct": 100,
    }
    return iid


def _give(world: World, party: PartyId, mat: str, qty: int) -> None:
    res = world.inventory.add(party, MaterialId(mat), qty)
    assert not isinstance(res, MatterErr)


def test_electricity_not_waived_without_inventory() -> None:
    world, _gen, consumer = _build_world()
    pid = PlotId("p-5-5")
    _claim(world, consumer, pid)
    _install_building(world, consumer, pid, "strip_mine")
    _give(world, consumer, "coal", 0)
    r = start_production(world, consumer, pid, "mine_coal", run_count=1)
    assert not r["ok"], r
    assert "electricity" in r["reason"].lower()


def test_production_succeeds_with_electricity_inventory() -> None:
    world, _gen, consumer = _build_world()
    pid = PlotId("p-5-5")
    _claim(world, consumer, pid)
    _install_building(world, consumer, pid, "strip_mine")
    _give(world, consumer, "electricity", 4)
    r = start_production(world, consumer, pid, "mine_coal", run_count=1)
    assert r["ok"], r


def test_grid_regions_split_by_road_components() -> None:
    world, gen, consumer = _build_world()
    a = PlotId("p-2-2")
    b = PlotId("p-3-2")
    c = PlotId("p-10-10")
    d = PlotId("p-11-10")
    _claim(world, gen, a)
    _claim(world, consumer, c)
    _install_building(world, gen, a, "power_shed")
    for party in (gen, consumer):
        world.inventory.add(party, MaterialId("lumber"), 10)
        world.inventory.add(party, MaterialId("stone"), 10)
    assert build_road(world, gen, a, b)["ok"]
    assert build_road(world, consumer, c, d)["ok"]
    regions = compute_grid_regions(world)
    region_ids = set()
    for pid in (a, b, c, d):
        for rid, reg in regions.items():
            if str(pid) in reg.plot_ids:
                region_ids.add(rid)
                break
    assert len(region_ids) == 2


def test_isolated_plot_with_power_shed_has_microgrid_capacity() -> None:
    world, gen, _consumer = _build_world()
    iso = PlotId("p-15-15")
    _claim(world, gen, iso)
    _install_building(world, gen, iso, "power_shed")
    info = get_plot_power_info(world, iso)
    assert info["powered"] is True
    assert info["capacity_per_day"] == 24
    assert info["grid_connected"] is False
    assert "microgrid" in str(info.get("status_note", "")).lower()


def test_generator_earns_revenue_from_consumers() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    _install_building(world, gen, gen_plot, "power_shed")
    _install_building(world, consumer, use_plot, "strip_mine")
    _give(world, consumer, "electricity", 4)
    world.inventory.add(gen, MaterialId("lumber"), 4)
    world.inventory.add(gen, MaterialId("stone"), 4)
    assert build_road(world, gen, gen_plot, use_plot)["ok"]
    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    gen_cash_before = world.ledger.balance(party_cash_account(gen))
    assert start_production(world, consumer, use_plot, "mine_coal")["ok"]
    world.tick = 1440
    tick_power_grid(world)
    gen_cash_after = world.ledger.balance(party_cash_account(gen))
    assert gen_cash_after > gen_cash_before
    assert_money_conserved(world.ledger, snap.ledger_total_cents)


def test_conservation_through_power_settlement() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    _install_building(world, gen, gen_plot, "power_shed")
    _install_building(world, consumer, use_plot, "strip_mine")
    _give(world, consumer, "electricity", 2)
    world.inventory.add(gen, MaterialId("lumber"), 4)
    world.inventory.add(gen, MaterialId("stone"), 4)
    assert build_road(world, gen, gen_plot, use_plot)["ok"]
    start = world.ledger.total_cents()
    record_electricity_consumed(world, use_plot, 2)
    world.tick = 1440
    tick_power_grid(world)
    end = world.ledger.total_cents()
    assert start == end


def test_brownout_reduces_consumer_efficiency() -> None:
    world, gen, consumer = _build_world()
    gen_plot = PlotId("p-4-4")
    use_plot = PlotId("p-5-4")
    _claim(world, gen, gen_plot)
    _claim(world, consumer, use_plot)
    kiln_iid = _install_building(world, consumer, use_plot, "kiln_shed")
    _install_building(world, gen, gen_plot, "power_shed")
    world.inventory.add(gen, MaterialId("lumber"), 4)
    world.inventory.add(gen, MaterialId("stone"), 4)
    assert build_road(world, gen, gen_plot, use_plot)["ok"]
    world.scenario_state["power_load_today"] = {str(use_plot): 100}
    world.tick = 1440
    tick_power_grid(world)
    maint = world.building_maintenance[kiln_iid]
    assert maint.get("brownout_penalty") is True
    assert int(maint["efficiency_pct"]) < 100
