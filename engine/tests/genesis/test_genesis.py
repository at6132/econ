"""Genesis scenario — cold-start economy, settlers, population demand."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId
from realm.economy.markets import MARKET_SELLER_REGISTRATION_CENTS
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.core.player_economy import (
    GENESIS_SETTLER_STARTING_CASH_CENTS,
    PLAYER_STARTING_CASH_CENTS,
)
from realm.world.tick import advance_tick
from realm.world import bootstrap_genesis


def _seed_settler_materials(
    w,
    materials: list[tuple[str, int]],
) -> None:
    """Seed bulk construction inputs into settler inventories (exchange no longer lists staples)."""
    for _pid, plot in w.plots.items():
        if plot.owner is not None and str(plot.owner).startswith("settler_"):
            for mid_s, qty in materials:
                w.inventory.add(plot.owner, MaterialId(mid_s), qty)


def test_genesis_bootstrap_ledger_conserved() -> None:
    w = bootstrap_genesis(seed=11, grid_width=10, grid_height=8, settler_count=4)
    assert w.ledger.total_cents() == 100_000_000_000
    player = party_cash_account(PartyId("player"))
    assert w.ledger.balance(player) == PLAYER_STARTING_CASH_CENTS
    # genesis_exchange now lists Tier-2 raws / processed / tool components alongside the
    # original staples & tools — count the materials actually registered so the test
    # tracks bootstrap changes without re-hardcoding the number.
    n_listed = sum(
        1
        for k in w.market_seller_registered
        if str(k).startswith("genesis_exchange|")
    )
    assert n_listed >= 11
    # Sprint 2 adds up to 3 NPC shippers when the world has coastal plots; bootstrap is a
    # no-op when none exist. Count whatever shippers actually got seeded so the assertion
    # tracks `seed_npc_shippers` without re-hardcoding map dependencies.
    from realm.economy.analytics import (
        ANALYTICS_VENDOR_PARTY_ID,
        ANALYTICS_VENDOR_STARTING_CASH_CENTS,
    )
    from realm.genesis.broker import (
        SURVEY_BROKER_PARTY_ID,
        SURVEY_BROKER_STARTING_CASH_CENTS,
    )
    from realm.genesis.consolidator import (
        CONSOLIDATOR_PARTY_ID,
        CONSOLIDATOR_STARTING_CASH_CENTS,
    )
    from realm.genesis.archetypes import (
        FINANCIER_PARTY_ID,
        FINANCIER_STARTING_CASH_CENTS,
        FLIPPER_PARTY_ID,
        FLIPPER_STARTING_CASH_CENTS,
        SHIPPER_PARTY_ID,
        SHIPPER_STARTING_CASH_CENTS,
        SPECIALIST_IRON_PARTY_ID,
        SPECIALIST_TIMBER_PARTY_ID,
    )
    from realm.deals.bank_loans import (
        GENESIS_BANK_PARTY_ID,
        GENESIS_BANK_STARTING_CASH_CENTS,
    )
    from realm.genesis.bank import BANK_STARTING_CASH_CENTS, FIRST_BANK_PARTY_ID
    from realm.genesis.energy import NPC_ENERGY_IDS, NPC_ENERGY_STARTING_CASH_CENTS
    from realm.genesis.road_builders import (
        FRONTIER_ROADS_PARTY_ID,
        FRONTIER_ROADS_STARTING_CASH_CENTS,
    )
    from realm.genesis.construction_firms import (
        GENESIS_CONSTRUCTION_PARTY_ID,
        STARTING_CASH_CENTS as GENESIS_CONSTRUCTION_STARTING_CASH_CENTS,
    )
    from realm.genesis.shippers import NPC_SHIPPER_STARTING_CASH_CENTS

    n_shippers = sum(1 for k in w.parties if str(k).startswith("shipper_"))
    n_genesis_construction = 1 if PartyId(GENESIS_CONSTRUCTION_PARTY_ID) in w.parties else 0
    n_consolidators = 1 if CONSOLIDATOR_PARTY_ID in w.parties else 0
    n_brokers = 1 if SURVEY_BROKER_PARTY_ID in w.parties else 0
    n_analytics = 1 if ANALYTICS_VENDOR_PARTY_ID in w.parties else 0
    n_energy = sum(1 for k in w.parties if k in NPC_ENERGY_IDS)
    n_banks = 1 if FIRST_BANK_PARTY_ID in w.parties else 0
    n_genesis_bank = 1 if GENESIS_BANK_PARTY_ID in w.parties else 0
    n_specialists = sum(
        1
        for pid in (SPECIALIST_IRON_PARTY_ID, SPECIALIST_TIMBER_PARTY_ID)
        if pid in w.parties
    )
    n_flippers = 1 if FLIPPER_PARTY_ID in w.parties else 0
    n_arch_shippers = 1 if SHIPPER_PARTY_ID in w.parties else 0
    n_financiers = 1 if FINANCIER_PARTY_ID in w.parties else 0
    n_road_builders = 1 if FRONTIER_ROADS_PARTY_ID in w.parties else 0
    n_insurer = 1 if PartyId("frontier_insurance_co") in w.parties else 0
    from realm.genesis.home_builders import HOME_BUILDER_STARTING_CASH_CENTS
    from realm.population.laborers import LABORER_STARTING_CASH_CENTS
    from realm.population.stores import NPC_STOREKEEPER_STARTING_CASH_CENTS

    n_laborers = len(w.laborers)
    n_home_builders = sum(1 for p in w.parties if str(p).startswith("frontier_homes_co_"))
    n_storekeeper = 1 if PartyId("genesis_storekeeper") in w.parties else 0
    n_store_parties = sum(1 for p in w.parties if str(p).startswith("store_town_"))
    from realm.population.stores import STORE_PARTY_STARTING_CASH_CENTS

    reserved_out = (
        PLAYER_STARTING_CASH_CENTS  # player
        + 4 * GENESIS_SETTLER_STARTING_CASH_CENTS  # settlers
        # Phase 7A: pop_hub_e/w are removed — no more $50k × 2 cash injections.
        + 88_000  # Tier-3 Margaux (Genesis)
        + 2_000_000  # genesis_exchange operating cash (from reserve)
        + n_store_parties * STORE_PARTY_STARTING_CASH_CENTS  # store bid accounts
        + n_shippers * NPC_SHIPPER_STARTING_CASH_CENTS  # Sprint 2 NPC shippers
        + n_consolidators * CONSOLIDATOR_STARTING_CASH_CENTS  # Sprint 2 consolidator
        + n_energy * NPC_ENERGY_STARTING_CASH_CENTS  # Sprint 3 NPC energy
        + n_brokers * SURVEY_BROKER_STARTING_CASH_CENTS  # Sprint 4 survey broker
        + n_analytics * ANALYTICS_VENDOR_STARTING_CASH_CENTS  # Sprint 4 analytics vendor
        + n_banks * BANK_STARTING_CASH_CENTS  # Sprint 5 first_bank
        + n_genesis_bank * GENESIS_BANK_STARTING_CASH_CENTS  # deal-making genesis bank
        + n_specialists * 1_000_000  # Sprint 5 Specialists ($10K each working cash)
        + n_flippers * FLIPPER_STARTING_CASH_CENTS  # Sprint 5 Flipper
        + n_arch_shippers * SHIPPER_STARTING_CASH_CENTS  # Sprint 5 Cross-Country
        + n_financiers * FINANCIER_STARTING_CASH_CENTS  # Sprint 5 Meridian
        + n_road_builders * FRONTIER_ROADS_STARTING_CASH_CENTS  # Sprint 6 Frontier Roads Co.
        + n_genesis_construction * GENESIS_CONSTRUCTION_STARTING_CASH_CENTS  # Phase 10D NPC builder
        + n_insurer * 10_000_000  # frontier_insurance_co NPC seed ($100k)
        + n_laborers * LABORER_STARTING_CASH_CENTS
        + n_home_builders * HOME_BUILDER_STARTING_CASH_CENTS
        + n_storekeeper * NPC_STOREKEEPER_STARTING_CASH_CENTS
        - n_listed * MARKET_SELLER_REGISTRATION_CENTS  # clearinghouse seller registration per material
    )
    assert w.ledger.balance(system_reserve_account()) == 100_000_000_000 - reserved_out


def test_genesis_settlers_start_production_after_workshops() -> None:
    w = bootstrap_genesis(seed=42, grid_width=12, grid_height=10, settler_count=8)
    _seed_settler_materials(
        w,
        [("lumber", 20), ("stone", 15), ("brick", 10)],
    )
    for _ in range(5000):
        advance_tick(w)
    n = sum(
        1
        for e in w.event_log
        if e.get("kind") == "production_start" and str(e.get("party", "")).startswith("settler_")
    )
    assert n >= 1, "expected at least one settler production_start after workshops complete"


def test_genesis_market_buy_prefers_lowest_price_ask_if_book_unsorted() -> None:
    """Aggressive buy must not trust in-memory list order; shuffle then verify cheapest clip wins.

    Phase 7A: the original variant used ``pop_hub_e`` as the buyer; with hubs
    removed we use ``settler_001`` (any registered party works — the test is
    about the market-matching engine, not about who buys).
    """
    from realm.core.inventory import MatterErr
    from realm.core.ledger import party_cash_account, system_reserve_account
    from realm.economy.markets import cancel_sell_order, market_buy, place_sell_order

    w = bootstrap_genesis(seed=77, grid_width=4, grid_height=4, settler_count=2)
    buyer = PartyId("settler_001")
    # Fund the buyer so it can pay for the clip — drawn from system reserve so
    # ledger total stays conserved.
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(buyer),
        amount_cents=10_000,
    )
    seller = PartyId("settler_001")
    ex = PartyId("genesis_exchange")
    mid = MaterialId("coal")
    key = str(mid)
    for o in list(w.market_asks_by_material.get(key, [])):
        cancel_sell_order(w, o.party, o.order_id)
    from realm.infrastructure.plot_logistics import add_party_plot_stock

    owned_plots = [pid for pid, plot in w.plots.items() if plot.owner == seller]
    if owned_plots:
        ad = add_party_plot_stock(w, seller, mid, 20, preferred_plot=owned_plots[0])
        assert not isinstance(ad, MatterErr)
        assert place_sell_order(w, seller, mid, 12, 44)["ok"] is True
    else:
        ad = w.inventory.add(seller, mid, 20)
        assert not isinstance(ad, MatterErr)
        assert place_sell_order(w, seller, mid, 12, 44)["ok"] is True
    ad2 = w.inventory.add(ex, mid, 50)
    assert not isinstance(ad2, MatterErr)
    assert place_sell_order(w, ex, mid, 14, 70)["ok"] is True
    lst = w.market_asks_by_material[key]
    lst.reverse()
    r = market_buy(w, buyer, mid, 8)
    assert r.get("ok") is True
    assert int(r["filled"]) == 8
    assert int(r["spent_cents"]) == 8 * 44


def test_genesis_skips_tier1_npc_bootstrap() -> None:
    w = bootstrap_genesis(seed=1, grid_width=6, grid_height=4, settler_count=2)
    assert PartyId("npc_grain_vendor") not in w.parties
    assert PartyId("t1_consumer") not in w.parties
    assert PartyId("genesis_exchange") in w.parties


def test_genesis_many_ticks_money_conserved() -> None:
    w = bootstrap_genesis(seed=2, grid_width=8, grid_height=6, settler_count=3)
    total = w.ledger.total_cents()
    for _ in range(800):
        advance_tick(w)
    assert w.ledger.total_cents() == total


def test_genesis_settlers_build_workshops_over_time() -> None:
    w = bootstrap_genesis(seed=5, grid_width=14, grid_height=10, settler_count=10)
    _seed_settler_materials(
        w,
        [("lumber", 25), ("stone", 20), ("brick", 15), ("timber", 10)],
    )
    for _ in range(5000):
        advance_tick(w)
    workshops = [
        b
        for b in w.plot_buildings
        if str(b.get("party", "")).startswith("settler_")
        and b.get("building_id") in ("strip_mine", "timber_yard", "grain_row")
    ]
    assert len(workshops) >= 3


def test_genesis_margaux_script_opener_by_scaled_tick() -> None:
    w = bootstrap_genesis(seed=7, grid_width=8, grid_height=6, settler_count=2)
    for _ in range(841):
        advance_tick(w)
    texts = [str(m.get("text", "")).lower() for m in w.npc_messages_to_player]
    assert any("eastern exchange" in t for t in texts)
    assert w.llm_agents.get("llm_margaux", {}).get("genesis_opener_sent") is True


def test_genesis_settler_workshop_diversity_not_all_strip_mines() -> None:
    w = bootstrap_genesis(seed=13, grid_width=22, grid_height=18, settler_count=40)
    _seed_settler_materials(
        w,
        [("lumber", 30), ("stone", 20), ("brick", 20), ("timber", 15)],
    )
    for _ in range(8000):
        advance_tick(w)
    sm = sum(
        1
        for b in w.plot_buildings
        if str(b.get("party", "")).startswith("settler_") and b.get("building_id") == "strip_mine"
    )
    ty = sum(
        1
        for b in w.plot_buildings
        if str(b.get("party", "")).startswith("settler_") and b.get("building_id") == "timber_yard"
    )
    gr = sum(
        1
        for b in w.plot_buildings
        if str(b.get("party", "")).startswith("settler_") and b.get("building_id") == "grain_row"
    )
    assert sm <= 40, f"expected strip-mine herd softened vs 40 settlers, got {sm}"
    assert ty + gr >= 10, f"expected timber yards + grain rows, ty={ty} gr={gr}"


def test_genesis_exchange_no_staple_listings_at_bootstrap() -> None:
    """Staples are settler-produced; exchange only lists tools and specialty stock."""
    w = bootstrap_genesis(seed=9, grid_width=12, grid_height=10, settler_count=12)
    ex = PartyId("genesis_exchange")
    staples = (
        "grain",
        "timber",
        "coal",
        "lumber",
        "brick",
        "stone",
        "fish",
        "smoked_fish",
    )
    for mat in staples:
        ex_asks = [
            o
            for o in w.market_asks_by_material.get(mat, [])
            if o.party == ex
        ]
        assert not ex_asks, f"exchange should not list {mat} at bootstrap"
    tool_asks = w.market_asks_by_material.get("mining_pick", [])
    assert any(o.party == ex for o in tool_asks)


def test_genesis_world_feed_emits_on_digest_cadence() -> None:
    w = bootstrap_genesis(seed=909, grid_width=6, grid_height=5, settler_count=2)
    for _ in range(961):
        advance_tick(w)
    assert any(e.get("kind") == "world_feed" for e in w.event_log)


def test_genesis_margaux_opener_mirrors_to_world_feed() -> None:
    from realm.core.time_scale import legacy_scaled

    w = bootstrap_genesis(seed=303, grid_width=6, grid_height=5, settler_count=2)
    for _ in range(legacy_scaled(14) + 1):
        advance_tick(w)
    msgs = [e for e in w.event_log if e.get("kind") == "world_feed"]
    assert any("Margaux" in str(e.get("message", "")) for e in msgs), "expected Margaux line on public feed"


def test_genesis_margaux_aux_poll_runs_cleanly_over_multi_day() -> None:
    """Auxiliary beats poll every 120 ticks; long sim should not error and may add lines beyond opener."""
    w = bootstrap_genesis(seed=21, grid_width=10, grid_height=8, settler_count=24)
    for _ in range(4000):
        advance_tick(w)
    texts = [m.get("text", "") for m in w.npc_messages_to_player if m.get("from_party") == "llm_margaux"]
    assert len(texts) >= 1


def test_settler_buys_mining_pick_within_early_ticks() -> None:
    """Settlers source a mining pick from the clearinghouse so Tier-0 extraction can run."""
    w = bootstrap_genesis(seed=403, grid_width=14, grid_height=12, settler_count=8)
    for _ in range(64):
        advance_tick(w)
    picks = sum(
        w.inventory.qty(p, MaterialId("mining_pick"))
        for p in w.parties
        if str(p).startswith("settler_")
    )
    assert picks >= 6


def test_settler_strip_mine_requires_exchange_materials() -> None:
    """After enough ticks, at least one settler completes a strip_mine (bought turnkey mats first)."""
    w = bootstrap_genesis(seed=404, grid_width=16, grid_height=14, settler_count=12)
    _seed_settler_materials(
        w,
        [("lumber", 25), ("stone", 25), ("brick", 20)],
    )
    for _ in range(1800):
        advance_tick(w)
    mines = sum(
        1
        for b in w.plot_buildings
        if str(b.get("party", "")).startswith("settler_") and b.get("building_id") == "strip_mine"
    )
    assert mines >= 1


# Phase 7A — removed `test_genesis_supply_contract_triggers_with_listed_coal`.
# It exercised `tick_genesis_pop_hub_contracts` (hubs proposing supply pacts to
# the player), which was deleted with the pop_hub parties. Hub-proposed pacts
# will be replaced by laborer/entrepreneur-driven demand in Phase 7B/7D.


def test_genesis_settlers_build_secondary_workshops() -> None:
    w = bootstrap_genesis(seed=17, grid_width=24, grid_height=20, settler_count=35)
    _seed_settler_materials(
        w,
        [
            ("lumber", 40),
            ("stone", 30),
            ("brick", 30),
            ("timber", 20),
            ("iron_ingot", 10),
        ],
    )
    for _ in range(15_000):
        advance_tick(w)
    secondary = {
        "power_shed",
        "wood_shop",
        "gristmill",
        "kiln_shed",
        "foundry",
        "stone_works",
    }
    n = sum(
        1
        for b in w.plot_buildings
        if str(b.get("party", "")).startswith("settler_")
        and str(b.get("building_id", "")) in secondary
    )
    assert n >= 8, f"expected settlers to add processing workshops, got {n}"


def test_genesis_subsurface_correlation_mountains_richer_in_iron() -> None:
    """Terrain-correlated rolls bias mountains toward higher iron vs the rest of the grid."""
    from realm.world import generate_plots

    plots = generate_plots(seed=42, width=60, height=45, correlate_subsurface=True)
    ir_mountain = [
        p.subsurface.iron_ore_grade for p in plots.values() if p.terrain.value == "mountain"
    ]
    ir_other = [
        p.subsurface.iron_ore_grade for p in plots.values() if p.terrain.value != "mountain"
    ]
    # Variable parcel layout yields fewer mountain deeds than uniform 60×45 cells.
    assert len(ir_mountain) > 20 and len(ir_other) > 100
    assert sum(ir_mountain) / len(ir_mountain) > sum(ir_other) / len(ir_other)


def test_genesis_full_initial_settler_cohort_no_partial_bootstrap() -> None:
    """All requested settlers exist at t=0 (no random partial first wave)."""
    w = bootstrap_genesis(seed=100, grid_width=20, grid_height=16, settler_count=120)
    n_settlers = sum(1 for p in w.parties if str(p).startswith("settler_"))
    assert n_settlers == 120
    gst = w.scenario_state.get("genesis", {})
    assert gst.get("settler_cap") == 120
    assert gst.get("settler_cycle_enabled") is False


def test_genesis_default_boot_scales_settlers_with_landmass_density() -> None:
    from realm.genesis.settler_cycle import GENESIS_DEFAULT_MAX_SETTLERS
    from realm.population.landmass_density import (
        GENESIS_MIN_BOOT_SETTLERS,
        genesis_settler_count_for_world,
    )

    w = bootstrap_genesis(seed=101)
    n = sum(1 for p in w.parties if str(p).startswith("settler_"))
    expected = genesis_settler_count_for_world(w)
    assert n == expected
    assert n >= GENESIS_MIN_BOOT_SETTLERS
    gst = w.scenario_state.get("genesis", {})
    assert gst.get("settler_cap") == GENESIS_DEFAULT_MAX_SETTLERS
    assert gst.get("settler_cycle_enabled") is True


def test_genesis_explicit_spawn_cap_enables_arrivals() -> None:
    w = bootstrap_genesis(seed=102, grid_width=12, grid_height=10, settler_count=8, settler_spawn_cap=20)
    assert sum(1 for p in w.parties if str(p).startswith("settler_")) == 8
    gst = w.scenario_state.get("genesis", {})
    assert gst.get("settler_cap") == 20
    assert gst.get("settler_cycle_enabled") is True


def test_genesis_bankruptcy_retires_settler_after_streak() -> None:
    from realm.genesis.settler_cycle import BANKRUPT_CASH_CENTS, BANKRUPT_STREAK_TICKS, tick_genesis_settler_lifecycle
    from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account

    w = bootstrap_genesis(seed=201, grid_width=10, grid_height=8, settler_count=4)
    victim = PartyId("settler_001")
    acct = party_cash_account(victim)
    drain = max(0, w.ledger.balance(acct) - 1000)
    tr = w.ledger.transfer(debit=acct, credit=system_reserve_account(), amount_cents=drain)
    assert not isinstance(tr, MoneyErr)
    assert w.ledger.balance(acct) < BANKRUPT_CASH_CENTS
    gst = w.scenario_state.setdefault("genesis", {})
    gst["broke_ticks"] = {str(victim): BANKRUPT_STREAK_TICKS - 1}
    tick_genesis_settler_lifecycle(w)
    assert victim not in w.parties
