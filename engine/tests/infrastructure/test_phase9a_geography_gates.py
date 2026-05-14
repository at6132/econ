"""Phase 9A — geography gates for inter-island shipping.

These tests prove that the inter-island shipment path:

1. Requires a completed dock on the origin plot owned by the shipper.
2. Requires a completed dock on the destination plot (any owner).
3. Requires the shipper to own at least one cargo vessel.
4. Burns coal (preferred) or electricity (fallback) per voyage.
5. Credits the receiving fee to the destination dock owner.

Intra-island shipping is unaffected. The tests use a hand-built world with
two islands so we control the inventory + buildings + ownership exactly.
"""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import (
    Ledger,
    party_cash_account,
    system_reserve_account,
)
from realm.core.inventory import Inventory
from realm.infrastructure.movement import (
    MOVEMENT_FUEL_TILES_PER_UNIT,
    dispatch_shipment,
    deliver_transit,
)
from realm.world import Plot, World
from realm.world.subsurface import SubsurfaceRoll
from realm.world.terrain import Terrain


def _empty_subsurface() -> SubsurfaceRoll:
    return SubsurfaceRoll(
        iron_ore_grade=0.0,
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
        sulfur_grade=0.0,
        saltpeter_grade=0.0,
        tin_grade=0.0,
        lead_grade=0.0,
        phosphate_grade=0.0,
        silica_grade=0.0,
        platinum_grade=0.0,
        oil_shale_grade=0.0,
        rare_earth_grade=0.0,
    )


def _make_plot(plot_id: str, x: int, y: int, terrain: Terrain) -> Plot:
    return Plot(
        plot_id=PlotId(plot_id),
        x=x,
        y=y,
        terrain=terrain,
        owner=None,
        subsurface=_empty_subsurface(),
        surveyed=False,
    )


def _make_two_island_world() -> World:
    """Two land plots on different islands, separated by a strip of water.

    Plot layout (y=0):
      island 0: p-0-0 (plains)  p-1-0 (water_deep)  island 1: p-2-0 (plains)
    """
    p0 = _make_plot("p-0-0", 0, 0, Terrain.PLAINS)
    p_water = _make_plot("p-1-0", 1, 0, Terrain.WATER_DEEP)
    p2 = _make_plot("p-2-0", 2, 0, Terrain.PLAINS)
    shipper = PartyId("shipper_alpha")
    receiver = PartyId("receiver_beta")
    p0.owner = shipper
    p2.owner = receiver
    ledger = Ledger()
    ledger.seed_system_reserve(10_000_000)
    inventory = Inventory()
    world = World(
        seed=42,
        tick=0,
        plots={p0.plot_id: p0, p_water.plot_id: p_water, p2.plot_id: p2},
        ledger=ledger,
        inventory=inventory,
    )
    world.parties.add(shipper)
    world.parties.add(receiver)
    world.scenario_state["plot_islands"] = {
        "p-0-0": 0,
        "p-2-0": 1,
    }
    for party in (shipper, receiver):
        acct = party_cash_account(party)
        ledger.ensure_account(acct)
        ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=500_000,
        )
    inventory.add(shipper, MaterialId("grain"), 100)
    return world


def _add_dock(world: World, plot_id: PlotId, owner: PartyId, *, completes_at_tick: int = 0) -> None:
    world.plot_buildings.append(
        {
            "plot_id": str(plot_id),
            "building_id": "dock",
            "party": str(owner),
            "completes_at_tick": int(completes_at_tick),
        }
    )


# ────────────────────────── geography-gate tests ──────────────────────────


def test_inter_island_dispatch_requires_origin_dock():
    world = _make_two_island_world()
    shipper = PartyId("shipper_alpha")
    receiver = PartyId("receiver_beta")
    # Destination dock only — no origin dock.
    _add_dock(world, PlotId("p-2-0"), receiver)
    world.inventory.add(shipper, MaterialId("vessel"), 1)
    world.inventory.add(shipper, MaterialId("coal"), 5)
    res = dispatch_shipment(
        world, shipper, MaterialId("grain"), 10, PlotId("p-0-0"), PlotId("p-2-0")
    )
    assert not res["ok"]
    assert "dock at the origin" in res["reason"]


