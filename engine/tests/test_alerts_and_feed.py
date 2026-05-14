"""Sprint 4 — Phase D tests: price alerts, world feed expansion, weekly digest."""

from __future__ import annotations

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.markets import cancel_party_asks_for_material, place_sell_order
from realm.events.price_alerts import add_price_alert, remove_price_alert, tick_price_alerts
from realm.events.sprint4_feed import tick_sprint4_feed
from realm.world import bootstrap_frontier, bootstrap_genesis


def _feed_kinds(w) -> set[str]:
    """Distinct feed_source tags across world_feed entries."""
    out: set[str] = set()
    for row in w.world_feed_log:
        if str(row.get("kind", "")) != "world_feed":
            continue
        src = row.get("feed_source") or row.get("kind_tag")
        if src:
            out.add(str(src))
    return out


def _give_cash(w, party: PartyId, cents: int) -> None:
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(
        debit=system_reserve_account(), credit=acct, amount_cents=cents
    )


def test_price_alert_triggers_when_condition_met() -> None:
    w = bootstrap_frontier(seed=51, grid_width=4, grid_height=3)
    # Clear coal asks so we can set a controlled price.
    if "coal" in w.market_asks_by_material:
        del w.market_asks_by_material["coal"]
    seller = PartyId("t1_coal_vendor")
    place_sell_order(w, seller, MaterialId("coal"), 5, 80)
    r = add_price_alert(w, "coal", "below", 55)
    assert r["ok"]
    feed_before = len(w.world_feed_log)
    tick_price_alerts(w)  # not below 55, no fire
    assert len(w.world_feed_log) == feed_before
    # Drop the price: cancel and relist below 55.
    cancel_party_asks_for_material(w, seller, MaterialId("coal"))
    w.inventory.add(seller, MaterialId("coal"), 10)
    place_sell_order(w, seller, MaterialId("coal"), 5, 40)
    tick_price_alerts(w)
    assert len(w.world_feed_log) >= feed_before + 1
    fired = w.world_feed_log[-1]
    assert "ALERT" in fired.get("message", "")
    assert fired.get("feed_source") == "price_alert"


def test_price_alert_does_not_retrigger_without_recovery() -> None:
    w = bootstrap_frontier(seed=52, grid_width=4, grid_height=3)
    if "coal" in w.market_asks_by_material:
        del w.market_asks_by_material["coal"]
    seller = PartyId("t1_coal_vendor")
    w.inventory.add(seller, MaterialId("coal"), 20)
    place_sell_order(w, seller, MaterialId("coal"), 5, 40)
    add_price_alert(w, "coal", "below", 55)
    tick_price_alerts(w)
    after_first = sum(
        1 for row in w.world_feed_log if row.get("feed_source") == "price_alert"
    )
    # Tick a few more times without changing price.
    for _ in range(5):
        tick_price_alerts(w)
    after_repeat = sum(
        1 for row in w.world_feed_log if row.get("feed_source") == "price_alert"
    )
    assert after_repeat == after_first  # no duplicate fires while staying below


def test_price_alert_delete() -> None:
    w = bootstrap_frontier(seed=53, grid_width=4, grid_height=3)
    if "coal" in w.market_asks_by_material:
        del w.market_asks_by_material["coal"]
    seller = PartyId("t1_coal_vendor")
    w.inventory.add(seller, MaterialId("coal"), 20)
    place_sell_order(w, seller, MaterialId("coal"), 5, 100)
    r = add_price_alert(w, "coal", "below", 55)
    alert_id = r["alert_id"]
    rem = remove_price_alert(w, alert_id)
    assert rem["ok"] is True
    # Now drop the price; the alert should NOT fire because it's deleted.
    cancel_party_asks_for_material(w, seller, MaterialId("coal"))
    w.inventory.add(seller, MaterialId("coal"), 10)
    place_sell_order(w, seller, MaterialId("coal"), 5, 30)
    feed_before = sum(
        1 for row in w.world_feed_log if row.get("feed_source") == "price_alert"
    )
    tick_price_alerts(w)
    feed_after = sum(
        1 for row in w.world_feed_log if row.get("feed_source") == "price_alert"
    )
    assert feed_after == feed_before


def test_feed_fires_on_settler_bankruptcy() -> None:
    w = bootstrap_genesis(seed=54, grid_width=10, grid_height=8, settler_count=4)
    settler = PartyId("settler_001")
    # Force settler into the red by transferring more cash out than they hold.
    sc = party_cash_account(settler)
    bal = w.ledger.balance(sc)
    # Manually push the balance negative — we want to test the feed hook.
    w.ledger.balances[str(sc)] = -100
    feed_before = len(w.world_feed_log)
    tick_sprint4_feed(w)
    feed_kinds = [
        row.get("feed_source")
        for row in w.world_feed_log[feed_before:]
        if row.get("kind") == "world_feed"
    ]
    assert "settler_bankruptcy" in feed_kinds


