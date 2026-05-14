"""Phase 9B — plot trading (transfer/list/buy) + speculative surveying.

Plots are property; property is tradeable (Primitive 1). These tests prove:

* ``transfer_plot`` — atomic P2P sale (ownership + cash + registry fee).
* ``list_plot_for_sale`` / ``buy_plot_listing`` — open-market plot listings.
* ``cancel_plot_listing`` — seller-only pull.
* ``authorize_survey`` + ``survey_plot_for`` — speculative surveying:
  surveyors may survey plots they don't own when (a) the plot is unclaimed
  or (b) the owner has issued an active authorization.

Use a hand-built world so we control parties, plots, and balances exactly.
"""

from __future__ import annotations

from realm.actions.plot_actions import (
    PLOT_TRANSFER_FEE_MIN_CENTS,
    SURVEY_AUTH_DURATION_TICKS,
    SURVEY_COST_CENTS,
    authorize_survey,
    buy_plot_listing,
    cancel_plot_listing,
    list_plot_for_sale,
    survey_plot_for,
    transfer_plot,
)
from realm.core.ids import PartyId, PlotId
from realm.core.inventory import Inventory
from realm.core.ledger import Ledger, party_cash_account, system_reserve_account
from realm.world import Plot, World
from realm.world.subsurface import SubsurfaceRoll
from realm.world.terrain import Terrain


def _empty_subsurface() -> SubsurfaceRoll:
    return SubsurfaceRoll(
        iron_ore_grade=0.5,  # something to survey
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
        sulfur_grade=0.0,
        saltpeter_grade=0.0,
        tin_grade=0.0,
        lead_grade=0.0,
        phosphate_grade=0.0,
        silica_grade=0.0,
        platinum_grade=0.0,
        oil_shale_grade=0.0,
        rare_earth_grade=0.0,
    )


def _make_world(*, owners: list[str] | None = None) -> tuple[World, list[PartyId]]:
    plot_a = Plot(
        plot_id=PlotId("p-1-1"),
        x=1,
        y=1,
        terrain=Terrain.PLAINS,
        owner=None,
        subsurface=_empty_subsurface(),
    )
    plot_b = Plot(
        plot_id=PlotId("p-2-2"),
        x=2,
        y=2,
        terrain=Terrain.PLAINS,
        owner=None,
        subsurface=_empty_subsurface(),
    )
    plot_frontier = Plot(
        plot_id=PlotId("p-9-9"),
        x=9,
        y=9,
        terrain=Terrain.PLAINS,
        owner=None,
        subsurface=_empty_subsurface(),
    )
    ledger = Ledger()
    ledger.seed_system_reserve(10_000_000)
    world = World(
        seed=42,
        tick=0,
        plots={p.plot_id: p for p in (plot_a, plot_b, plot_frontier)},
        ledger=ledger,
        inventory=Inventory(),
    )
    parties = [PartyId(pid) for pid in (owners or ["alice", "bob", "carol"])]
    for p in parties:
        world.parties.add(p)
        acct = party_cash_account(p)
        ledger.ensure_account(acct)
        ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=1_000_000,
        )
    # Alice owns plot_a; Bob and Carol start landless.
    plot_a.owner = parties[0]
    return world, parties


# ─────────────────────────── transfer_plot ───────────────────────────


def test_transfer_plot_atomic_cash_and_ownership():
    world, parties = _make_world()
    alice, bob, _carol = parties
    alice_acct = party_cash_account(alice)
    bob_acct = party_cash_account(bob)
    reserve_before = world.ledger.balance(system_reserve_account())
    alice_before = world.ledger.balance(alice_acct)
    bob_before = world.ledger.balance(bob_acct)
    res = transfer_plot(world, alice, bob, PlotId("p-1-1"), price_cents=200_000)
    assert res["ok"], res
    assert world.plots[PlotId("p-1-1")].owner == bob
    fee = res["fee_cents"]
    assert fee >= PLOT_TRANSFER_FEE_MIN_CENTS
    # Bob lost the sale price.
    assert world.ledger.balance(bob_acct) == bob_before - 200_000
    # Alice gained the sale price minus the registry fee.
    assert world.ledger.balance(alice_acct) == alice_before + 200_000 - fee
    # Registry fee flowed to system_reserve.
    assert world.ledger.balance(system_reserve_account()) == reserve_before + fee


def test_transfer_plot_rejects_non_owner_seller():
    world, parties = _make_world()
    alice, bob, _carol = parties
    res = transfer_plot(world, bob, alice, PlotId("p-1-1"), price_cents=100_000)
    assert not res["ok"]
    assert "does not own" in res["reason"]


def test_transfer_plot_rejects_insufficient_cash():
    world, parties = _make_world()
    alice, bob, _carol = parties
    res = transfer_plot(world, alice, bob, PlotId("p-1-1"), price_cents=9_999_999)
    assert not res["ok"]
    assert "cash" in res["reason"].lower()
    assert world.plots[PlotId("p-1-1")].owner == alice


def test_transfer_plot_self_is_blocked():
    world, parties = _make_world()
    alice, _bob, _carol = parties
    res = transfer_plot(world, alice, alice, PlotId("p-1-1"), price_cents=100)
    assert not res["ok"]


# ──────────────────────── listings + buy ────────────────────────


