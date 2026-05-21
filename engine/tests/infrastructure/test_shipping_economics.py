"""Bulk shipping economics — trip amortization, congestion, conservation."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.core.conservation import (
    ConservationSnapshot,
    assert_money_conserved,
)
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.infrastructure.movement import (
    UNCHARTED_TRIP_MULTIPLIER,
    compute_shipping_fee,
    dispatch_shipment,
)
from realm.infrastructure.route_operators import ROUTE_DAILY_CAPACITY, register_route
from realm.world import bootstrap_genesis
from realm.world.geo import manhattan
from realm.world.regions import region_for_plot, route_key


def test_bulk_shipping_cheaper_per_unit() -> None:
    w = bootstrap_genesis(seed=1, settler_count=5)
    land = [
        pid
        for pid, p in w.plots.items()
        if "water" not in str(p.terrain).lower()
    ]
    pid1, pid2 = PlotId(land[0]), PlotId(land[10])
    fee_1 = compute_shipping_fee(w, pid1, pid2, qty=1)
    fee_100 = compute_shipping_fee(w, pid1, pid2, qty=100)
    assert fee_1["ok"] and fee_100["ok"]
    assert fee_100["per_unit_cents"] < fee_1["per_unit_cents"], (
        "Shipping 100 units should be cheaper per unit than shipping 1"
    )


def test_bulk_coal_is_profitable_to_ship() -> None:
    """100 coal at ~50 tiles should beat 83¢/unit market reference."""
    w = bootstrap_genesis(seed=2, settler_count=5)
    land = [
        pid
        for pid, p in w.plots.items()
        if "water" not in str(p.terrain).lower()
    ]
    for i in range(len(land)):
        for j in range(i + 1, len(land)):
            p1, p2 = w.plots[land[i]], w.plots[land[j]]
            dist = abs(p1.x - p2.x) + abs(p1.y - p2.y)
            if 45 <= dist <= 55:
                fee = compute_shipping_fee(w, PlotId(land[i]), PlotId(land[j]), qty=100)
                assert fee["ok"]
                coal_value = 83
                assert fee["per_unit_cents"] < coal_value, (
                    f"Shipping 100 coal 50 tiles should be profitable: "
                    f"{fee['per_unit_cents']}c vs {coal_value}c coal"
                )
                return
    import pytest

    pytest.skip("No plots ~50 tiles apart found")


def test_shipping_conservation() -> None:
    w = bootstrap_genesis(seed=3, settler_count=5)
    player = PartyId("player")
    land = [
        pid
        for pid, p in w.plots.items()
        if p.owner is None and "water" not in str(p.terrain).lower()
    ][:2]
    if len(land) < 2:
        import pytest

        pytest.skip("need two land plots")
    a, b = PlotId(land[0]), PlotId(land[1])
    assert claim_plot(w, player, a)["ok"]
    assert claim_plot(w, player, b)["ok"]
    w.inventory.add(player, MaterialId("coal"), 20)
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(player),
        amount_cents=500_000,
    )
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    r = dispatch_shipment(w, player, MaterialId("coal"), 10, a, b)
    assert r["ok"], r
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def _add_waystation(world, party: PartyId, plot_id: PlotId) -> None:
    world.next_building_instance_seq += 1
    world.plot_buildings.append(
        {
            "instance_id": f"b-{world.next_building_instance_seq}",
            "condition_bps": 10_000,
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": "waystation",
            "label": "ws",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )


def test_route_congestion_surcharge() -> None:
    w = bootstrap_genesis(seed=4, settler_count=6, grid_width=24, grid_height=18)
    player = PartyId("player")
    plots = [
        pid
        for pid, p in w.plots.items()
        if p.owner is None and "water" not in str(p.terrain).lower()
    ]
    a, b = PlotId(plots[0]), PlotId(plots[1])
    assert claim_plot(w, player, a)["ok"]
    assert claim_plot(w, player, b)["ok"]
    ra = region_for_plot(w, a)
    rb = region_for_plot(w, b)
    assert ra and rb and ra != rb
    rk = route_key(ra, rb)
    _add_waystation(w, player, a)
    reg = register_route(w, player, a, ra, rb, 5)
    assert reg["ok"], reg
    w.inventory.add(player, MaterialId("grain"), ROUTE_DAILY_CAPACITY + 10)
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(player),
        amount_cents=2_000_000,
    )
    base = compute_shipping_fee(w, a, b, qty=1)
    assert base["ok"]
    vol = w.scenario_state.setdefault("route_daily_volume", {})
    vol[rk] = {
        "daily_capacity": ROUTE_DAILY_CAPACITY,
        "units_shipped_today": ROUTE_DAILY_CAPACITY,
    }
    w.inventory.add(player, MaterialId("grain"), 1)
    r = dispatch_shipment(w, player, MaterialId("grain"), 1, a, b)
    assert r["ok"], r
    assert int(r["fee_cents"]) == int(int(base["total_fee_cents"]) * 1.5)


def test_uncharted_route_costs_double() -> None:
    w = bootstrap_genesis(seed=5, settler_count=6, grid_width=24, grid_height=18)
    w.scenario_state["route_operators"] = {}
    player = PartyId("player")
    plots = [
        pid
        for pid, p in w.plots.items()
        if p.owner is None and "water" not in str(p.terrain).lower()
    ]
    a, b = PlotId(plots[0]), PlotId(plots[1])
    assert claim_plot(w, player, a)["ok"]
    assert claim_plot(w, player, b)["ok"]
    ra = region_for_plot(w, a)
    rb = region_for_plot(w, b)
    if not ra or not rb or ra == rb:
        import pytest

        pytest.skip("need distinct regions")
    uncharted = compute_shipping_fee(w, a, b, qty=10)
    assert uncharted.get("is_uncharted")
    from realm.infrastructure.movement import PER_TILE_TRIP_FEE_CENTS

    reg = register_route(w, player, a, ra, rb, PER_TILE_TRIP_FEE_CENTS)
    assert reg["ok"], reg
    charted = compute_shipping_fee(w, a, b, qty=10)
    assert not charted.get("is_uncharted")
    assert uncharted["trip_cost_cents"] >= int(
        charted["trip_cost_cents"] * UNCHARTED_TRIP_MULTIPLIER * 0.95
    )
