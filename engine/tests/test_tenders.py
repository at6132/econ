"""Sprint 2 — Phase C · open supply tenders.

Covers the full tender pipeline: posting, bidding (including bid revision),
deadline-based awarding to the lowest bidder, SupplyContract creation on
award, settler bidding behaviour, and the "bid without inventory" semantics
(commitment to future delivery).

Phase 7A: ``pop_hub_e/w`` were removed. Tests post tenders directly from
``player`` (or another entrepreneur) — the test coverage is for the tender
*mechanism*, not for who posts.
"""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId
from realm.settler_cost_basis import record_settler_production
from realm.tenders import (
    list_all_tenders,
    list_open_tenders,
    post_tender,
    submit_tender_bid,
    tender_by_id,
    tick_settler_tender_bidding,
    tick_tender_lifecycle,
)
from realm.world import World, bootstrap_genesis


_POSTER = PartyId("player")


def _world() -> World:
    return bootstrap_genesis(seed=42, settler_count=4, grid_width=12, grid_height=10)


# ───────────────────────── unit tests ─────────────────────────


def test_post_tender_validates_arguments() -> None:
    w = _world()
    bad = post_tender(
        w,
        posted_by=_POSTER,
        material=MaterialId("coal"),
        qty_per_cycle=0,
        interval_ticks=1440,
        duration_cycles=10,
        bid_window_ticks=1440,
    )
    assert bad["ok"] is False


def test_post_tender_rejects_unknown_poster() -> None:
    w = _world()
    bad = post_tender(
        w,
        posted_by=PartyId("not_a_real_party"),
        material=MaterialId("coal"),
        qty_per_cycle=4,
        interval_ticks=1440,
        duration_cycles=2,
        bid_window_ticks=1440,
    )
    assert bad["ok"] is False
    assert "party" in bad["reason"].lower()


def test_bid_submission_and_revision() -> None:
    w = _world()
    r = post_tender(
        w,
        posted_by=_POSTER,
        material=MaterialId("coal"),
        qty_per_cycle=10,
        interval_ticks=1440,
        duration_cycles=5,
        bid_window_ticks=2000,
    )
    tid = r["tender_id"]
    b1 = submit_tender_bid(w, PartyId("settler_001"), tid, 85)
    assert b1["ok"]
    tender = tender_by_id(w, tid)
    assert len(tender["bids"]) == 1
    # Bid revision: same bidder, new price → only one entry remains.
    b2 = submit_tender_bid(w, PartyId("settler_001"), tid, 75)
    assert b2["ok"]
    tender = tender_by_id(w, tid)
    assert len(tender["bids"]) == 1
    assert tender["bids"][0]["price_per_unit_cents"] == 75


def test_bid_does_not_require_current_inventory() -> None:
    """A settler with no inventory can still submit a bid (forward commitment)."""
    w = _world()
    r = post_tender(
        w,
        posted_by=_POSTER,
        material=MaterialId("coal"),
        qty_per_cycle=4,
        interval_ticks=1440,
        duration_cycles=3,
        bid_window_ticks=720,
    )
    party = PartyId("settler_001")
    assert int(w.inventory.qty(party, MaterialId("coal"))) == 0
    b = submit_tender_bid(w, party, r["tender_id"], 80)
    assert b["ok"]


def test_bid_rejected_after_deadline() -> None:
    w = _world()
    r = post_tender(
        w,
        posted_by=_POSTER,
        material=MaterialId("coal"),
        qty_per_cycle=4,
        interval_ticks=1440,
        duration_cycles=3,
        bid_window_ticks=120,
    )
    w.tick += 200
    b = submit_tender_bid(w, PartyId("settler_001"), r["tender_id"], 80)
    assert b["ok"] is False
    assert "deadline" in b["reason"]


def test_self_bid_rejected() -> None:
    w = _world()
    r = post_tender(
        w,
        posted_by=_POSTER,
        material=MaterialId("coal"),
        qty_per_cycle=4,
        interval_ticks=1440,
        duration_cycles=3,
        bid_window_ticks=2000,
    )
    b = submit_tender_bid(w, _POSTER, r["tender_id"], 80)
    assert b["ok"] is False


