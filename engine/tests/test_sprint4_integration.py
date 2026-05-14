"""Sprint 4 integration — survey market, analytics, forwards, alerts, feed.

Bootstraps a Genesis world (default settler cohort), runs ~1 game-day of
``advance_tick`` with manual nudges, and asserts the end-to-end information-
economy story:

1. Survey reports — at least one SurveyReport exists in ``world.survey_reports``.
2. Survey broker — has purchased at least one high-grade report.
3. Analytics — purchase of ``price_history`` for coal returns data and charges 300c.
4. Forward contracts — at least one ``forward_contract`` row exists.
5. Feed — at least 5 distinct feed_source kinds present (we don't gate on the
   full 25 because the bigger triggers fire stochastically across many days;
   the broad catalogue is exercised by ``test_alerts_and_feed.py``).
6. Alerts — a price alert fires when its condition is met.
7. Conservation — ``world.ledger.total_cents()`` is unchanged.

The single bootstrap is reused across assertions so the test stays cheap.
"""

from __future__ import annotations

from realm.actions import create_survey_report
from realm.contracts.stubs import (
    accept_forward_contract,
    propose_forward_contract,
)
from realm.economy.analytics import (
    ANALYTICS_VENDOR_PARTY_ID,
    PRICE_HISTORY_COST_CENTS,
    purchase_analytics_product,
    seed_analytics_vendor,
)
from realm.genesis.broker import (
    BROKER_HIGH_GRADE_THRESHOLD,
    SURVEY_BROKER_PARTY_ID,
    seed_survey_broker,
    tick_survey_broker,
)
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.economy.markets import cancel_party_asks_for_material, place_sell_order
from realm.events.price_alerts import add_price_alert, tick_price_alerts
from realm.world.tick import advance_tick
from realm.world import World, bootstrap_genesis


def _give_cash(w: World, party: PartyId, cents: int) -> None:
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(
        debit=system_reserve_account(), credit=acct, amount_cents=cents
    )


def _player_plot(w: World) -> PlotId:
    player = PartyId("player")
    if player not in w.parties:
        w.parties.add(player)
        w.reputation.setdefault(str(player), {"honored": 0, "breached": 0})
    for pid, plot in w.plots.items():
        if str(plot.owner) == str(player):
            return pid
    for pid, plot in w.plots.items():
        if plot.owner is None:
            plot.owner = player
            return pid
    raise AssertionError("no unowned plot in world")


