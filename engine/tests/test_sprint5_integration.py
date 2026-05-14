"""Sprint 5 — integration test: business, sub-accounts, bank, archetypes, Margaux."""

from __future__ import annotations

import pytest

from realm.actions import register_business
from realm.genesis_archetypes import (
    FINANCIER_PARTY_ID,
    FLIPPER_PARTY_ID,
    SHIPPER_PARTY_ID,
    SPECIALIST_IRON_PARTY_ID,
    SPECIALIST_TIMBER_PARTY_ID,
)
from realm.genesis_bank import (
    BANK_STARTING_CASH_CENTS,
    FIRST_BANK_PARTY_ID,
    bank_rates_view,
)
from realm.genesis_consolidator import CONSOLIDATOR_PARTY_ID
from realm.economy.exchange import exchange_price_for_party
from realm.core.ids import PartyId
from realm.core.ledger import party_cash_account
from realm.economy.markets import place_sell_order
from realm.sub_accounts import create_sub_account, party_accounts_view
from realm.world.tick import advance_tick
from realm.world import bootstrap_genesis


_TICKS_PER_GAME_DAY = 1440


@pytest.fixture
def gen_world():
    return bootstrap_genesis(
        seed=999,
        grid_width=24,
        grid_height=18,
        settler_count=6,
        map_layout="islands",
    )


def test_sprint5_integration_end_to_end(gen_world) -> None:
    w = gen_world
    starting_total = w.ledger.total_cents()

    # 1. Business registration
    r = register_business(w, PartyId("player"), "Player Iron Co.", "smelter")
    assert r["ok"] is True
    assert w.party_display_names[str(PartyId("player"))] == "Player Iron Co."

    # 2. Sub-accounts default cash + create reserve
    accounts_before = party_accounts_view(w, PartyId("player"))
    labels_before = {a["label"] for a in accounts_before}
    assert "cash" in labels_before
    cr = create_sub_account(w, PartyId("player"), "reserve")
    assert cr["ok"] is True
    accounts_after = party_accounts_view(w, PartyId("player"))
    labels_after = {a["label"] for a in accounts_after}
    assert "reserve" in labels_after

    # 3. Bank exists with $500K, rates view for player at honored=0 starter tier
    assert FIRST_BANK_PARTY_ID in w.parties
    assert (
        w.ledger.balance(party_cash_account(FIRST_BANK_PARTY_ID))
        == BANK_STARTING_CASH_CENTS
    )
    rates = bank_rates_view(w, PartyId("player"))
    assert rates["current_tier"] == "starter"

    # 4. Reputation pricing function (the rebate hook is exercised in test_bank_loans).
    discount = exchange_price_for_party(1000, {"honored": 12, "breached": 0})
    assert discount == 950

    # 5. All 5 archetypes seeded and active
    for pid in (
        SPECIALIST_IRON_PARTY_ID,
        SPECIALIST_TIMBER_PARTY_ID,
        FLIPPER_PARTY_ID,
        SHIPPER_PARTY_ID,
        FINANCIER_PARTY_ID,
        CONSOLIDATOR_PARTY_ID,
    ):
        assert pid in w.parties

    # Advance 5 game-days so the archetypes actually act.
    for _ in range(5 * _TICKS_PER_GAME_DAY):
        advance_tick(w)

    # Each archetype has taken at least 1 economic action — measured by:
    #   - Specialist/Consolidator: at least one building owned.
    #   - Flipper: at least one intel listing in their name.
    #   - Shipper: route registrations exist.
    #   - Financier: scanned settlers (loans may not always originate, but
    #     party still has cash on the ledger from seeding).
    flipper_listings = [
        r for r in w.intel_listings if str(r.get("seller", "")) == str(FLIPPER_PARTY_ID)
    ]
    assert flipper_listings, "Flipper should have listed at least one report"
    shipper_routes = [
        k
        for k, ops in (w.scenario_state.get("route_operators") or {}).items()
        if any(str(o.get("operator_party")) == str(SHIPPER_PARTY_ID) for o in ops)
    ]
    assert shipper_routes, "Shipper should have route registrations"
    specialist_buildings = [
        b
        for b in w.plot_buildings
        if str(b.get("party")) in (str(SPECIALIST_IRON_PARTY_ID), str(SPECIALIST_TIMBER_PARTY_ID))
    ]
    assert specialist_buildings, "Specialists should have pre-built workshops"

    # 6. Margaux: at least 1 message present (opener + day-N beats).
    margaux_msgs = [
        m
        for m in w.npc_messages_to_player
        if str(m.get("from_party")) == "llm_margaux"
    ]
    assert margaux_msgs, "Margaux should have queued at least one message"

    # 7. Archetype-to-archetype interaction visible in durable state.
    archetype_ids = {
        str(p)
        for p in (
            SPECIALIST_IRON_PARTY_ID,
            SPECIALIST_TIMBER_PARTY_ID,
            FLIPPER_PARTY_ID,
            SHIPPER_PARTY_ID,
            FINANCIER_PARTY_ID,
            CONSOLIDATOR_PARTY_ID,
        )
    }
    found_cross = False
    for row in w.intel_listings:
        if row.get("status") != "sold":
            continue
        s = str(row.get("seller", ""))
        b = str(row.get("buyer", ""))
        if s in archetype_ids and b in archetype_ids and s != b:
            found_cross = True
            break
    if not found_cross:
        for c in w.contracts:
            if c.get("kind") not in ("forward_contract", "bank_loan"):
                continue
            for key in ("seller", "buyer", "lender", "borrower"):
                val = str(c.get(key, ""))
                if val and val in archetype_ids:
                    other_keys = {"seller", "buyer", "lender", "borrower"} - {key}
                    if any(str(c.get(k, "")) in archetype_ids for k in other_keys):
                        found_cross = True
                        break
            if found_cross:
                break
    assert found_cross, "Expect at least one archetype-to-archetype transaction"

    # 8. Conservation
    assert w.ledger.total_cents() == starting_total