def test_feed_fires_on_price_spike() -> None:
    """A 15% intraday price move triggers a price_spike feed entry."""
    w = bootstrap_genesis(seed=55, grid_width=8, grid_height=6, settler_count=2)
    # Manually seed the daily-open price so the day-boundary scan sees a
    # large move regardless of which materials genesis bootstrap touched.
    gst = w.scenario_state.setdefault("genesis", {})
    s4 = gst.setdefault("sprint4_feed", {})
    s4["daily_price_open_cents"] = {"coal": 100}
    # Set up a new coal-only ask book at 130¢ — a 30% lift over the recorded open.
    if "coal" in w.market_asks_by_material:
        del w.market_asks_by_material["coal"]
    seller = PartyId("t1_coal_vendor") if PartyId("t1_coal_vendor") in w.parties else PartyId("settler_001")
    w.inventory.add(seller, MaterialId("coal"), 5)
    place_sell_order(w, seller, MaterialId("coal"), 5, 130)
    w.tick = 1440  # day boundary
    tick_sprint4_feed(w)
    spike_lines = [
        row
        for row in w.world_feed_log
        if row.get("feed_source") == "price_spike" and str(row.get("material", "")) == "coal"
    ]
    assert spike_lines, "expected a price_spike entry for coal"


def test_weekly_digest_fires_every_10080_ticks() -> None:
    w = bootstrap_genesis(seed=56, grid_width=8, grid_height=6, settler_count=2)
    # Run the feed function at the two weekly tick boundaries; outside of the
    # boundary it should not emit a digest. The frontier-style integer-tick
    # scheduling is what the spec calls for.
    w.tick = 10_080
    tick_sprint4_feed(w)
    w.tick = 20_160
    tick_sprint4_feed(w)
    digests = [
        row for row in w.world_feed_log if row.get("feed_source") == "weekly_digest"
    ]
    assert len(digests) == 2


def test_feed_fires_on_new_building_type() -> None:
    """The first time a new building_id appears in plot_buildings the existing
    ``note_genesis_first_building_operational`` hook emits ``first_building``.
    """
    from realm.genesis_feed_hooks import note_genesis_first_building_operational

    w = bootstrap_genesis(seed=57, grid_width=8, grid_height=6, settler_count=2)
    party = PartyId("settler_001")
    # Synthesise a completed blast_furnace row so the hook believes it's
    # operational at the current tick.
    w.plot_buildings.append(
        {
            "instance_id": "b000999",
            "plot_id": "p-0-0",
            "party": str(party),
            "building_id": "blast_furnace",
            "completes_at_tick": 0,
            "condition_bps": 10_000,
        }
    )
    note_genesis_first_building_operational(w, party, "blast_furnace")
    found = [
        row
        for row in w.world_feed_log
        if row.get("feed_source") == "first_building"
        and row.get("building_id") == "blast_furnace"
    ]
    assert found


def test_distinct_feed_kinds_after_warmup() -> None:
    """Sanity: bootstrap genesis, tick a small window + a couple manual triggers,
    expect several distinct feed sources (the catalogue is wide on purpose)."""
    w = bootstrap_genesis(seed=58, grid_width=24, grid_height=18, settler_count=10)
    from realm.world.tick import advance_tick

    for _ in range(200):
        advance_tick(w)
    # Add a couple manual triggers so the test is independent of agent stochastics.
    add_price_alert(w, "coal", "above", 1)
    tick_price_alerts(w)
    # Synthesise a settler bankruptcy + spike to cover deterministic kinds.
    settler = PartyId("settler_001")
    sc = party_cash_account(settler)
    w.ledger.balances[str(sc)] = -100
    gst = w.scenario_state.setdefault("genesis", {})
    s4 = gst.setdefault("sprint4_feed", {})
    s4["daily_price_open_cents"] = {"coal": 100}
    w.tick = ((w.tick // 1440) + 1) * 1440
    if "coal" in w.market_asks_by_material:
        del w.market_asks_by_material["coal"]
    seller = PartyId("settler_002")
    w.inventory.add(seller, MaterialId("coal"), 5)
    place_sell_order(w, seller, MaterialId("coal"), 5, 130)
    tick_sprint4_feed(w)
    note_kinds = _feed_kinds(w)
    assert len(note_kinds) >= 4, f"expected several feed kinds, got {note_kinds}"