def test_sprint4_integration_end_to_end() -> None:
    w = bootstrap_genesis(seed=400, grid_width=24, grid_height=18, settler_count=20)
    starting_total_cents = w.ledger.total_cents()

    # Make sure both NPC vendors are seeded (idempotent).
    if ANALYTICS_VENDOR_PARTY_ID not in w.parties:
        seed_analytics_vendor(w)
    if SURVEY_BROKER_PARTY_ID not in w.parties:
        seed_survey_broker(w)

    # Ensure player party with cash for analytics purchases.
    player = PartyId("player")
    if player not in w.parties:
        w.parties.add(player)
        w.reputation.setdefault(str(player), {"honored": 0, "breached": 0})
    _give_cash(w, player, 1_000_000)  # $10k working capital

    # ── Pre-populate at least one settler-owned high-grade report so the broker
    # has something to buy on its first daily pass. (We don't rely on
    # stochastic settler surveying within a single game-day.)
    import dataclasses

    settler = PartyId("settler_001")
    if settler not in w.parties:
        w.parties.add(settler)
        w.reputation.setdefault(str(settler), {"honored": 0, "breached": 0})
    settler_plot: PlotId | None = None
    for pid, plot in w.plots.items():
        if str(plot.owner) == str(settler):
            settler_plot = pid
            break
    if settler_plot is None:
        for pid, plot in w.plots.items():
            if plot.owner is None:
                plot.owner = settler
                settler_plot = pid
                break
    assert settler_plot is not None
    p = w.plots[settler_plot]
    p.subsurface = dataclasses.replace(p.subsurface, iron_ore_grade=0.9)
    rep = create_survey_report(w, settler, settler_plot, is_deep=False)
    assert rep is not None
    assert max(rep.grades.values()) > BROKER_HIGH_GRADE_THRESHOLD

    # ── Run a small advance_tick window so day-cadence hooks fire at least once.
    for _ in range(200):
        advance_tick(w)
    # Force a day-boundary so broker + consolidator + settler-forward tickers run.
    w.tick = ((w.tick // 1440) + 1) * 1440
    tick_survey_broker(w)
    # Run a couple more advances so the broker's listings and the analytics
    # vendor have a chance to be touched by any agent loop.
    for _ in range(20):
        advance_tick(w)

    # ─── 1. SurveyReport exists ────────────────────────────────────────────
    assert len(w.survey_reports) >= 1
    assert rep.report_id in w.survey_reports

    # ─── 2. Broker has at least one report ─────────────────────────────────
    ownership = w.scenario_state.get("report_ownership", {})
    broker_owned = [
        rid for rid, owner in ownership.items() if owner == str(SURVEY_BROKER_PARTY_ID)
    ]
    assert broker_owned, "survey broker should have bought at least 1 report"

    # ─── 3. Analytics: price history for coal charges 300c, returns data ──
    cash_before = w.ledger.balance(party_cash_account(player))
    r = purchase_analytics_product(w, player, "price_history", {"material": "coal"})
    assert r["ok"] is True
    assert r["cost_cents"] == PRICE_HISTORY_COST_CENTS == 300
    assert w.ledger.balance(party_cash_account(player)) == cash_before - 300
    assert "series" in r["data"]

    # ─── 4. Forward contracts exist ────────────────────────────────────────
    # If the consolidator+settler organic flow hasn't proposed one yet (it's
    # probabilistic), synthesise one between two parties to exercise the
    # primitive. The agent paths are independently covered by
    # ``test_forward_contracts.py``.
    forward_rows = [
        c for c in w.contracts if str(c.get("kind", "")) == "forward_contract"
    ]
    if not forward_rows:
        seller_id = PartyId("settler_001")
        buyer_id = PartyId("pop_hub_e") if PartyId("pop_hub_e") in w.parties else player
        # Give seller cash for the deposit + inventory for delivery.
        _give_cash(w, seller_id, 100_000)
        w.inventory.add(seller_id, MaterialId("coal"), 100)
        _give_cash(w, buyer_id, 200_000)
        prop = propose_forward_contract(
            w, seller_id, buyer_id, MaterialId("coal"), 30, 80, int(w.tick) + 2880
        )
        assert prop.get("ok"), prop
        accept_forward_contract(w, buyer_id, str(prop["contract_id"]))
        forward_rows = [
            c for c in w.contracts if str(c.get("kind", "")) == "forward_contract"
        ]
    assert forward_rows, "expected at least one forward_contract in world.contracts"

    # ─── 5. Feed: ≥ 5 distinct feed_source kinds present ──────────────────
    # The catalogue has 25+ triggers; many fire only on multi-day cadences
    # (e.g. weekly digest, rank changes). We exercise a handful directly so
    # the assertion is deterministic in a 1-game-day window.
    from realm.events.sprint4_feed import tick_sprint4_feed

    if "coal" in w.market_asks_by_material:
        del w.market_asks_by_material["coal"]
    extra_seller = PartyId("settler_002") if PartyId("settler_002") in w.parties else player
    w.inventory.add(extra_seller, MaterialId("coal"), 5)
    place_sell_order(w, extra_seller, MaterialId("coal"), 5, 40)
    add_price_alert(w, "coal", "below", 55)
    tick_price_alerts(w)
    # Synthesise a settler bankruptcy + price spike. Use a conservation-preserving
    # transfer (cash → system reserve) followed by a 1c "fee" out the reserve so
    # the settler ends up negative.
    bankrupt_settler = PartyId("settler_003") if PartyId("settler_003") in w.parties else extra_seller
    sc = party_cash_account(bankrupt_settler)
    w.ledger.ensure_account(sc)
    bal = w.ledger.balance(sc)
    if bal > 0:
        w.ledger.transfer(debit=sc, credit=system_reserve_account(), amount_cents=bal)
    w.ledger.transfer(debit=sc, credit=system_reserve_account(), amount_cents=100)
    s4 = w.scenario_state.setdefault("genesis", {}).setdefault("sprint4_feed", {})
    s4["daily_price_open_cents"] = {"coal": 100}
    w.tick = ((w.tick // 1440) + 1) * 1440
    if "coal" in w.market_asks_by_material:
        del w.market_asks_by_material["coal"]
    w.inventory.add(extra_seller, MaterialId("coal"), 10)
    place_sell_order(w, extra_seller, MaterialId("coal"), 10, 200)
    tick_sprint4_feed(w)
    # Weekly digest fires at week boundary.
    w.tick = 10_080
    tick_sprint4_feed(w)

    feed_sources: set[str] = set()
    for row in w.world_feed_log:
        if str(row.get("kind", "")) != "world_feed":
            continue
        src = row.get("feed_source")
        if src:
            feed_sources.add(str(src))
    assert len(feed_sources) >= 5, (
        f"expected ≥5 distinct feed sources, got {sorted(feed_sources)}"
    )

    # ─── 6. Alert fires when condition is met ─────────────────────────────
    alert_rows = [
        row for row in w.world_feed_log if row.get("feed_source") == "price_alert"
    ]
    assert alert_rows, "expected at least one price_alert in feed"

    # ─── 7. Conservation across all of the above ──────────────────────────
    assert w.ledger.total_cents() == starting_total_cents, (
        f"ledger conservation broken: started at {starting_total_cents}, "
        f"now {w.ledger.total_cents()}"
    )
