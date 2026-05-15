"""CPI basket, weekly tick, and CPI-indexed wages."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.economy.cpi import CPI_BASKET, TICKS_PER_GAME_WEEK, tick_cpi
from realm.economy.markets import cancel_sell_order, place_sell_order
from realm.population.employment import JobOpening, post_job_opening, tick_laborer_wages
from realm.population.laborers import TICKS_PER_GAME_DAY, laborer_cash_account
from realm.world import bootstrap_frontier, bootstrap_genesis


def test_cpi_starts_at_100() -> None:
    w = bootstrap_frontier(seed=801, grid_width=4, grid_height=4)
    p = PartyId("player")
    for mat in CPI_BASKET:
        w.inventory.add(p, MaterialId(mat), 50)
        assert place_sell_order(w, p, MaterialId(mat), 10, 100)["ok"]
    w.tick = TICKS_PER_GAME_WEEK
    tick_cpi(w)
    assert abs(float(w.scenario_state.get("cpi_current", 0)) - 100.0) < 1e-6
    assert w.scenario_state.get("cpi_base_basket_cost") is not None


def test_cpi_rises_when_prices_rise() -> None:
    w = bootstrap_frontier(seed=802, grid_width=4, grid_height=4)
    p = PartyId("player")
    for mat in CPI_BASKET:
        w.inventory.add(p, MaterialId(mat), 50)
        assert place_sell_order(w, p, MaterialId(mat), 10, 100)["ok"]
    w.tick = TICKS_PER_GAME_WEEK
    tick_cpi(w)
    asks = w.market_asks_by_material.get("grain", [])
    assert asks and cancel_sell_order(w, p, asks[0].order_id)["ok"]
    assert place_sell_order(w, p, MaterialId("grain"), 10, 500)["ok"]
    w.tick = 2 * TICKS_PER_GAME_WEEK
    tick_cpi(w)
    assert float(w.scenario_state["cpi_current"]) > 100.0


def test_cpi_history_capped_at_52_entries() -> None:
    w = bootstrap_frontier(seed=803, grid_width=3, grid_height=3)
    p = PartyId("player")
    w.inventory.add(p, MaterialId("grain"), 100)
    assert place_sell_order(w, p, MaterialId("grain"), 5, 50)["ok"]
    for week in range(1, 60):
        w.tick = week * TICKS_PER_GAME_WEEK
        tick_cpi(w)
    hist = w.scenario_state.get("cpi_history", [])
    assert len(hist) <= 52


def test_cpi_indexed_wage_adjusts_with_inflation() -> None:
    w = bootstrap_genesis(seed=804, grid_width=48, grid_height=36, settler_count=6)
    human = PartyId("player")
    pid = next(x for x, pl in w.plots.items() if pl.owner is None)
    assert claim_plot(w, human, pid)["ok"] is True
    r = post_job_opening(
        w,
        human,
        PlotId(str(pid)),
        skill_min=0,
        wage_per_day_cents=1_000,
        cpi_indexed=True,
    )
    assert r["ok"] is True
    oid = str(r["opening_id"])
    opening = next(o for o in w.job_openings if o.opening_id == oid)
    lab_id = next(
        lid
        for lid, lab in w.laborers.items()
        if lab.employer is None and int(lab.skill_level) >= int(opening.skill_min)
    )
    lab = w.laborers[lab_id]
    lab.employer = human
    lab.employment_contract = opening.opening_id
    opening.filled_by = lab_id
    w.scenario_state["cpi_current"] = 120.0
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    w.tick = TICKS_PER_GAME_DAY
    out = tick_laborer_wages(w)
    assert out["cents_moved"] >= 1_200
    assert_money_conserved(w.ledger, snap.ledger_total_cents)
    lc = laborer_cash_account(lab_id)
    assert w.ledger.balance(lc) >= 1_200


def test_cpi_feed_entry_on_3pct_move() -> None:
    w = bootstrap_frontier(seed=805, grid_width=3, grid_height=3)
    p = PartyId("player")
    w.inventory.add(p, MaterialId("grain"), 50)
    assert place_sell_order(w, p, MaterialId("grain"), 5, 100)["ok"]
    w.tick = TICKS_PER_GAME_WEEK
    tick_cpi(w)
    asks = w.market_asks_by_material.get("grain", [])
    assert asks and cancel_sell_order(w, p, asks[0].order_id)["ok"]
    assert place_sell_order(w, p, MaterialId("grain"), 5, 200)["ok"]
    pre = len(w.event_log)
    w.tick = 2 * TICKS_PER_GAME_WEEK
    tick_cpi(w)
    new = w.event_log[pre:]
    hits = [e for e in new if e.get("kind") == "world_feed" and e.get("feed_source") == "cpi_alert"]
    assert hits, "expected CPI world_feed after >=3% WoW move"
