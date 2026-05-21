"""Market ask/bid/cancel conservation and access control."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import market_escrow_account, party_cash_account
from realm.economy.markets import (
    cancel_buy_order,
    cancel_sell_order,
    market_buy,
    p2p_trade,
    place_buy_order,
    place_sell_order,
    sell_into_bids,
)
from realm.world import bootstrap_frontier


def test_cancel_sell_order_restores_inventory() -> None:
    w = bootstrap_frontier(seed=20, grid_width=2, grid_height=2)
    p = PartyId("player")
    m = MaterialId("electricity")
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
    m = MaterialId("electricity")
    pr = place_sell_order(w, p, m, 1, 50)
    assert pr["ok"] is True
    oid = pr["order_id"]
    cr = cancel_sell_order(w, PartyId("npc_grain_vendor"), oid)
    assert cr["ok"] is False


def test_cancel_unknown_order() -> None:
    w = bootstrap_frontier(seed=22, grid_width=2, grid_height=2)
    cr = cancel_sell_order(w, PartyId("player"), "ord-nope")
    assert cr["ok"] is False


def test_place_bid_locks_escrow_cancel_refunds() -> None:
    w = bootstrap_frontier(seed=30, grid_width=2, grid_height=2)
    buyer = PartyId("t1_consumer")
    bc = party_cash_account(buyer)
    esc = market_escrow_account()
    cash_before = w.ledger.balance(bc)
    escrow_before = w.ledger.balance(esc)
    # No electricity asks in Frontier bootstrap — bid stays on book.
    pr = place_buy_order(w, buyer, MaterialId("electricity"), 2, 100)
    assert pr["ok"] is True
    oid = pr["order_id"]
    assert w.ledger.balance(bc) == cash_before - 200
    assert w.ledger.balance(esc) == escrow_before + 200
    cr = cancel_buy_order(w, buyer, oid)
    assert cr["ok"] is True
    assert w.ledger.balance(bc) == cash_before
    assert w.ledger.balance(esc) == escrow_before


def test_incoming_bid_crosses_resting_ask_conserves_money() -> None:
    w = bootstrap_frontier(seed=31, grid_width=2, grid_height=2)
    buyer = PartyId("t1_consumer")
    before_grain = w.inventory.qty(buyer, MaterialId("grain"))
    t0 = w.ledger.total_cents()
    pr = place_buy_order(w, buyer, MaterialId("grain"), 2, 200)
    assert pr["ok"] is True
    assert w.ledger.total_cents() == t0
    assert w.inventory.qty(buyer, MaterialId("grain")) == before_grain + 2


def test_incoming_ask_crosses_resting_bid() -> None:
    w = bootstrap_frontier(seed=32, grid_width=2, grid_height=2)
    buyer = PartyId("t1_consumer")
    assert place_buy_order(w, buyer, MaterialId("electricity"), 2, 80)["ok"] is True
    player = PartyId("player")
    elec_before = w.inventory.qty(player, MaterialId("electricity"))
    t0 = w.ledger.total_cents()
    pr = place_sell_order(w, player, MaterialId("electricity"), 2, 50)
    assert pr["ok"] is True
    assert w.ledger.total_cents() == t0
    assert w.inventory.qty(player, MaterialId("electricity")) == elec_before - 2
    assert w.inventory.qty(buyer, MaterialId("electricity")) >= 2


def test_sell_into_bids_moves_inventory_and_conserves() -> None:
    w = bootstrap_frontier(seed=33, grid_width=2, grid_height=2)
    buyer = PartyId("t1_lumber_buyer")
    assert place_buy_order(w, buyer, MaterialId("electricity"), 1, 500)["ok"] is True
    player = PartyId("player")
    before_e = w.inventory.qty(player, MaterialId("electricity"))
    t0 = w.ledger.total_cents()
    r = sell_into_bids(w, player, MaterialId("electricity"), 1)
    assert r["ok"] is True
    assert w.ledger.total_cents() == t0
    assert w.inventory.qty(player, MaterialId("electricity")) == before_e - 1


def test_p2p_idempotent_replay_does_not_double_settle() -> None:
    w = bootstrap_frontier(seed=93, grid_width=2, grid_height=2)
    buyer = PartyId("t1_consumer")
    before = w.inventory.qty(buyer, MaterialId("grain"))
    r1 = p2p_trade(
        w,
        PartyId("player"),
        buyer,
        MaterialId("grain"),
        1,
        50,
        idempotency_key="idem-a",
    )
    assert r1["ok"] is True
    mid = before + 1
    assert w.inventory.qty(buyer, MaterialId("grain")) == mid
    r2 = p2p_trade(
        w,
        PartyId("player"),
        buyer,
        MaterialId("grain"),
        1,
        50,
        idempotency_key="idem-a",
    )
    assert r2.get("idempotent_replay") is True
    assert w.inventory.qty(buyer, MaterialId("grain")) == mid


def test_p2p_idempotency_mismatch() -> None:
    w = bootstrap_frontier(seed=94, grid_width=2, grid_height=2)
    assert p2p_trade(
        w,
        PartyId("player"),
        PartyId("t1_consumer"),
        MaterialId("electricity"),
        1,
        50,
        idempotency_key="idem-b",
    )["ok"] is True
    r = p2p_trade(
        w,
        PartyId("player"),
        PartyId("t1_consumer"),
        MaterialId("electricity"),
        2,
        50,
        idempotency_key="idem-b",
    )
    assert r["ok"] is False
    assert r.get("code") == "P2P_IDEMPOTENCY_MISMATCH"


def test_aggressive_buy_increments_honored_for_buyer_and_seller() -> None:
    w = bootstrap_frontier(seed=88, grid_width=2, grid_height=2)
    buyer = PartyId("t1_consumer")
    seller = PartyId("npc_grain_vendor")
    hb0 = w.reputation[str(buyer)]["honored"]
    hs0 = w.reputation[str(seller)]["honored"]
    r = market_buy(w, buyer, MaterialId("grain"), 1)
    assert r.get("ok") is True
    assert w.reputation[str(buyer)]["honored"] == hb0 + 1
    assert w.reputation[str(seller)]["honored"] == hs0 + 1
    ev = next(e for e in reversed(w.event_log) if e.get("kind") == "market_buy")
    assert ev.get("seller") == str(seller)
    assert str(seller) in (ev.get("sellers") or "")
