"""Sprint 4 — Phase B tests: analytics NPC service (price history, regional surveys, etc.)."""

from __future__ import annotations

import statistics

from realm.events.event_log import log_event
from realm.economy.analytics import (
    ANALYTICS_VENDOR_PARTY_ID,
    PARTY_VOLUME_COST_CENTS,
    PARTY_VOLUME_WINDOW_DAYS,
    PRICE_HISTORY_COST_CENTS,
    PRICE_HISTORY_WINDOW_DAYS,
    REGIONAL_SURVEY_COST_CENTS,
    SUPPLY_SHORTAGE_COST_CENTS,
    purchase_analytics_product,
    seed_analytics_vendor,
)
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.economy.markets import cancel_party_asks_for_material, place_sell_order
from realm.world.regions import _world_bounds, region_for_coords
from realm.world import World, bootstrap_frontier, bootstrap_genesis


def _give_cash(w: World, party: PartyId, cents: int) -> None:
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(
        debit=system_reserve_account(), credit=acct, amount_cents=cents
    )


def _genesis() -> World:
    w = bootstrap_genesis(seed=300, grid_width=16, grid_height=12, settler_count=4)
    if ANALYTICS_VENDOR_PARTY_ID not in w.parties:
        seed_analytics_vendor(w)
    return w


# ───────────────────────── tests ─────────────────────────


def test_price_history_purchase_deducts_300c() -> None:
    w = _genesis()
    player = PartyId("player")
    if player not in w.parties:
        w.parties.add(player)
        w.reputation.setdefault(str(player), {"honored": 0, "breached": 0})
    _give_cash(w, player, 100_000)
    starting_total = w.ledger.total_cents()
    cash_before = w.ledger.balance(party_cash_account(player))
    r = purchase_analytics_product(w, player, "price_history", {"material": "coal"})
    assert r["ok"] is True
    assert r["cost_cents"] == PRICE_HISTORY_COST_CENTS == 300
    assert w.ledger.balance(party_cash_account(player)) == cash_before - 300
    assert w.ledger.total_cents() == starting_total


def test_price_history_returns_30_days_window() -> None:
    """Tick a few price points; the returned series matches the window."""
    w = _genesis()
    player = PartyId("player")
    if player not in w.parties:
        w.parties.add(player)
    _give_cash(w, player, 100_000)
    # Inject synthetic market_history rows at various ticks.
    w.market_history.append(
        {"tick": 100, "best_asks_cents": {"coal": 100, "iron_ore": 250}}
    )
    w.market_history.append(
        {"tick": 200, "best_asks_cents": {"coal": 110}}
    )
    w.market_history.append(
        {"tick": 300, "best_asks_cents": {"coal": 105}}
    )
    w.tick = 400
    r = purchase_analytics_product(w, player, "price_history", {"material": "coal"})
    assert r["ok"] is True
    series = r["data"]["series"]
    # All 3 injected rows fall within the 30-day window; bootstrap-time rows
    # at tick 0 may also be present.
    injected_ticks = {row["tick"] for row in series}
    assert {100, 200, 300}.issubset(injected_ticks)
    assert r["data"]["window_days"] == PRICE_HISTORY_WINDOW_DAYS


def test_regional_survey_aggregate_accuracy() -> None:
    """Returned avg matches the true plot-level average for the region."""
    w = _genesis()
    player = PartyId("player")
    if player not in w.parties:
        w.parties.add(player)
    _give_cash(w, player, 100_000)
    width, height = _world_bounds(w)
    # Pick the first region that has at least 4 plots.
    from realm.world.regions import all_region_ids

    region_id: str | None = None
    region_grades: list[float] = []
    for rid_candidate in all_region_ids():
        grades = [
            float(p.subsurface.iron_ore_grade)
            for p in w.plots.values()
            if region_for_coords(p.x, p.y, width, height) == rid_candidate
        ]
        if len(grades) >= 4:
            region_id = rid_candidate
            region_grades = grades
            break
    assert region_id is not None
    expected = statistics.fmean(region_grades)
    r = purchase_analytics_product(
        w,
        player,
        "regional_survey",
        {"mineral": "iron_ore", "region_id": region_id},
    )
    assert r["ok"] is True
    assert abs(float(r["data"]["avg_grade"]) - expected) < 1e-3
    assert r["data"]["plots_sampled"] == len(region_grades)


def test_party_volume_shows_significant_only() -> None:
    """Trades > 50 units appear as 'significant'; < 50 do not appear."""
    w = _genesis()
    player = PartyId("player")
    if player not in w.parties:
        w.parties.add(player)
    _give_cash(w, player, 100_000)
    target = PartyId("settler_001")
    if target not in w.parties:
        w.parties.add(target)
    # Synthesise market_match events for the last 7 days.
    w.tick = 5000
    log_event(
        w,
        "market_match",
        "synthetic coal match",
        material="coal",
        buyer=str(target),
        seller="other",
        qty=100,
    )
    log_event(
        w,
        "market_match",
        "synthetic timber match",
        material="timber",
        buyer=str(target),
        seller="other",
        qty=10,
    )
    r = purchase_analytics_product(
        w, player, "party_volume", {"party_id": str(target)}
    )
    assert r["ok"] is True
    profile = r["data"]["profile"]
    coal_lines = [p for p in profile if p["material"] == "coal"]
    timber_lines = [p for p in profile if p["material"] == "timber"]
    assert coal_lines and coal_lines[0]["signal"] == "significant"
    assert not timber_lines  # under threshold — should not appear


def test_supply_shortage_identifies_scarce_materials() -> None:
    """A material with <10 ask-units shows up in the shortage list."""
    w = _genesis()
    player = PartyId("player")
    if player not in w.parties:
        w.parties.add(player)
    _give_cash(w, player, 100_000)
    # Remove ALL coal asks so the depth is 0.
    coal = MaterialId("coal")
    if "coal" in w.market_asks_by_material:
        del w.market_asks_by_material["coal"]
    # Make sure coal is in the recent history so the scanner sees it.
    w.market_history.append({"tick": int(w.tick), "best_asks_cents": {"coal": 100}})
    r = purchase_analytics_product(w, player, "supply_shortage", {})
    assert r["ok"] is True
    assert "coal" in r["data"]["materials_in_shortage"]


def test_analytics_purchase_logged() -> None:
    w = _genesis()
    player = PartyId("player")
    if player not in w.parties:
        w.parties.add(player)
    _give_cash(w, player, 100_000)
    log_count_before = len(w.analytics_purchases)
    r = purchase_analytics_product(w, player, "supply_shortage", {})
    assert r["ok"] is True
    assert len(w.analytics_purchases) == log_count_before + 1
    rec = w.analytics_purchases[-1]
    assert rec["product"] == "supply_shortage"
    assert rec["party"] == "player"
    assert rec["cost_cents"] == SUPPLY_SHORTAGE_COST_CENTS == 400


def test_unknown_product_rejected_without_charge() -> None:
    w = _genesis()
    player = PartyId("player")
    if player not in w.parties:
        w.parties.add(player)
    _give_cash(w, player, 100_000)
    cash_before = w.ledger.balance(party_cash_account(player))
    r = purchase_analytics_product(w, player, "vibes", {})
    assert r["ok"] is False
    assert w.ledger.balance(party_cash_account(player)) == cash_before
