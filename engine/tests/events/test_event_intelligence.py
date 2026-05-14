"""Phase 8 — Sub-phase 8E: intelligence products on top of the event system.

Covers the contract laid out in the Sub-phase 8E spec:
  * ``regional_risk`` analytics product returns active events + 30-day
    history + seasonal risk notes.
  * ``market_cycle`` analytics product flags spiked materials and reports
    bank credit posture + active route blockages.
  * Buying these products charges the buyer and credits the vendor
    (conservation holds).
  * Event entries persist in ``world.event_log`` (the Chronicle source)
    after the event itself has resolved.
"""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.economy.analytics import (
    MARKET_CYCLE_COST_CENTS,
    REGIONAL_RISK_COST_CENTS,
    purchase_analytics_product,
)
from realm.economy.market_events import (
    trigger_boom_event,
    trigger_route_blockage,
)
from realm.events.world_events import (
    tick_world_events,
    trigger_drought,
    trigger_storm,
)
from realm.world import bootstrap_genesis


def _ensure_cash(world, party: PartyId, amount: int) -> None:
    cash = party_cash_account(party)
    world.ledger.ensure_account(cash)
    if world.ledger.balance(cash) < amount:
        world.ledger.transfer(
            debit=system_reserve_account(),
            credit=cash,
            amount_cents=amount - world.ledger.balance(cash),
        )


# ─────────────────────────────────────────────────────────────────────
# Regional risk report
# ─────────────────────────────────────────────────────────────────────


def test_regional_risk_report_shows_active_drought() -> None:
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    w.tick = 100 * TICKS_PER_GAME_DAY  # mid-summer
    trigger_drought(w, 1, severity=0.7, duration_days=10)
    buyer = PartyId("player")
    _ensure_cash(w, buyer, REGIONAL_RISK_COST_CENTS + 100)
    pre_total = w.ledger.total_cents()
    res = purchase_analytics_product(w, buyer, "regional_risk")
    assert res.get("ok"), res
    data = res["data"]
    isl_data = next(i for i in data["islands"] if i["island_id"] == 1)
    drought_events = [
        e for e in isl_data["active_events"] if e["event_type"] == "drought"
    ]
    assert drought_events, "regional risk should list the active drought on island 1"
    assert w.ledger.total_cents() == pre_total, "purchase must conserve ledger total"


def test_regional_risk_report_summarises_recent_history() -> None:
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    w.tick = 100 * TICKS_PER_GAME_DAY
    ev = trigger_storm(w, 0, severity=0.8, duration_days=3)
    # Resolve the storm so it shows up as a historical 30-day event.
    w.tick = int(ev.end_tick) + 1
    tick_world_events(w)
    buyer = PartyId("player")
    _ensure_cash(w, buyer, REGIONAL_RISK_COST_CENTS + 100)
    res = purchase_analytics_product(w, buyer, "regional_risk")
    assert res.get("ok")
    isl0 = next(i for i in res["data"]["islands"] if i["island_id"] == 0)
    # Storm should appear in the 30-day frequency map even though it's resolved.
    assert isl0["events_last_30_days"].get("storm", 0) >= 1


def test_regional_risk_report_emits_seasonal_assessment() -> None:
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    w.tick = 100 * TICKS_PER_GAME_DAY  # summer
    buyer = PartyId("player")
    _ensure_cash(w, buyer, REGIONAL_RISK_COST_CENTS + 100)
    res = purchase_analytics_product(w, buyer, "regional_risk")
    assert res["ok"]
    notes = []
    for isl in res["data"]["islands"]:
        notes.extend(isl["risk_assessment"])
    assert any("drought risk" in n for n in notes), (
        f"expected at least one drought-risk note in summer (got {notes})"
    )


# ─────────────────────────────────────────────────────────────────────
# Market cycle report
# ─────────────────────────────────────────────────────────────────────


