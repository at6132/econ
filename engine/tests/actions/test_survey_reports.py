"""Sprint 4 — Phase A tests: survey reports as tradeable assets, intel market, broker."""

from __future__ import annotations

from realm.actions import (
    SURVEY_COST_CENTS,
    buy_survey_report,
    create_survey_report,
    list_survey_report,
    survey_plot,
    transfer_survey_report,
)
from realm.genesis.broker import (
    BROKER_BUY_STANDARD_CENTS,
    BROKER_HIGH_GRADE_THRESHOLD,
    SURVEY_BROKER_PARTY_ID,
    seed_survey_broker,
    tick_survey_broker,
)
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.world import World, bootstrap_frontier, bootstrap_genesis


def _give_cash(w: World, party: PartyId, cents: int) -> None:
    acct = party_cash_account(party)
    w.ledger.ensure_account(acct)
    w.ledger.transfer(
        debit=system_reserve_account(), credit=acct, amount_cents=cents
    )


def _ensure_party(w: World, party: PartyId, cash_cents: int = 0) -> None:
    if party not in w.parties:
        w.parties.add(party)
        w.reputation.setdefault(str(party), {"honored": 0, "breached": 0})
    if cash_cents > 0:
        _give_cash(w, party, cash_cents)


def _player_plot(w: World) -> PlotId:
    """Return (or assign) a plot owned by the human ('player') party."""
    player = PartyId("player")
    for pid, plot in w.plots.items():
        if str(plot.owner) == str(player):
            return pid
    for pid, plot in w.plots.items():
        if plot.owner is None:
            plot.owner = player
            return pid
    raise AssertionError("no unowned plot to claim")


# ───────────────────────── tests ─────────────────────────


def test_survey_creates_report() -> None:
    w = bootstrap_frontier(seed=200, grid_width=4, grid_height=3)
    player = PartyId("player")
    _give_cash(w, player, SURVEY_COST_CENTS)
    plot_id = _player_plot(w)
    r = survey_plot(w, player, plot_id)
    assert r["ok"] is True
    # Exactly one new survey report for this plot, owned by the player.
    matches = [
        rep
        for rep in w.survey_reports.values()
        if str(rep.plot_id) == str(plot_id) and str(rep.conducted_by) == "player"
    ]
    assert len(matches) == 1
    report = matches[0]
    ownership = w.scenario_state.get("report_ownership", {})
    assert ownership.get(report.report_id) == "player"
    assert report.survey_type == "standard"
    assert report.is_deep is False
    assert isinstance(report.grades, dict) and len(report.grades) >= 5


def test_report_transfer_moves_ownership_and_money() -> None:
    w = bootstrap_frontier(seed=201, grid_width=4, grid_height=3)
    seller = PartyId("player")
    buyer = PartyId("buyer_alpha")
    _ensure_party(w, buyer, cash_cents=10_000)
    plot_id = _player_plot(w)
    report = create_survey_report(w, seller, plot_id, is_deep=False)
    assert report is not None
    starting_total = w.ledger.total_cents()
    seller_cash_before = w.ledger.balance(party_cash_account(seller))
    buyer_cash_before = w.ledger.balance(party_cash_account(buyer))
    r = transfer_survey_report(
        w, seller, buyer, report.report_id, price_cents=500
    )
    assert r["ok"] is True
    assert w.scenario_state["report_ownership"][report.report_id] == str(buyer)
    assert w.ledger.balance(party_cash_account(buyer)) == buyer_cash_before - 500
    assert w.ledger.balance(party_cash_account(seller)) == seller_cash_before + 500
    assert w.ledger.total_cents() == starting_total


