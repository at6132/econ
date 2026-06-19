"""Market feed headlines and company equity offerings."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.corporations.company import Company, company_cash_account, store_company
from realm.corporations.equity_offering import accept_equity_offering, schedule_company_ipo
from realm.corporations.formation import _form_company
from realm.economy.market_feed import maybe_feed_resting_bid, maybe_feed_resting_ask
from realm.economy.markets import place_buy_order, place_sell_order
from realm.infrastructure.plot_logistics import add_party_plot_stock
from realm.world import bootstrap_genesis


def test_resting_orders_emit_world_feed() -> None:
    from realm.actions import claim_plot, survey_plot

    w = bootstrap_genesis(seed=3, settler_count=4, grid_width=16, grid_height=12)
    buyer = PartyId("genesis_storekeeper")
    seller = next(p for p in sorted(w.parties, key=str) if str(p).startswith("settler_"))
    pid = next(
        p.plot_id
        for p in w.plots.values()
        if p.owner is None and str(p.terrain.value) not in ("water_deep", "water_shallow")
    )
    assert claim_plot(w, seller, pid)["ok"]
    assert survey_plot(w, seller, pid)["ok"]
    add_party_plot_stock(w, seller, MaterialId("coal"), 20, preferred_plot=pid)
    before = len(w.world_feed_log)
    place_buy_order(w, buyer, MaterialId("coal"), 12, 95)
    place_sell_order(w, seller, MaterialId("coal"), 12, 90, from_plot_id=pid)
    assert len(w.world_feed_log) > before
    kinds = {str(e.get("feed_source", "")) for e in w.world_feed_log}
    assert "market_bid" in kinds or "market_ask" in kinds


def test_company_formation_schedules_ipo() -> None:
    w = bootstrap_genesis(seed=5, settler_count=6, grid_width=18, grid_height=14)
    a = PartyId("settler_001")
    b = PartyId("settler_002")
    for party in (a, b):
        acct = party_cash_account(party)
        w.ledger.ensure_account(acct)
        tr = w.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=800_000)
        assert tr.ok, getattr(tr, "reason", tr)
    company = _form_company(w, a, b)
    feed = [e for e in w.world_feed_log if str(e.get("feed_source", "")) == "equity_ipo"]
    assert feed, "IPO should hit world feed"
    from realm.corporations.equity_offering import list_open_equity_offerings

    open_rows = list_open_equity_offerings(w)
    assert open_rows
    assert open_rows[0]["company_id"] == company.company_id


def test_player_can_buy_ipo_shares() -> None:
    w = bootstrap_genesis(seed=9, settler_count=4, grid_width=14, grid_height=12)
    company = Company(
        company_id="co_test",
        name="Test Mining Co.",
        founded_tick=0,
        founding_party="settler_001",
        share_registry={"settler_001": 1000},
        total_shares=1000,
        managed_plots=[],
        cash_account=str(company_cash_account("co_test")),
        hq_plot_id=None,
        era_unlocked="industrial",
    )
    w.ledger.ensure_account(company_cash_account("co_test"))
    store_company(w, company)
    scheduled = schedule_company_ipo(w, company, PartyId("settler_001"))
    assert scheduled.get("ok")
    player = PartyId("player")
    acct = party_cash_account(player)
    w.ledger.ensure_account(acct)
    tr = w.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=500_000)
    assert tr.ok, getattr(tr, "reason", tr)
    oid = str(scheduled["offering_id"])
    res = accept_equity_offering(w, player, oid, 40)
    assert res.get("ok"), res
    from realm.corporations.company import get_company

    co = get_company(w, "co_test")
    assert co is not None
    assert int(co.share_registry.get("player", 0)) == 40
