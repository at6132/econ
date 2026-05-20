"""Market microstructure: oracle margins, order expiry, FIFO, laborer spending, bank CPI."""

from __future__ import annotations

from realm.agents.market_oracle import _build_oracle
from realm.core.conservation import (
    ConservationSnapshot,
    assert_money_conserved,
)
from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.economy.markets import cancel_sell_order, market_buy, place_sell_order, tick_order_expiry
from realm.genesis.bank import _cpi_rate_adjustment_bps
from realm.population.laborers import laborer_cash_account
from realm.population.stores import SPENDING_TRIGGER_NEED, tick_laborer_spending
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick


def test_oracle_has_positive_margins_at_day_0() -> None:
    w = bootstrap_genesis(seed=42, settler_count=5)
    oracle = _build_oracle(w, 0)
    positive = sum(1 for m in oracle.recipe_margins.values() if m > -0.5)
    total = len(oracle.recipe_margins)
    assert total > 0
    assert positive / total > 0.5, f"Only {positive}/{total} recipes look viable"


def test_order_expiry_removes_stale_orders() -> None:
    w = bootstrap_genesis(seed=1, settler_count=2)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    place_sell_order(w, PartyId("player"), MaterialId("coal"), qty=5, price_per_unit_cents=100)
    for _ in range(31 * 1440):
        advance_tick(w)
    player_orders = [
        a
        for asks in w.market_asks_by_material.values()
        for a in asks
        if a.party == PartyId("player")
    ]
    assert len(player_orders) == 0
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_order_expiry_runs_on_day_boundary() -> None:
    w = bootstrap_genesis(seed=11, settler_count=2)
    place_sell_order(w, PartyId("player"), MaterialId("coal"), qty=1, price_per_unit_cents=50)
    w.tick = 43_200
    tick_order_expiry(w)
    player_orders = [
        a
        for asks in w.market_asks_by_material.values()
        for a in asks
        if a.party == PartyId("player")
    ]
    assert len(player_orders) == 0


def test_fifo_fills_earlier_order_first() -> None:
    from realm.economy.markets import _asks
    from realm.world import bootstrap_frontier

    w = bootstrap_frontier(seed=202, grid_width=2, grid_height=2)
    seller1, seller2, buyer = PartyId("player"), PartyId("t1_consumer"), PartyId("t1_timber_merchant")
    mid = MaterialId("timber")
    for o in list(_asks(w, mid)):
        cancel_sell_order(w, o.party, o.order_id)
    for party in (seller1, seller2, buyer):
        ad = w.inventory.add(party, mid, 5)
        assert not isinstance(ad, MatterErr)
    w.tick = 0
    r1 = place_sell_order(w, seller1, mid, qty=2, price_per_unit_cents=80)
    assert r1["ok"] is True
    oid1 = str(r1["order_id"])
    w.tick = 1
    r2 = place_sell_order(w, seller2, mid, qty=2, price_per_unit_cents=80)
    assert r2["ok"] is True
    oid2 = str(r2["order_id"])

    def _clip_qty(oid: str) -> int:
        for o in _asks(w, mid):
            if o.order_id == oid:
                return int(o.qty)
        return 0

    q1_before = _clip_qty(oid1)
    q2_before = _clip_qty(oid2)
    w.ledger.ensure_account(party_cash_account(buyer))
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(buyer),
        amount_cents=10_000,
    )
    assert market_buy(w, buyer, mid, max_qty=1)["ok"] is True
    assert _clip_qty(oid1) < q1_before
    assert _clip_qty(oid2) == q2_before


def test_laborer_buys_at_high_need_level() -> None:
    w = bootstrap_genesis(seed=3, settler_count=5)
    lab = next(iter(w.laborers.values()))
    lid = lab.laborer_id
    w.ledger.ensure_account(laborer_cash_account(lid))
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=laborer_cash_account(lid),
        amount_cents=50_000,
    )
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    lab.needs["food"] = 0.92
    food_before = float(lab.needs["food"])
    assert food_before < SPENDING_TRIGGER_NEED
    for _ in range(1440):
        advance_tick(w)
    assert float(lab.needs["food"]) > food_before
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_bank_rate_rises_with_inflation() -> None:
    w = bootstrap_genesis(seed=4, settler_count=5)
    w.scenario_state["cpi_current"] = 108.0
    w.scenario_state["cpi_history"] = [
        {"cpi": 100.0, "tick": 0},
        {"cpi": 108.0, "tick": 10080},
    ]
    adj = _cpi_rate_adjustment_bps(w)
    assert adj > 0, "High inflation should raise bank rates"
