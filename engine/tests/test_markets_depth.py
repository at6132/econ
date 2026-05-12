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


def test_market_buy_skips_rep_blocked_cheapest_ask() -> None:
    """Cheapest ask can require rep the buyer lacks; walker must still lift higher-priced asks."""
    from realm.inventory import MatterErr
    from realm.markets import cancel_sell_order
    from realm.world import bootstrap_genesis

    w = bootstrap_genesis(seed=808, grid_width=4, grid_height=4, settler_count=0)
    p = PartyId("player")
    ex = PartyId("genesis_exchange")
    hub = PartyId("pop_hub_e")
    mid = MaterialId("coal")
    key = str(mid)
    for o in list(w.market_asks_by_material.get(key, [])):
        cancel_sell_order(w, o.party, o.order_id)
    ad = w.inventory.add(p, mid, 30)
    assert not isinstance(ad, MatterErr)
    assert place_sell_order(w, p, mid, 10, 50, min_counterparty_honored=5)["ok"] is True
    ad2 = w.inventory.add(ex, mid, 40)
    assert not isinstance(ad2, MatterErr)
    assert place_sell_order(w, ex, mid, 12, 72)["ok"] is True
    assert w.reputation[str(hub)].get("honored", 0) == 0
    r = market_buy(w, hub, mid, 4)
    assert r.get("ok") is True
    assert int(r.get("filled", 0)) == 4
    assert w.inventory.qty(hub, mid) >= 4
