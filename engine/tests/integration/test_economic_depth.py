"""Integration smoke: economic depth systems + ledger conservation."""

from __future__ import annotations

from realm.actions import claim_plot, register_business
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.economy import currencies as cur
from realm.economy import futures as fut
from realm.economy import fx_market as fx
from realm.economy.business_requirements import BANK_MIN_RESERVE_RATIO
from realm.world import bootstrap_genesis
from realm.world.regional_advantage import ADVANTAGE_CATEGORIES, seed_regional_advantages
from realm.world.tick import advance_tick


def test_full_economic_depth_conservation() -> None:
    w = bootstrap_genesis(seed=1501, grid_width=48, grid_height=36, settler_count=8)
    start = w.ledger.total_cents()
    human = PartyId("player")
    pid = next(x for x, pl in w.plots.items() if pl.owner is None)
    assert claim_plot(w, human, PlotId(str(pid)))["ok"] is True
    r = register_business(
        w,
        human,
        "Depth Bank",
        template_id="bank",
        registered_plot_ids=(str(pid),),
    )
    assert r["ok"] is True
    bid = str(r["business_id"])
    cc = cur.create_currency(w, human, bid, "DEP", "Depth Coin", reserve_ratio=0.2)
    if cc.get("ok"):
        cur.mint_currency(w, human, str(cc["currency_id"]), 50)
    fut.post_futures_order(
        w, human, "sell", MaterialId("coal"), 1, 50, int(w.tick) + 5_000
    )
    seed_regional_advantages(w)
    for _ in range(1440):
        advance_tick(w)
    assert w.ledger.total_cents() == start


def test_fx_market_is_live_after_day() -> None:
    w = bootstrap_genesis(seed=1502, grid_width=48, grid_height=36, settler_count=4)
    human = PartyId("player")
    pid = next(x for x, pl in w.plots.items() if pl.owner is None)
    assert claim_plot(w, human, PlotId(str(pid)))["ok"] is True
    rb = register_business(
        w, human, "FX Bank2", template_id="bank", registered_plot_ids=(str(pid),)
    )
    assert rb["ok"] is True
    bid = str(rb["business_id"])
    assert cur.create_currency(w, human, bid, "XXA", "X1", reserve_ratio=0.5)["ok"]
    assert cur.create_currency(w, human, bid, "XXB", "X2", reserve_ratio=0.5)["ok"]
    c1 = f"curr_{bid}_xxa"
    c2 = f"curr_{bid}_xxb"
    cur.mint_currency(w, human, c1, 100)
    cur.mint_currency(w, human, c2, 100)
    m1 = MaterialId(w.issued_currencies[c1].material_id)
    m2 = MaterialId(w.issued_currencies[c2].material_id)
    a = PartyId("settler_001")
    b = PartyId("settler_002")
    w.inventory.transfer(material=m1, qty=80, from_party=human, to_party=a)
    w.inventory.transfer(material=m2, qty=80, from_party=human, to_party=b)
    fx.post_fx_order(w, a, str(m1), 40, str(m2), 20)
    fx.post_fx_order(w, b, str(m2), 20, str(m1), 35)
    for _ in range(1440):
        advance_tick(w)
    assert len(w.fx_orders) >= 1


def test_currency_circulating_when_minted() -> None:
    w = bootstrap_genesis(seed=1503, grid_width=48, grid_height=36, settler_count=4)
    human = PartyId("player")
    pid = next(x for x, pl in w.plots.items() if pl.owner is None)
    assert claim_plot(w, human, PlotId(str(pid)))["ok"] is True
    rb = register_business(
        w, human, "Mint Bank", template_id="bank", registered_plot_ids=(str(pid),)
    )
    assert rb["ok"] is True
    bid = str(rb["business_id"])
    assert cur.create_currency(w, human, bid, "MMC", "M1", reserve_ratio=0.2)["ok"]
    cid = f"curr_{bid}_mmc"
    assert cur.mint_currency(w, human, cid, 100)["ok"]
    c = w.issued_currencies[cid]
    assert c.total_issued > 0 and c.reserve_cents > 0
    ratio = c.reserve_cents / c.total_issued
    assert ratio >= BANK_MIN_RESERVE_RATIO


def test_cpi_and_regional_tracking() -> None:
    w = bootstrap_genesis(seed=1504, grid_width=48, grid_height=36, settler_count=4)
    seed_regional_advantages(w)
    assert len(w.regional_advantages) > 0
    for _lm, adv in w.regional_advantages.items():
        for cat in ADVANTAGE_CATEGORIES:
            assert cat in adv
            assert 0.8 <= adv[cat] <= 1.3
    assert float(w.scenario_state.get("cpi_current", 100.0)) > 0
