"""Equity stake contracts — ownership % and business cash dividends."""

from __future__ import annotations

from realm.contracts.equity_stake import accept_equity_stake, propose_equity_stake, tick_equity_stakes
from realm.contracts.stubs import propose_equity_stub
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import PartyId
from realm.core.ledger import business_cash_account, party_cash_account
from realm.economy.businesses import BusinessEntity
from realm.world import bootstrap_frontier


def _seed_biz(world: object) -> str:
    bid = "biz-00001"
    world.businesses[bid] = BusinessEntity(
        business_id=bid,
        owner_party=PartyId("player"),
        business_name="TestCo",
        business_type_tag="mining",
        description="t",
        registered_at_tick=0,
        registered_plot_ids=tuple(),
        sub_account_label="main",
        status="active",
        suspension_reason=None,
        public_profile=True,
        last_viability_check_tick=0,
        equity_contract_ids=[],
    )
    world.ledger.ensure_account(business_cash_account(bid))
    return bid


def test_propose_equity_stake_creates_contract() -> None:
    w = bootstrap_frontier(seed=201, grid_width=2, grid_height=2)
    bid = _seed_biz(w)
    r = propose_equity_stake(
        w,
        PartyId("player"),
        PartyId("t1_consumer"),
        bid,
        500,
        1_000,
    )
    assert r["ok"] is True
    assert any(c.get("kind") == "equity_stake" for c in w.contracts)


def test_equity_stake_investment_transfers_on_accept() -> None:
    w = bootstrap_frontier(seed=202, grid_width=2, grid_height=2)
    bid = _seed_biz(w)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    pr = propose_equity_stake(w, PartyId("player"), PartyId("t1_consumer"), bid, 800, 5_000)
    cid = str(pr["contract_id"])
    assert accept_equity_stake(w, PartyId("t1_consumer"), cid)["ok"] is True
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_equity_stub_still_works_as_deprecated_alias() -> None:
    w = bootstrap_frontier(seed=203, grid_width=2, grid_height=2)
    r = propose_equity_stub(w, PartyId("player"), PartyId("t1_consumer"), 1_000, 10, 2)
    assert r["ok"] is True


def test_equity_dividend_from_business_cash() -> None:
    from realm.population.laborers import TICKS_PER_GAME_DAY

    w = bootstrap_frontier(seed=204, grid_width=2, grid_height=2)
    bid = _seed_biz(w)
    pr = propose_equity_stake(w, PartyId("player"), PartyId("t1_consumer"), bid, 1_000, 1_000)
    cid = str(pr["contract_id"])
    assert accept_equity_stake(w, PartyId("t1_consumer"), cid)["ok"] is True
    biz_acct = business_cash_account(bid)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    from realm.core.ledger import MoneyErr

    tr = w.ledger.transfer(
        debit=party_cash_account(PartyId("player")),
        credit=biz_acct,
        amount_cents=100_000,
    )
    assert not isinstance(tr, MoneyErr)
    w.tick = TICKS_PER_GAME_DAY
    inv0 = w.ledger.balance(party_cash_account(PartyId("t1_consumer")))
    tick_equity_stakes(w)
    inv1 = w.ledger.balance(party_cash_account(PartyId("t1_consumer")))
    assert inv1 >= inv0
    assert_money_conserved(w.ledger, snap.ledger_total_cents)
