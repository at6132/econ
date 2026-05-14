"""Sprint 5 — Phase D tests: the five Tier-2 archetypes."""

from __future__ import annotations

import dataclasses

import pytest

from realm.genesis_archetypes import (
    FINANCIER_PARTY_ID,
    FLIPPER_PARTY_ID,
    SHIPPER_PARTY_ID,
    SPECIALIST_IRON_PARTY_ID,
    SPECIALIST_TIMBER_PARTY_ID,
)
from realm.genesis_consolidator import CONSOLIDATOR_PARTY_ID
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.regions import all_region_ids, route_key
from realm.route_operators import list_route_operators
from realm.tick import advance_tick
from realm.world import bootstrap_genesis


_TICKS_PER_GAME_DAY = 1440


@pytest.fixture
def gen_world():
    # Force the islands layout so coastal plots exist (Kessler needs one).
    return bootstrap_genesis(
        seed=900,
        grid_width=24,
        grid_height=18,
        settler_count=6,
        map_layout="islands",
    )


def _advance_game_days(w, days: int) -> None:
    for _ in range(int(days * _TICKS_PER_GAME_DAY)):
        advance_tick(w)


def test_all_five_archetypes_at_bootstrap(gen_world) -> None:
    w = gen_world
    for pid in (
        SPECIALIST_IRON_PARTY_ID,
        SPECIALIST_TIMBER_PARTY_ID,
        FLIPPER_PARTY_ID,
        SHIPPER_PARTY_ID,
        FINANCIER_PARTY_ID,
        CONSOLIDATOR_PARTY_ID,
    ):
        assert pid in w.parties, f"{pid} should be seeded at genesis"


def test_specialist_never_leaves_vertical(gen_world) -> None:
    """Specialist doesn't construct any building outside its workshop type."""
    w = gen_world
    _advance_game_days(w, 2)
    iron_buildings = [
        b
        for b in w.plot_buildings
        if str(b.get("party")) == str(SPECIALIST_IRON_PARTY_ID)
    ]
    for b in iron_buildings:
        assert b.get("building_id") == "foundry"
    timber_buildings = [
        b
        for b in w.plot_buildings
        if str(b.get("party")) == str(SPECIALIST_TIMBER_PARTY_ID)
    ]
    for b in timber_buildings:
        assert b.get("building_id") == "wood_shop"


def test_flipper_claims_and_lists_reports(gen_world) -> None:
    """Prospect Holdings: after a few game-days, has survey reports listed on the
    Intelligence market."""
    w = gen_world
    _advance_game_days(w, 3)
    flipper_listings = [
        row
        for row in w.intel_listings
        if str(row.get("seller", "")) == str(FLIPPER_PARTY_ID)
        and row.get("status") == "active"
    ]
    assert flipper_listings, "Prospect Holdings should have at least one active listing"


def test_shipper_registered_all_routes(gen_world) -> None:
    w = gen_world
    regions = all_region_ids()
    expected_pairs = 0
    registered_pairs = 0
    for i, ra in enumerate(regions):
        for rb in regions[i + 1 :]:
            expected_pairs += 1
            ops = list_route_operators(w, route_key(ra, rb))
            if any(str(o.get("operator_party")) == str(SHIPPER_PARTY_ID) for o in ops):
                registered_pairs += 1
    assert expected_pairs == 36
    assert registered_pairs == 36, (
        f"Cross-Country Logistics should register all 36 routes; got {registered_pairs}"
    )


def test_financier_loans_to_cash_poor_settler(gen_world) -> None:
    w = gen_world
    cash_poor = next(p for p in w.parties if str(p).startswith("settler_"))
    # Drain settler to make them cash-poor.
    drain = w.ledger.balance(party_cash_account(cash_poor))
    if drain > 0:
        w.ledger.transfer(
            debit=party_cash_account(cash_poor),
            credit=system_reserve_account(),
            amount_cents=drain,
        )
    # Pretend the settler produced revenue today (recent market_match seller event).
    w.event_log.append(
        {
            "tick": int(w.tick),
            "kind": "market_match",
            "seller": str(cash_poor),
            "qty": 8,
            "price_per_unit_cents": 5_000,
        }
    )
    # Tick to the next game-day boundary to trigger Meridian.
    _advance_game_days(w, 1)
    loans_to_settler = [
        c
        for c in w.contracts
        if c.get("kind") == "bank_loan"
        and str(c.get("borrower")) == str(cash_poor)
        and str(c.get("lender")) == str(FINANCIER_PARTY_ID)
    ]
    assert loans_to_settler, (
        "Meridian Capital should extend a loan to a cash-poor profitable settler"
    )


def test_consolidator_uses_forward_contracts(gen_world) -> None:
    """Kessler upgrade: at least one bank_loan-style forward contract is active."""
    w = gen_world
    _advance_game_days(w, 7)
    kessler_forwards = [
        c
        for c in w.contracts
        if c.get("kind") == "forward_contract"
        and (
            str(c.get("buyer")) == str(CONSOLIDATOR_PARTY_ID)
            or str(c.get("seller")) == str(CONSOLIDATOR_PARTY_ID)
        )
    ]
    assert kessler_forwards, (
        "Kessler Industrial should propose at least one forward contract"
    )


def test_archetypes_interact_with_each_other(gen_world) -> None:
    """Tick several days; expect at least one transaction between two archetype
    parties (e.g. Specialist buys Flipper's survey report). The event_log is
    capped, so look at durable state too."""
    w = gen_world
    _advance_game_days(w, 5)
    archetype_ids = {
        str(SPECIALIST_IRON_PARTY_ID),
        str(SPECIALIST_TIMBER_PARTY_ID),
        str(FLIPPER_PARTY_ID),
        str(SHIPPER_PARTY_ID),
        str(FINANCIER_PARTY_ID),
        str(CONSOLIDATOR_PARTY_ID),
    }
    # 1. Sold intel listings where both seller and buyer are archetypes.
    for row in w.intel_listings:
        if row.get("status") != "sold":
            continue
        seller = str(row.get("seller", ""))
        buyer = str(row.get("buyer", ""))
        if seller in archetype_ids and buyer in archetype_ids and seller != buyer:
            return
    # 2. Forward contracts where both sides are archetypes.
    for c in w.contracts:
        if c.get("kind") != "forward_contract":
            continue
        seller = str(c.get("seller", ""))
        buyer = str(c.get("buyer", ""))
        if seller in archetype_ids and buyer in archetype_ids and seller != buyer:
            return
    # 3. Fall back to scanning recent event log for any cross-archetype activity.
    for ev in w.event_log:
        kind = ev.get("kind") or ""
        if kind in {
            "market_match",
            "survey_report_transferred",
            "intel_listing_sold",
            "contract_forward_propose",
            "bank_loan_apply",
        }:
            a = str(ev.get("buyer") or ev.get("from_party") or ev.get("borrower") or "")
            b = str(ev.get("seller") or ev.get("to_party") or ev.get("lender") or "")
            if a in archetype_ids and b in archetype_ids and a != b:
                return
    raise AssertionError(
        "Expect at least one archetype-to-archetype transaction within 5 game-days"
    )