def test_tender_awards_to_lowest_bidder_and_creates_supply_contract() -> None:
    w = _world()
    r = post_tender(
        w,
        posted_by=_POSTER,
        material=MaterialId("coal"),
        qty_per_cycle=4,
        interval_ticks=1440,
        duration_cycles=2,
        bid_window_ticks=500,
    )
    tid = r["tender_id"]
    submit_tender_bid(w, PartyId("settler_001"), tid, 80)
    submit_tender_bid(w, PartyId("settler_002"), tid, 70)
    submit_tender_bid(w, PartyId("settler_003"), tid, 85)
    # Advance past the deadline and run the lifecycle ticker.
    w.tick = int(r["bid_deadline_tick"]) + 1
    pre_contracts = list(w.contracts)
    tick_tender_lifecycle(w)
    tender = tender_by_id(w, tid)
    assert tender["status"] == "awarded"
    assert tender["awarded_to"] == "settler_002"
    assert tender["awarded_price_per_unit_cents"] == 70
    assert tender["awarded_contract_id"] is not None
    # A new SupplyContract should exist with matching terms.
    new_contracts = [c for c in w.contracts if c not in pre_contracts]
    assert len(new_contracts) == 1
    supply = new_contracts[0]
    assert supply["kind"] == "supply"
    assert supply["supplier"] == "settler_002"
    assert supply["buyer"] == str(_POSTER)
    assert supply["material"] == "coal"
    assert supply["qty"] == 8  # 4/cycle × 2 cycles
    assert supply["total_price_cents"] == 70 * 8


def test_tender_with_no_bids_expires() -> None:
    w = _world()
    r = post_tender(
        w,
        posted_by=_POSTER,
        material=MaterialId("copper_ingot"),
        qty_per_cycle=2,
        interval_ticks=1440,
        duration_cycles=2,
        bid_window_ticks=100,
    )
    w.tick = int(r["bid_deadline_tick"]) + 1
    tick_tender_lifecycle(w)
    tender = tender_by_id(w, r["tender_id"])
    assert tender["status"] == "expired"


def test_settlers_bid_on_tenders_when_basis_is_low_enough() -> None:
    """Plant a low cost basis for coal and verify settlers submit a tender bid."""
    w = _world()
    settler = PartyId("settler_001")
    # Plant a low basis: 30c per coal (well below the implied price of ~80c).
    record_settler_production(w, settler, "mine_coal", MaterialId("coal"), 100)
    # Override basis directly for determinism (the recorded value depends on labor).
    from realm.settler_cost_basis import ensure_cost_basis_state

    blob = ensure_cost_basis_state(w).setdefault(str(settler), {})
    blob.setdefault("output_basis", {})["coal"] = 30
    blob.setdefault("output_qty_produced", {})["coal"] = 100
    # Post a tender; round the tick to a game-day boundary so the daily ticker fires.
    r = post_tender(
        w,
        posted_by=_POSTER,
        material=MaterialId("coal"),
        qty_per_cycle=4,
        interval_ticks=1440,
        duration_cycles=5,
        bid_window_ticks=2000,
    )
    w.tick = 1440  # day boundary
    tick_settler_tender_bidding(w)
    tender = tender_by_id(w, r["tender_id"])
    bidders = [str(b.get("bidder")) for b in tender.get("bids") or []]
    assert str(settler) in bidders, bidders


def test_tenders_state_survives_round_trip_through_state_io() -> None:
    """Tenders live in scenario_state — verify they serialize cleanly."""
    from realm.state_io import dump_world, load_world

    w = _world()
    post_tender(
        w,
        posted_by=_POSTER,
        material=MaterialId("coal"),
        qty_per_cycle=4,
        interval_ticks=1440,
        duration_cycles=2,
        bid_window_ticks=500,
    )
    snap = dump_world(w)
    w2 = load_world(snap)
    assert len(list_all_tenders(w2)) == 1


def test_tender_pipeline_ledger_conservation() -> None:
    """Bid → award → contract creation must not move money outside the ledger."""
    w = _world()
    pre_total = w.ledger.total_cents()
    r = post_tender(
        w,
        posted_by=_POSTER,
        material=MaterialId("coal"),
        qty_per_cycle=4,
        interval_ticks=1440,
        duration_cycles=2,
        bid_window_ticks=500,
    )
    submit_tender_bid(w, PartyId("settler_001"), r["tender_id"], 80)
    w.tick = int(r["bid_deadline_tick"]) + 1
    tick_tender_lifecycle(w)
    assert w.ledger.total_cents() == pre_total
