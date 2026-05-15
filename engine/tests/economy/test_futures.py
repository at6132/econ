"""Futures market: escrow, matching, settlement, defaults, curve feed."""

from __future__ import annotations

from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import futures_escrow_account, party_cash_account
from realm.economy import futures as fut
from realm.world import bootstrap_frontier


def test_post_futures_sell_escrows_deposit() -> None:
    w = bootstrap_frontier(seed=1101, grid_width=3, grid_height=3)
    a = PartyId("player")
    esc = futures_escrow_account()
    w.ledger.ensure_account(esc)
    before_esc = w.ledger.balance(esc)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    r = fut.post_futures_order(
        w, a, "sell", MaterialId("coal"), 10, 100, int(w.tick) + 5_000
    )
    assert r["ok"] is True
    dep = int(r["deposit_cents"])
    assert w.ledger.balance(esc) == before_esc + dep
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_futures_matching_on_crossing_prices() -> None:
    w = bootstrap_frontier(seed=1102, grid_width=3, grid_height=3)
    alice = PartyId("player")
    bob = PartyId("t1_consumer")
    dt = int(w.tick) + 10_000
    assert fut.post_futures_order(w, alice, "sell", MaterialId("coal"), 5, 70, dt)["ok"]
    assert fut.post_futures_order(w, bob, "buy", MaterialId("coal"), 5, 75, dt)["ok"]
    fut.tick_futures_matching(w)
    sell = next(o for o in w.futures_orders if o.side == "sell")
    buy = next(o for o in w.futures_orders if o.side == "buy")
    assert sell.status == "matched" and buy.status == "matched"
    assert int(sell.match_price_cents or 0) == 72


def test_futures_settlement_delivers_goods() -> None:
    w = bootstrap_frontier(seed=1103, grid_width=3, grid_height=3)
    alice = PartyId("player")
    bob = PartyId("t1_consumer")
    dt = int(w.tick) + 1
    assert fut.post_futures_order(w, alice, "sell", MaterialId("coal"), 3, 50, dt)["ok"]
    assert fut.post_futures_order(w, bob, "buy", MaterialId("coal"), 3, 60, dt)["ok"]
    fut.tick_futures_matching(w)
    w.inventory.add(alice, MaterialId("coal"), 10)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    w.tick = dt
    fut.tick_futures_settlement(w)
    assert w.inventory.qty(bob, MaterialId("coal")) >= 3
    assert_money_conserved(w.ledger, snap.ledger_total_cents)
    assert (
        ConservationSnapshot.of(w.ledger, w.inventory).inventory_total_units
        == snap.inventory_total_units
    )


def test_futures_default_loses_deposit() -> None:
    w = bootstrap_frontier(seed=1104, grid_width=3, grid_height=3)
    alice = PartyId("t1_consumer")
    bob = PartyId("player")
    dt = int(w.tick) + 1
    assert fut.post_futures_order(w, alice, "sell", MaterialId("coal"), 2, 40, dt)["ok"]
    assert fut.post_futures_order(w, bob, "buy", MaterialId("coal"), 2, 50, dt)["ok"]
    fut.tick_futures_matching(w)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    bob_cash_before = w.ledger.balance(party_cash_account(bob))
    w.tick = dt
    fut.tick_futures_settlement(w)
    sell = next(o for o in w.futures_orders if o.side == "sell")
    buy = next(o for o in w.futures_orders if o.side == "buy")
    assert sell.status == "defaulted" and buy.status == "defaulted"
    assert_money_conserved(w.ledger, snap.ledger_total_cents)
    assert w.ledger.balance(party_cash_account(bob)) > bob_cash_before


def test_futures_price_curve_feed_entry() -> None:
    w = bootstrap_frontier(seed=1105, grid_width=3, grid_height=3)
    from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account

    sellers = (PartyId("player"), PartyId("t1_consumer"), PartyId("t1_timber_merchant"))
    buyers = (PartyId("t1_lumber_buyer"), PartyId("t1_coal_vendor"), PartyId("t1_clay_vendor"))
    for pid in sellers + buyers:
        w.ledger.ensure_account(party_cash_account(pid))
        tr = w.ledger.transfer(
            debit=system_reserve_account(),
            credit=party_cash_account(pid),
            amount_cents=200_000,
        )
        assert not isinstance(tr, MoneyErr), tr
    base = int(w.tick)
    for i in range(3):
        dt = base + 2_000 + i * 700
        assert fut.post_futures_order(
            w, sellers[i], "sell", MaterialId("coal"), 2, 70, dt
        )["ok"]
        assert fut.post_futures_order(
            w, buyers[i], "buy", MaterialId("coal"), 2, 80, dt
        )["ok"]
    pre = len(w.event_log)
    fut.tick_futures_matching(w)
    new = [e for e in w.event_log[pre:] if e.get("feed_source") == "futures_curve"]
    assert new, "expected futures curve world_feed"