def test_market_cycle_report_flags_spiked_material() -> None:
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    # Seed 3 days of history at baseline 100 cents for grain.
    base_tick = max(0, int(w.tick) - TICKS_PER_GAME_DAY * 4)
    for i in range(3):
        w.market_history.append(
            {
                "tick": base_tick + i * TICKS_PER_GAME_DAY,
                "best_asks_cents": {"grain": 100},
                "best_bids_cents": {"grain": 95},
            }
        )
    # Place a high ask so the current best-ask is 200 (2.0× the MA).
    from realm.economy.markets import place_sell_order
    from realm.core.inventory import MatterErr

    npc = next(p for p in sorted(str(x) for x in w.parties) if p.startswith("settler"))
    npc_pid = PartyId(npc)
    ad = w.inventory.add(npc_pid, MaterialId("grain"), 5)
    if isinstance(ad, MatterErr):
        raise AssertionError(ad.reason)
    res = place_sell_order(w, npc_pid, MaterialId("grain"), 1, 200)
    assert res.get("ok")
    buyer = PartyId("player")
    _ensure_cash(w, buyer, MARKET_CYCLE_COST_CENTS + 100)
    out = purchase_analytics_product(w, buyer, "market_cycle")
    assert out["ok"]
    flagged = out["data"]["flagged_materials"]
    grain = next((f for f in flagged if f["material"] == "grain"), None)
    assert grain is not None, f"grain spike should be flagged (flagged={flagged})"
    assert grain["label"] in ("panic_risk", "elevated", "moderate")


def test_market_cycle_report_reflects_credit_crunch_status() -> None:
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    w.scenario_state["bank_credit_crunch"] = True
    buyer = PartyId("player")
    _ensure_cash(w, buyer, MARKET_CYCLE_COST_CENTS + 100)
    out = purchase_analytics_product(w, buyer, "market_cycle")
    assert out["ok"]
    assert out["data"]["bank_credit"]["crunch_active"] is True


def test_market_cycle_report_lists_active_route_blockages() -> None:
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    trigger_route_blockage(w, "island_0|island_1", duration_days=5)
    buyer = PartyId("player")
    _ensure_cash(w, buyer, MARKET_CYCLE_COST_CENTS + 100)
    out = purchase_analytics_product(w, buyer, "market_cycle")
    assert out["ok"]
    assert "island_0|island_1" in out["data"]["blocked_routes"]


# ─────────────────────────────────────────────────────────────────────
# Chronicle / event log persistence
# ─────────────────────────────────────────────────────────────────────


def test_event_persists_in_chronicle_after_resolution() -> None:
    """A resolved event still has its start/end rows in ``world.event_log``."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    w.tick = 100 * TICKS_PER_GAME_DAY
    ev = trigger_drought(w, 1, severity=0.5, duration_days=3)
    # Resolve it.
    w.tick = int(ev.end_tick) + 1
    tick_world_events(w)
    start_rows = [
        e for e in w.event_log
        if e.get("kind") == "world_feed"
        and e.get("event_class") == "world_event_start"
        and e.get("event_type") == "drought"
    ]
    end_rows = [
        e for e in w.event_log
        if e.get("kind") == "world_feed"
        and e.get("event_class") == "world_event_end"
        and e.get("event_type") == "drought"
    ]
    assert start_rows, "drought start chronicle row must persist"
    assert end_rows, "drought end chronicle row must persist"


# ─────────────────────────────────────────────────────────────────────
# Conservation
# ─────────────────────────────────────────────────────────────────────


def test_all_intel_purchases_conserve_ledger() -> None:
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    buyer = PartyId("player")
    _ensure_cash(w, buyer, REGIONAL_RISK_COST_CENTS + MARKET_CYCLE_COST_CENTS + 500)
    pre = w.ledger.total_cents()
    purchase_analytics_product(w, buyer, "regional_risk")
    purchase_analytics_product(w, buyer, "market_cycle")
    assert w.ledger.total_cents() == pre


def test_boom_event_shows_up_in_event_log() -> None:
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    pre = len(w.event_log)
    trigger_boom_event(w, 1, material="iron_ore")
    rows = [
        e for e in w.event_log[pre:]
        if e.get("event_class") == "boom_event"
    ]
    assert rows, "boom_event feed entry must fire and persist in the chronicle"
