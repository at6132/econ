"""Plot listing reserves, DDP breach penalties, and physical P2P."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.economy.market_delivery import DDP_BREACH_MIN_CENTS, DDP_BREACH_PENALTY_BPS
from realm.economy.market_reserves import plot_available_qty, plot_reserved_qty
from realm.economy.exchange import GENESIS_EXCHANGE_PARTY_ID
from realm.economy.markets import cancel_buy_order, p2p_trade, place_buy_order, place_sell_order
from realm.infrastructure.plot_logistics import plot_output_qty
from realm.production.storage_caps import party_uses_plot_storage
from realm.world import bootstrap_genesis


def _ensure_cash(world, party: PartyId, cents: int) -> None:
    from realm.core.ledger import system_reserve_account

    acc = party_cash_account(party)
    world.ledger.ensure_account(acc)
    world.ledger.transfer(debit=system_reserve_account(), credit=acc, amount_cents=cents)


def _clear_exchange_asks(world, material: MaterialId) -> None:
    key = str(material)
    lst = world.market_asks_by_material.get(key, [])
    world.market_asks_by_material[key] = [
        o for o in lst if o.party != GENESIS_EXCHANGE_PARTY_ID
    ]


def _unowned_plot(world) -> PlotId | None:
    for pid, plot in world.plots.items():
        if plot.owner is None:
            return pid
    return None


def test_listing_reserves_stock_on_plot() -> None:
    w = bootstrap_genesis(seed=40, grid_width=12, grid_height=10, settler_count=1)
    seller = PartyId("player")
    pid = _unowned_plot(w)
    assert pid is not None
    assert claim_plot(w, seller, pid)["ok"]
    w.plot_output_stock.setdefault(str(pid), {})["timber"] = 8
    r = place_sell_order(w, seller, MaterialId("timber"), 5, 40_000, from_plot_id=pid)
    assert r["ok"], r
    assert plot_output_qty(w, pid, MaterialId("timber")) == 8
    assert plot_reserved_qty(w, pid, MaterialId("timber")) == 5
    assert plot_available_qty(w, pid, MaterialId("timber")) == 3


def test_ddp_breach_penalty_no_fob_fallback() -> None:
    w = bootstrap_genesis(seed=41, grid_width=12, grid_height=10, settler_count=2)
    seller = PartyId("player")
    buyer = PartyId("settler_001")
    _ensure_cash(w, seller, 500_000)
    _ensure_cash(w, buyer, 500_000)
    pid = _unowned_plot(w)
    assert pid is not None
    assert claim_plot(w, seller, pid)["ok"]
    buyer_pid = None
    for p_id, plot in w.plots.items():
        if plot.owner is None and p_id != pid:
            buyer_pid = p_id
            break
    assert buyer_pid is not None
    assert claim_plot(w, buyer, buyer_pid)["ok"]
    w.plot_output_stock.setdefault(str(pid), {})["timber"] = 4
    assert place_sell_order(
        w,
        seller,
        MaterialId("timber"),
        4,
        10_000,
        from_plot_id=pid,
        delivery_terms="ddp",
    )["ok"]
    seller_c = party_cash_account(seller)
    buyer_c = party_cash_account(buyer)
    seller_before = w.ledger.balance(seller_c)
    buyer_before = w.ledger.balance(buyer_c)
    from unittest.mock import patch

    _clear_exchange_asks(w, MaterialId("timber"))
    with patch(
        "realm.infrastructure.movement.dispatch_shipment",
        return_value={"ok": False, "reason": "insufficient cash for freight"},
    ):
        br = place_buy_order(
            w,
            buyer,
            MaterialId("timber"),
            4,
            10_001,
            delivery_plot_id=buyer_pid,
        )
    assert br.get("ok"), br
    assert len(w.market_fob_pickups) == 0
    oid = str(br.get("order_id", ""))
    if oid:
        cancel_buy_order(w, buyer, oid)
    payment = 4 * 10_000
    expected_penalty = max(DDP_BREACH_MIN_CENTS, payment * DDP_BREACH_PENALTY_BPS // 10_000)
    assert w.ledger.balance(buyer_c) == buyer_before + expected_penalty
    assert w.ledger.balance(seller_c) == seller_before - expected_penalty


def test_p2p_bulk_spawns_transit() -> None:
    w = bootstrap_genesis(seed=42, grid_width=14, grid_height=12, settler_count=2)
    assert party_uses_plot_storage(w, PartyId("player"))
    seller = PartyId("player")
    buyer = PartyId("settler_001")
    _ensure_cash(w, buyer, 1_000_000)
    pid = _unowned_plot(w)
    assert pid is not None
    assert claim_plot(w, seller, pid)["ok"]
    buyer_pid = None
    for p_id, plot in w.plots.items():
        if plot.owner is None and p_id != pid:
            buyer_pid = p_id
            break
    assert buyer_pid is not None
    assert claim_plot(w, buyer, buyer_pid)["ok"]
    w.plot_output_stock.setdefault(str(pid), {})["timber"] = 3
    before = len(w.in_transit)
    r = p2p_trade(w, seller, buyer, MaterialId("timber"), 2, 20_000)
    assert r["ok"], r
    assert len(w.in_transit) == before + 1
    assert plot_output_qty(w, buyer_pid, MaterialId("timber")) == 0
