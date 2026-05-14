"""Sprint 3 — Phase D · coastal advantages.

Covers:
- Fishing fails inland and succeeds coastal (Sprint 1 gate still holds).
- Fishing now produces ``fish`` (real material, not grain proxy).
- ``fish`` spoils in 12 game-hours; ``smoked_fish`` keeps for 10 game-days.
- Coastal → coastal shipping gets a 40 % discount.
- ``tidal_mill`` building requires coastal terrain.
- ``tidal_power`` recipe runs without coal input.
"""

from __future__ import annotations

from realm.production.buildings import BUILDINGS, build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import Inventory, MatterErr
from realm.core.ledger import (
    Ledger,
    MoneyErr,
    party_cash_account,
    system_reserve_account,
)
from realm.materials import MATERIALS
from realm.infrastructure.movement import (
    BASE_SHIP_FEE_CENTS,
    PER_TILE_SHIP_CENTS,
    dispatch_shipment,
)
from realm.production import start_production, tick_production
from realm.world.terrain import Terrain
from realm.world import Plot, SubsurfaceRoll, World


def _build_test_world(*, width: int = 10, height: int = 10) -> tuple[World, PartyId]:
    sub = SubsurfaceRoll(0.0, 0.0, 0.0, 0.0)
    plots: dict[PlotId, Plot] = {}
    for y in range(height):
        for x in range(width):
            pid = PlotId(f"p-{x}-{y}")
            terrain = Terrain.WATER_SHALLOW if y == height - 1 else Terrain.PLAINS
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=terrain,
                owner=None,
                subsurface=sub,
                surveyed=True,
            )
    w = World(
        seed=1,
        tick=100,
        plots=plots,
        ledger=Ledger(),
        inventory=Inventory(),
        parties=set(),
        scenario_id="testbed",
        use_plot_output_logistics=False,
    )
    assert not isinstance(w.ledger.seed_system_reserve(10_000_000_000), MoneyErr)
    p = PartyId("alice")
    w.parties.add(p)
    w.ledger.ensure_account(party_cash_account(p))
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(p),
        amount_cents=10_000_000,
    )
    w.reputation[str(p)] = {"honored": 0, "breached": 0}
    return w, p


def _give(world: World, party: PartyId, mat: str, qty: int) -> None:
    res = world.inventory.add(party, MaterialId(mat), qty)
    assert not isinstance(res, MatterErr)


def test_fishing_blocked_inland() -> None:
    w, p = _build_test_world(width=10, height=10)
    inland = PlotId("p-5-2")  # nowhere near water
    w.plots[inland].owner = p
    _give(w, p, "hand_saw", 1)
    r = start_production(w, p, inland, "fishing")
    assert not r["ok"], r
    assert "coast" in r["reason"].lower() or "site" in r["reason"].lower() or "terrain" in r["reason"].lower()


def test_fishing_allowed_coastal_produces_fish() -> None:
    w, p = _build_test_world(width=10, height=10)
    coastal = PlotId("p-3-8")  # row 8, water at row 9 (coastal adjacency)
    w.plots[coastal].owner = p
    _give(w, p, "hand_saw", 1)
    r = start_production(w, p, coastal, "fishing")
    assert r["ok"], r
    for _ in range(int(r["ticks_remaining"]) + 1):
        w.tick += 1
        tick_production(w)
    assert w.inventory.qty(p, MaterialId("fish")) >= 2


def test_fish_spoils_quickly() -> None:
    interval = MATERIALS[MaterialId("fish")].spoilage_interval_ticks
    # 12 game-hours = 720 ticks
    assert interval == 720


def test_smoked_fish_lasts_longer() -> None:
    raw_interval = MATERIALS[MaterialId("fish")].spoilage_interval_ticks
    smoked_interval = MATERIALS[MaterialId("smoked_fish")].spoilage_interval_ticks
    assert smoked_interval > raw_interval * 10