def test_report_listing_and_purchase() -> None:
    w = bootstrap_frontier(seed=202, grid_width=4, grid_height=3)
    seller = PartyId("player")
    buyer = PartyId("buyer_beta")
    _ensure_party(w, buyer, cash_cents=10_000)
    plot_id = _player_plot(w)
    report = create_survey_report(w, seller, plot_id, is_deep=False)
    assert report is not None
    lst = list_survey_report(w, seller, report.report_id, ask_price_cents=600)
    assert lst["ok"] is True
    starting_total = w.ledger.total_cents()
    buy = buy_survey_report(w, buyer, lst["listing_id"])
    assert buy["ok"] is True
    # New owner can read grades.
    visible = w.visible_survey_reports_for(buyer)
    assert any(rep.report_id == report.report_id for rep in visible)
    # Listing flipped to sold; ownership flipped to buyer.
    listing_rows = [row for row in w.intel_listings if row["listing_id"] == lst["listing_id"]]
    assert listing_rows and listing_rows[0]["status"] == "sold"
    assert w.scenario_state["report_ownership"][report.report_id] == str(buyer)
    assert w.ledger.total_cents() == starting_total


def test_report_not_visible_without_ownership() -> None:
    w = bootstrap_frontier(seed=203, grid_width=4, grid_height=3)
    seller = PartyId("player")
    other = PartyId("buyer_gamma")
    _ensure_party(w, other, cash_cents=10_000)
    plot_id = _player_plot(w)
    report = create_survey_report(w, seller, plot_id, is_deep=False)
    assert report is not None
    visible = w.visible_survey_reports_for(other)
    assert all(rep.report_id != report.report_id for rep in visible)


def test_high_grade_check_threshold() -> None:
    """Sanity: the broker's helper recognises grade ≥ 0.5 as high."""
    from realm.genesis.broker import _is_high_grade
    from realm.world import SurveyReport

    high = SurveyReport(
        report_id="x",
        plot_id=PlotId("p-0-0"),
        conducted_by=PartyId("settler_001"),
        conducted_at_tick=0,
        grades={"iron_ore_grade": 0.6, "coal_grade": 0.1},
        survey_type="standard",
        is_deep=False,
    )
    low = SurveyReport(
        report_id="y",
        plot_id=PlotId("p-0-0"),
        conducted_by=PartyId("settler_001"),
        conducted_at_tick=0,
        grades={"iron_ore_grade": 0.2, "coal_grade": 0.1},
        survey_type="standard",
        is_deep=False,
    )
    assert _is_high_grade(high) is True
    assert _is_high_grade(low) is False


def test_survey_broker_buys_high_grade_reports() -> None:
    """A settler-owned report with a grade > 0.5 is bought by the broker on its tick."""
    w = bootstrap_genesis(seed=204, grid_width=12, grid_height=8, settler_count=4)
    settler = PartyId("settler_001")
    _ensure_party(w, settler, cash_cents=0)
    # Find a settler-owned plot (genesis assigns settlers some plots), else synthesise one.
    settler_plot: PlotId | None = None
    for pid, plot in w.plots.items():
        if str(plot.owner) == str(settler):
            settler_plot = pid
            break
    if settler_plot is None:
        # Take an unowned plot and assign it.
        for pid, plot in w.plots.items():
            if plot.owner is None:
                plot.owner = settler
                settler_plot = pid
                break
    assert settler_plot is not None
    plot = w.plots[settler_plot]
    # Force iron_ore grade up so the report is "high-grade".
    import dataclasses

    plot.subsurface = dataclasses.replace(plot.subsurface, iron_ore_grade=0.85)
    report = create_survey_report(w, settler, settler_plot, is_deep=False)
    assert report is not None
    assert max(report.grades.values()) > BROKER_HIGH_GRADE_THRESHOLD

    assert SURVEY_BROKER_PARTY_ID in w.parties or seed_survey_broker(w)
    settler_cash_before = w.ledger.balance(party_cash_account(settler))
    # Tick the broker on a day boundary.
    w.tick = 1440
    tick_survey_broker(w)
    ownership = w.scenario_state.get("report_ownership", {})
    assert ownership.get(report.report_id) == str(SURVEY_BROKER_PARTY_ID)
    assert (
        w.ledger.balance(party_cash_account(settler))
        == settler_cash_before + BROKER_BUY_STANDARD_CENTS
    )
    # The broker should also list it in the intel market.
    listings = [
        row
        for row in w.intel_listings
        if row["report_id"] == report.report_id and row["status"] == "active"
    ]
    assert listings, "broker should relist the bought report"