def test_inter_island_dispatch_requires_destination_dock():
    world = _make_two_island_world()
    shipper = PartyId("shipper_alpha")
    _add_dock(world, PlotId("p-0-0"), shipper)
    world.inventory.add(shipper, MaterialId("vessel"), 1)
    world.inventory.add(shipper, MaterialId("coal"), 5)
    res = dispatch_shipment(
        world, shipper, MaterialId("grain"), 10, PlotId("p-0-0"), PlotId("p-2-0")
    )
    assert not res["ok"]
    assert "dock at the destination" in res["reason"]


def test_inter_island_dispatch_requires_vessel():
    world = _make_two_island_world()
    shipper = PartyId("shipper_alpha")
    receiver = PartyId("receiver_beta")
    _add_dock(world, PlotId("p-0-0"), shipper)
    _add_dock(world, PlotId("p-2-0"), receiver)
    # No vessel in inventory.
    world.inventory.add(shipper, MaterialId("coal"), 5)
    res = dispatch_shipment(
        world, shipper, MaterialId("grain"), 10, PlotId("p-0-0"), PlotId("p-2-0")
    )
    assert not res["ok"]
    assert "cargo vessel" in res["reason"]


def test_inter_island_dispatch_requires_fuel():
    world = _make_two_island_world()
    shipper = PartyId("shipper_alpha")
    receiver = PartyId("receiver_beta")
    _add_dock(world, PlotId("p-0-0"), shipper)
    _add_dock(world, PlotId("p-2-0"), receiver)
    world.inventory.add(shipper, MaterialId("vessel"), 1)
    # No coal, no electricity.
    res = dispatch_shipment(
        world, shipper, MaterialId("grain"), 10, PlotId("p-0-0"), PlotId("p-2-0")
    )
    assert not res["ok"]
    assert "fuel" in res["reason"].lower()


def test_inter_island_dispatch_succeeds_when_all_gates_pass():
    world = _make_two_island_world()
    shipper = PartyId("shipper_alpha")
    receiver = PartyId("receiver_beta")
    _add_dock(world, PlotId("p-0-0"), shipper)
    _add_dock(world, PlotId("p-2-0"), receiver)
    world.inventory.add(shipper, MaterialId("vessel"), 1)
    world.inventory.add(shipper, MaterialId("coal"), 5)
    res = dispatch_shipment(
        world, shipper, MaterialId("grain"), 10, PlotId("p-0-0"), PlotId("p-2-0")
    )
    assert res["ok"], res
    assert res["inter_island"] is True
    assert res["dest_dock_owner"] == str(receiver)
    assert res["fuel_material"] == "coal"
    assert res["fuel_units"] >= 1


def test_inter_island_fuel_is_consumed_from_inventory():
    world = _make_two_island_world()
    shipper = PartyId("shipper_alpha")
    receiver = PartyId("receiver_beta")
    _add_dock(world, PlotId("p-0-0"), shipper)
    _add_dock(world, PlotId("p-2-0"), receiver)
    world.inventory.add(shipper, MaterialId("vessel"), 1)
    world.inventory.add(shipper, MaterialId("coal"), 10)
    coal_before = world.inventory.qty(shipper, MaterialId("coal"))
    vessel_before = world.inventory.qty(shipper, MaterialId("vessel"))
    res = dispatch_shipment(
        world, shipper, MaterialId("grain"), 10, PlotId("p-0-0"), PlotId("p-2-0")
    )
    assert res["ok"], res
    coal_after = world.inventory.qty(shipper, MaterialId("coal"))
    vessel_after = world.inventory.qty(shipper, MaterialId("vessel"))
    assert coal_after == coal_before - int(res["fuel_units"])
    # Vessel is durable capital, not consumed per voyage (v1 design).
    assert vessel_after == vessel_before


def test_inter_island_falls_back_to_electricity_when_no_coal():
    world = _make_two_island_world()
    shipper = PartyId("shipper_alpha")
    receiver = PartyId("receiver_beta")
    _add_dock(world, PlotId("p-0-0"), shipper)
    _add_dock(world, PlotId("p-2-0"), receiver)
    world.inventory.add(shipper, MaterialId("vessel"), 1)
    world.inventory.add(shipper, MaterialId("electricity"), 10)
    res = dispatch_shipment(
        world, shipper, MaterialId("grain"), 10, PlotId("p-0-0"), PlotId("p-2-0")
    )
    assert res["ok"], res
    assert res["fuel_material"] == "electricity"


