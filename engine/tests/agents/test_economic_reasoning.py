"""Unit tests for shared economic reasoning."""

from __future__ import annotations

from realm.agents.economic_reasoning import (
    can_afford_recipe_labor,
    cash_urgency,
    evaluate_staple_purchase,
    liquid_working_capital_cents,
    liquidity_reserve_cents,
    materials_complementary,
    needs_export_dock,
    normalize_output_material,
    party_has_completed_dock,
    partnership_combined_cash_floor,
    operating_float_target_cents,
    recommended_sell_delivery_terms,
    tender_bid_threshold_bps,
)
from realm.economy.market_delivery import DELIVERY_DDP, DELIVERY_FOB
from realm.agents.settler_identity import SettlerPersonality, personality_to_dict
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account
from realm.world import bootstrap_genesis


def test_materials_complementary_from_building_ids() -> None:
    assert materials_complementary("strip_mine", "foundry")
    assert materials_complementary("coal", "iron_ingot")
    assert not materials_complementary("grain_row", "grain_row")


def test_normalize_output_material() -> None:
    assert normalize_output_material("strip_mine") == "coal"
    assert normalize_output_material("iron_ore") == "iron_ore"


def test_liquidity_and_tender_bps_use_personality() -> None:
    w = bootstrap_genesis(seed=1, grid_width=12, grid_height=12, settler_count=2)
    party = PartyId("settler_001")
    store = w.scenario_state.setdefault("settler_identities", {})
    greedy = SettlerPersonality(
        risk_tolerance=0.8,
        specialization_loyalty=0.4,
        social_radius=2,
        patience=0.2,
        greed_index=0.85,
    )
    store[str(party)] = {"personality": personality_to_dict(greedy)}
    assert liquidity_reserve_cents(w, party) > 0
    assert cash_urgency(w, party) >= 0.0
    assert tender_bid_threshold_bps(w, party) >= 10_500


def test_opportunistic_buy_when_asks_below_fair_value() -> None:
    w = bootstrap_genesis(seed=3, grid_width=12, grid_height=12, settler_count=2)
    from realm.actions import claim_plot, survey_plot
    from realm.genesis.consolidator import CONSOLIDATOR_PARTY_ID
    from realm.economy.markets import place_sell_order
    from realm.infrastructure.plot_logistics import add_party_plot_stock

    seller = PartyId("settler_001")
    coal = MaterialId("coal")
    pid = next(
        p.plot_id
        for p in w.plots.values()
        if p.owner is None
        and str(p.terrain.value) not in ("water_deep", "water_shallow")
    )
    claim_plot(w, seller, pid)
    survey_plot(w, seller, pid)
    add_party_plot_stock(w, seller, coal, 20, preferred_plot=pid)
    listed = place_sell_order(w, seller, coal, 5, 50)
    assert listed.get("ok"), listed
    w.tick = 1440  # refresh daily market oracle after listing
    have = int(w.inventory.qty(CONSOLIDATOR_PARTY_ID, coal))
    decision = evaluate_staple_purchase(
        w, CONSOLIDATOR_PARTY_ID, coal, target_stock=12, current_stock=have
    )
    assert decision is not None
    ceiling, qty = decision
    assert ceiling >= 50
    assert qty >= 2


def test_operating_float_target_is_reasonable() -> None:
    w = bootstrap_genesis(seed=4, grid_width=12, grid_height=12, settler_count=2)
    party = PartyId("settler_001")
    target = operating_float_target_cents(w, party)
    assert 1_000 <= target <= 80_000


def test_liquid_working_capital_includes_inventory() -> None:
    w = bootstrap_genesis(seed=5, grid_width=12, grid_height=12, settler_count=2)
    party = PartyId("settler_001")
    cash_only = w.ledger.balance(party_cash_account(party))
    liquid = liquid_working_capital_cents(w, party)
    assert liquid >= cash_only


def test_partnership_cash_floor_scales_with_risk() -> None:
    w = bootstrap_genesis(seed=2, grid_width=12, grid_height=12, settler_count=2)
    a = PartyId("settler_001")
    b = PartyId("settler_002")
    floor = partnership_combined_cash_floor(w, a, b)
    assert 100_000 <= floor <= 250_000


def test_kessler_seeded_with_dock_and_vessel() -> None:
    from realm.genesis.consolidator import CONSOLIDATOR_PARTY_ID

    w = bootstrap_genesis(seed=7, grid_width=12, grid_height=12, settler_count=2)
    assert party_has_completed_dock(w, CONSOLIDATOR_PARTY_ID)
    assert int(w.inventory.qty(CONSOLIDATOR_PARTY_ID, MaterialId("vessel"))) >= 1


def test_needs_export_dock_when_bulk_inventory_and_no_dock() -> None:
    from realm.actions import claim_plot

    w = bootstrap_genesis(seed=8, grid_width=12, grid_height=12, settler_count=2)
    party = PartyId("settler_001")
    plot_id = next(pid for pid, pl in w.plots.items() if pl.owner is None)
    assert claim_plot(w, party, plot_id).get("ok")
    w.plot_output_stock.setdefault(str(plot_id), {})["coal"] = 24
    assert not party_has_completed_dock(w, party)
    assert needs_export_dock(w, party)


def test_inland_settler_lists_fob_without_dock() -> None:
    from realm.actions import claim_plot

    w = bootstrap_genesis(seed=9, grid_width=12, grid_height=12, settler_count=2)
    party = PartyId("settler_001")
    plot_id = next(pid for pid, pl in w.plots.items() if pl.owner is None)
    assert claim_plot(w, party, plot_id).get("ok")
    assert recommended_sell_delivery_terms(w, party, plot_id) == DELIVERY_FOB