def test_coastal_shipping_discount() -> None:
    """Inter-coastal shipping costs 40 % less than the inland baseline."""
    w, p = _build_test_world(width=20, height=10)
    # Two coastal plots in different regions, then two inland plots in
    # different regions for the baseline comparison.
    coastal_a = PlotId("p-1-8")
    coastal_b = PlotId("p-18-8")
    inland_a = PlotId("p-1-2")
    inland_b = PlotId("p-18-2")
    for pid in (coastal_a, coastal_b, inland_a, inland_b):
        w.plots[pid].owner = p
    # Cargo on both source plots.
    _give(w, p, "grain", 100)
    r_coastal = dispatch_shipment(
        w, p, MaterialId("grain"), 5, coastal_a, coastal_b
    )
    assert r_coastal["ok"], r_coastal
    assert r_coastal["coastal_route"] is True
    r_inland = dispatch_shipment(
        w, p, MaterialId("grain"), 5, inland_a, inland_b
    )
    assert r_inland["ok"], r_inland
    assert r_inland["coastal_route"] is False
    assert int(r_coastal["fee_cents"]) < int(r_inland["fee_cents"]), (
        r_coastal,
        r_inland,
    )
    # Sanity: discount should be ~40 %.
    assert r_coastal["fee_cents"] <= int(r_inland["fee_cents"]) * 0.7


def test_harbor_speed_bonus_from_dock_plot() -> None:
    """A dock-equipped coastal source dispatches 1.5 × faster."""
    w, p = _build_test_world(width=20, height=10)
    src = PlotId("p-3-8")
    dst = PlotId("p-16-8")
    w.plots[src].owner = p
    w.plots[dst].owner = p
    _give(w, p, "grain", 50)
    # Baseline shipment, no dock yet.
    r0 = dispatch_shipment(w, p, MaterialId("grain"), 2, src, dst)
    assert r0["ok"], r0
    base_transit = int(r0["arrive_tick"]) - int(w.tick)
    # Plant a completed dock on the source plot manually.
    w.next_building_instance_seq += 1
    iid = f"b{w.next_building_instance_seq:06d}"
    w.plot_buildings.append(
        {
            "instance_id": iid,
            "condition_bps": 10_000,
            "plot_id": str(src),
            "party": str(p),
            "building_id": "dock",
            "label": "dock",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    r1 = dispatch_shipment(w, p, MaterialId("grain"), 2, src, dst)
    assert r1["ok"], r1
    assert r1["harbor_speedup"] is True
    fast_transit = int(r1["arrive_tick"]) - int(w.tick)
    assert fast_transit < base_transit, (fast_transit, base_transit)


def test_tidal_mill_coastal_only() -> None:
    """Inland tidal_mill construction is rejected."""
    w, p = _build_test_world(width=10, height=10)
    inland = PlotId("p-5-2")
    w.plots[inland].owner = p
    # Grant materials so the failure is solely on terrain.
    mats = BUILDINGS["tidal_mill"]["self_materials"] or {}
    for mid_s, qty in mats.items():
        _give(w, p, mid_s, int(qty) + 2)
    r = build_on_plot(w, p, inland, "tidal_mill", build_mode="self_contract")
    assert not r["ok"], r
    assert "coastal" in r["reason"].lower() or "terrain" in r["reason"].lower()


def test_tidal_power_requires_no_coal() -> None:
    """``tidal_power`` recipe runs on a tidal_mill with no coal inventory."""
    w, p = _build_test_world(width=10, height=10)
    coastal = PlotId("p-3-8")
    w.plots[coastal].owner = p
    # Plant a completed tidal_mill on the coastal plot.
    w.next_building_instance_seq += 1
    iid = f"b{w.next_building_instance_seq:06d}"
    w.plot_buildings.append(
        {
            "instance_id": iid,
            "condition_bps": 10_000,
            "plot_id": str(coastal),
            "party": str(p),
            "building_id": "tidal_mill",
            "label": "tidal_mill",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    w.building_maintenance[iid] = {
        "due_at_tick": int(w.tick) + 7_200,
        "missed_cycles": 0,
        "efficiency_pct": 100,
    }
    # No coal seeded — recipe must still succeed.
    assert w.inventory.qty(p, MaterialId("coal")) == 0
    r = start_production(w, p, coastal, "tidal_power")
    assert r["ok"], r
    # Coal stays at zero throughout the run.
    for _ in range(int(r["ticks_remaining"]) + 1):
        w.tick += 1
        tick_production(w)
    assert w.inventory.qty(p, MaterialId("coal")) == 0
    assert w.inventory.qty(p, MaterialId("electricity")) >= 1
