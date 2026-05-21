"""Movement: bulk shipping fee formula (trip cost amortized per unit)."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.infrastructure.movement import compute_shipping_fee, dispatch_shipment
from realm.infrastructure.roads import compute_road_savings_and_tolls
from realm.economy.markets import best_resting_ask_cents, best_resting_bid_cents
from realm.infrastructure.movement import BASE_TRIP_FEE_CENTS, PER_TILE_TRIP_FEE_CENTS
from realm.world import bootstrap_frontier


def test_dispatch_fee_matches_bulk_formula() -> None:
    w = bootstrap_frontier(seed=70, grid_width=4, grid_height=2)
    a, b = PlotId("p-0-0"), PlotId("p-3-0")
    p = PartyId("player")
    assert claim_plot(w, p, a)["ok"] is True
    assert claim_plot(w, p, b)["ok"] is True
    fee_info = compute_shipping_fee(w, a, b, qty=1)
    assert fee_info["ok"]
    unit_value = best_resting_ask_cents(w, MaterialId("timber")) or 100
    road_calc = compute_road_savings_and_tolls(
        w,
        from_plot_id=a,
        to_plot_id=b,
        per_tile_cents=PER_TILE_TRIP_FEE_CENTS,
        goods_value_cents=int(unit_value),
        shipper=p,
    )
    expected = max(
        BASE_TRIP_FEE_CENTS,
        int(fee_info["total_fee_cents"]) - int(road_calc["savings_cents"]),
    )
    r = dispatch_shipment(w, p, MaterialId("timber"), 1, a, b)
    assert r["ok"] is True
    assert r["fee_cents"] == expected
    assert len(w.in_transit) == 1
    assert w.in_transit[0].from_plot_id == a
    assert w.in_transit[0].dest_plot_id == b
