"""Market ask/cancel conservation and access control."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.markets import cancel_sell_order, place_sell_order
from realm.world import bootstrap_frontier


def test_cancel_sell_order_restores_inventory() -> None:
    w = bootstrap_frontier(seed=20, grid_width=2, grid_height=2)
    p = PartyId("player")
    m = MaterialId("timber")
    before = w.inventory.qty(p, m)
    pr = place_sell_order(w, p, m, 3, 100)
    assert pr["ok"] is True
    oid = pr["order_id"]
    assert isinstance(oid, str)
    assert w.inventory.qty(p, m) == before - 3
    cr = cancel_sell_order(w, p, oid)
    assert cr["ok"] is True
    assert w.inventory.qty(p, m) == before


def test_cancel_sell_order_wrong_party() -> None:
    w = bootstrap_frontier(seed=21, grid_width=2, grid_height=2)
    p = PartyId("player")
    m = MaterialId("timber")
    pr = place_sell_order(w, p, m, 1, 50)
    oid = pr["order_id"]
    cr = cancel_sell_order(w, PartyId("npc_grain_vendor"), oid)
    assert cr["ok"] is False


def test_cancel_unknown_order() -> None:
    w = bootstrap_frontier(seed=22, grid_width=2, grid_height=2)
    cr = cancel_sell_order(w, PartyId("player"), "ord-nope")
    assert cr["ok"] is False
