"""Movement: shipping fee formula (base + per-tile)."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.world.geo import manhattan
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.infrastructure.movement import BASE_SHIP_FEE_CENTS, PER_TILE_SHIP_CENTS, dispatch_shipment
from realm.world import bootstrap_frontier


def test_dispatch_fee_matches_distance_formula() -> None:
    w = bootstrap_frontier(seed=70, grid_width=4, grid_height=2)
    a, b = PlotId("p-0-0"), PlotId("p-3-0")
    p = PartyId("player")
    assert claim_plot(w, p, a)["ok"] is True
    assert claim_plot(w, p, b)["ok"] is True
    dist = manhattan(w, a, b)
    assert dist == 3
    expected = BASE_SHIP_FEE_CENTS + dist * PER_TILE_SHIP_CENTS
    r = dispatch_shipment(w, p, MaterialId("timber"), 1, a, b)
    assert r["ok"] is True
    assert r["fee_cents"] == expected
    assert len(w.in_transit) == 1
    assert w.in_transit[0].from_plot_id == a
    assert w.in_transit[0].dest_plot_id == b