def test_intra_island_dispatch_needs_no_dock_no_vessel_no_fuel():
    """Same-island shipping is the door-to-door wagon analog — no infrastructure gate."""
    world = _make_two_island_world()
    # Add a second land plot on island 0.
    p_b = _make_plot("p-0-1", 0, 1, Terrain.PLAINS)
    p_b.owner = PartyId("shipper_alpha")
    world.plots[p_b.plot_id] = p_b
    world.scenario_state["plot_islands"]["p-0-1"] = 0
    shipper = PartyId("shipper_alpha")
    # Bare-bones: no dock, no vessel, no fuel.
    res = dispatch_shipment(
        world, shipper, MaterialId("grain"), 5, PlotId("p-0-0"), PlotId("p-0-1")
    )
    assert res["ok"], res
    assert res["inter_island"] is False
    assert res["dest_dock_owner"] is None
    assert res["fuel_units"] == 0


def test_inter_island_receiving_fee_credits_destination_dock_owner():
    world = _make_two_island_world()
    shipper = PartyId("shipper_alpha")
    receiver = PartyId("receiver_beta")
    _add_dock(world, PlotId("p-0-0"), shipper)
    _add_dock(world, PlotId("p-2-0"), receiver)
    world.inventory.add(shipper, MaterialId("vessel"), 1)
    world.inventory.add(shipper, MaterialId("coal"), 5)
    res = dispatch_shipment(
        world, shipper, MaterialId("grain"), 10, PlotId("p-0-0"), PlotId("p-2-0")
    )
    assert res["ok"], res
    receiver_acct = party_cash_account(receiver)
    receiver_before = world.ledger.balance(receiver_acct)
    reserve_before = world.ledger.balance(system_reserve_account())
    # Advance to arrival and deliver.
    world.tick = int(res["arrive_tick"])
    deliver_transit(world)
    receiver_after = world.ledger.balance(receiver_acct)
    reserve_after = world.ledger.balance(system_reserve_account())
    assert receiver_after > receiver_before, (
        f"dock owner should have been credited the receiving fee; "
        f"before={receiver_before} after={receiver_after}"
    )
    # System reserve doesn't gain anything from inter-island receiving fee.
    assert reserve_after == reserve_before


def test_intra_island_receiving_fee_still_goes_to_system_reserve():
    """Backstop: door-to-door has no port so the fee sinks to the system as before."""
    world = _make_two_island_world()
    p_b = _make_plot("p-0-1", 0, 1, Terrain.PLAINS)
    p_b.owner = PartyId("shipper_alpha")
    world.plots[p_b.plot_id] = p_b
    world.scenario_state["plot_islands"]["p-0-1"] = 0
    shipper = PartyId("shipper_alpha")
    res = dispatch_shipment(
        world, shipper, MaterialId("grain"), 5, PlotId("p-0-0"), PlotId("p-0-1")
    )
    assert res["ok"], res
    reserve_before = world.ledger.balance(system_reserve_account())
    world.tick = int(res["arrive_tick"])
    deliver_transit(world)
    reserve_after = world.ledger.balance(system_reserve_account())
    # Same-island receiving fee continues to sink to system_reserve.
    assert reserve_after >= reserve_before


def test_fuel_units_scale_with_distance():
    world = _make_two_island_world()
    # Move dst plot far away.
    far = _make_plot("p-50-50", 50, 50, Terrain.PLAINS)
    far.owner = PartyId("receiver_beta")
    world.plots[far.plot_id] = far
    world.scenario_state["plot_islands"]["p-50-50"] = 1
    shipper = PartyId("shipper_alpha")
    receiver = PartyId("receiver_beta")
    _add_dock(world, PlotId("p-0-0"), shipper)
    _add_dock(world, far.plot_id, receiver)
    world.inventory.add(shipper, MaterialId("vessel"), 1)
    world.inventory.add(shipper, MaterialId("coal"), 50)
    res = dispatch_shipment(
        world, shipper, MaterialId("grain"), 5, PlotId("p-0-0"), far.plot_id
    )
    assert res["ok"], res
    # Manhattan distance is 100 tiles → at least 100 // FUEL_TILES_PER_UNIT units.
    expected_min = max(1, 100 // MOVEMENT_FUEL_TILES_PER_UNIT)
    assert int(res["fuel_units"]) >= expected_min