def test_list_plot_creates_active_listing():
    world, parties = _make_world()
    alice, _bob, _carol = parties
    res = list_plot_for_sale(world, alice, PlotId("p-1-1"), ask_price_cents=300_000)
    assert res["ok"], res
    assert len(world.plot_listings) == 1
    row = world.plot_listings[0]
    assert row["status"] == "active"
    assert row["ask_price_cents"] == 300_000


def test_list_plot_rejects_non_owner():
    world, parties = _make_world()
    _alice, bob, _carol = parties
    res = list_plot_for_sale(world, bob, PlotId("p-1-1"), ask_price_cents=100)
    assert not res["ok"]


def test_list_plot_rejects_duplicate_listing():
    world, parties = _make_world()
    alice, _bob, _carol = parties
    assert list_plot_for_sale(world, alice, PlotId("p-1-1"), 100_000)["ok"]
    dup = list_plot_for_sale(world, alice, PlotId("p-1-1"), 200_000)
    assert not dup["ok"]


def test_cancel_listing_only_by_seller():
    world, parties = _make_world()
    alice, bob, _carol = parties
    listed = list_plot_for_sale(world, alice, PlotId("p-1-1"), 250_000)
    assert listed["ok"]
    lid = listed["listing_id"]
    not_yours = cancel_plot_listing(world, bob, lid)
    assert not not_yours["ok"]
    cancelled = cancel_plot_listing(world, alice, lid)
    assert cancelled["ok"]
    # Same id can't be cancelled twice.
    assert not cancel_plot_listing(world, alice, lid)["ok"]


def test_buy_plot_listing_transfers_ownership_and_marks_sold():
    world, parties = _make_world()
    alice, bob, _carol = parties
    listed = list_plot_for_sale(world, alice, PlotId("p-1-1"), 200_000)
    assert listed["ok"]
    res = buy_plot_listing(world, bob, listed["listing_id"])
    assert res["ok"], res
    assert world.plots[PlotId("p-1-1")].owner == bob
    listing = world.plot_listings[0]
    assert listing["status"] == "sold"
    assert listing["buyer"] == str(bob)


def test_buy_own_listing_rejected():
    world, parties = _make_world()
    alice, _bob, _carol = parties
    listed = list_plot_for_sale(world, alice, PlotId("p-1-1"), 100)
    assert listed["ok"]
    res = buy_plot_listing(world, alice, listed["listing_id"])
    assert not res["ok"]


# ────────────────────── speculative surveying ──────────────────────


def test_speculative_survey_of_unclaimed_plot_succeeds():
    world, parties = _make_world()
    _alice, bob, _carol = parties
    # plot_frontier (p-9-9) is unclaimed → bob can survey it.
    res = survey_plot_for(world, bob, PlotId("p-9-9"))
    assert res["ok"], res
    assert world.plots[PlotId("p-9-9")].surveyed
    # Surveyor owns the resulting report.
    owners = world.scenario_state.get("report_ownership", {})
    assert any(owner == str(bob) for owner in owners.values())


def test_speculative_survey_blocked_without_authorization():
    world, parties = _make_world()
    _alice, bob, _carol = parties
    res = survey_plot_for(world, bob, PlotId("p-1-1"))
    assert not res["ok"]
    assert "authorization" in res["reason"].lower()


def test_authorized_survey_consumes_authorization():
    world, parties = _make_world()
    alice, bob, _carol = parties
    auth = authorize_survey(world, alice, bob, PlotId("p-1-1"))
    assert auth["ok"], auth
    assert len(world.survey_authorizations) == 1
    res = survey_plot_for(world, bob, PlotId("p-1-1"))
    assert res["ok"], res
    assert world.plots[PlotId("p-1-1")].surveyed
    # Authorization consumed.
    assert len(world.survey_authorizations) == 0
    # Surveyor owns the report (not the plot owner).
    owners = world.scenario_state.get("report_ownership", {})
    assert any(owner == str(bob) for owner in owners.values())


def test_expired_authorization_does_not_unblock_survey():
    world, parties = _make_world()
    alice, bob, _carol = parties
    auth = authorize_survey(world, alice, bob, PlotId("p-1-1"))
    assert auth["ok"], auth
    # Advance past expiry.
    world.tick = int(auth["expires_at_tick"]) + 1
    res = survey_plot_for(world, bob, PlotId("p-1-1"))
    assert not res["ok"]
    assert "authorization" in res["reason"].lower()


def test_speculative_survey_costs_the_surveyor():
    world, parties = _make_world()
    _alice, bob, _carol = parties
    bob_acct = party_cash_account(bob)
    before = world.ledger.balance(bob_acct)
    res = survey_plot_for(world, bob, PlotId("p-9-9"))
    assert res["ok"], res
    assert world.ledger.balance(bob_acct) == before - SURVEY_COST_CENTS


def test_owner_cannot_survey_via_survey_plot_for():
    """Plot owner should use the normal ``survey_plot`` (not the ``_for`` path)."""
    world, parties = _make_world()
    alice, _bob, _carol = parties
    res = survey_plot_for(world, alice, PlotId("p-1-1"))
    assert not res["ok"]


def test_authorization_window_is_30_game_days():
    world, parties = _make_world()
    alice, bob, _carol = parties
    res = authorize_survey(world, alice, bob, PlotId("p-1-1"))
    assert res["ok"]
    assert res["expires_at_tick"] == SURVEY_AUTH_DURATION_TICKS
