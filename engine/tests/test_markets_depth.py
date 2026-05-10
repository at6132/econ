"""Iceberg orders and reputation-gated matching."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.markets import market_buy, place_buy_order, place_sell_order
from realm.tick import advance_tick
from realm.world import bootstrap_frontier


def test_iceberg_ask_refills_visible_clip() -> None:
    w = bootstrap_frontier(seed=100, grid_width=2, grid_height=2)
    p = PartyId("player")
    key = str(MaterialId("timber"))
    before_inv = w.inventory.qty(p, MaterialId("timber"))
    pr = place_sell_order(w, p, MaterialId("timber"), 6, 1, iceberg_display_qty=2)
    assert pr["ok"] is True
    oid = pr["order_id"]
    assert w.inventory.qty(p, MaterialId("timber")) == before_inv - 6
    a = next(x for x in w.market_asks_by_material[key] if x.order_id == oid)
    assert a.qty == 2 and a.iceberg_hidden_qty == 4
    assert market_buy(w, PartyId("t1_consumer"), MaterialId("timber"), 2)["ok"] is True
    a = next(x for x in w.market_asks_by_material[key] if x.order_id == oid)
    assert a.qty == 2 and a.iceberg_hidden_qty == 2
    assert market_buy(w, PartyId("t1_consumer"), MaterialId("timber"), 4)["ok"] is True
    assert not any(x.order_id == oid for x in w.market_asks_by_material.get(key, []))


def test_min_counterparty_honored_blocks_cross_until_rep() -> None:
    w = bootstrap_frontier(seed=101, grid_width=2, grid_height=2)
    player = PartyId("player")
    consumer = PartyId("t1_consumer")
    pr = place_sell_order(w, player, MaterialId("electricity"), 2, 100, min_counterparty_honored=99)
    assert pr["ok"] is True
    oid = pr["order_id"]
    key = str(MaterialId("electricity"))
    assert place_buy_order(w, consumer, MaterialId("electricity"), 1, 200)["ok"] is True
    assert any(x.order_id == oid for x in w.market_asks_by_material[key])
    w.reputation[str(consumer)] = {"honored": 100, "breached": 0}
    assert market_buy(w, consumer, MaterialId("electricity"), 2)["ok"] is True
    assert not any(x.order_id == oid for x in w.market_asks_by_material.get(key, []))


def test_aggressive_buy_respects_min_seller_honored() -> None:
    w = bootstrap_frontier(seed=102, grid_width=2, grid_height=2)
    assert place_sell_order(w, PartyId("player"), MaterialId("grain"), 1, 5)["ok"] is True
    r = market_buy(w, PartyId("t1_consumer"), MaterialId("grain"), 1, min_seller_honored=999)
    assert r["ok"] is False
