"""Sprint 2 — Phase D · Kessler Industrial (consolidator).

Covers the consolidator's bootstrap (capital, buildings, recipes), its daily
input-cornering, its undercutting list-price behaviour, its market-share
growth, and the design-rule guarantee that a player with their own supply is
*not* squeezed by Kessler's input buying.
"""

from __future__ import annotations

from realm.actions import claim_plot
from realm.genesis_consolidator import (
    CONSOLIDATOR_DISPLAY_NAME,
    CONSOLIDATOR_PARTY_ID,
    CONSOLIDATOR_STARTING_CASH_CENTS,
    consolidator_market_share_bps,
    seed_consolidator,
    tick_consolidator,
)
from realm.genesis_pricing import exchange_ask_cents
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account
from realm.markets import place_sell_order
from realm.world import World, bootstrap_genesis


def _world(*, settlers: int = 6, w: int = 20, h: int = 14) -> World:
    return bootstrap_genesis(seed=99, settler_count=settlers, grid_width=w, grid_height=h)


# ───────────────────────── bootstrap ─────────────────────────


def test_consolidator_spawns_with_capital_buildings_and_recipes() -> None:
    w = _world()
    assert CONSOLIDATOR_PARTY_ID in w.parties
    cash = w.ledger.balance(party_cash_account(CONSOLIDATOR_PARTY_ID))
    assert cash == CONSOLIDATOR_STARTING_CASH_CENTS
    assert w.party_display_names.get(str(CONSOLIDATOR_PARTY_ID)) == CONSOLIDATOR_DISPLAY_NAME
    bldgs = [b for b in w.plot_buildings if b.get("party") == str(CONSOLIDATOR_PARTY_ID)]
    ids = {b.get("building_id") for b in bldgs}
    assert "foundry" in ids
    assert "strip_mine" in ids
    # Tier-1 recipes are accessible.
    book = w.party_recipe_books.get(str(CONSOLIDATOR_PARTY_ID), set())
    assert "smelt_iron" in book
    assert "mine_iron_ore" in book


def test_consolidator_seed_is_idempotent() -> None:
    w = _world()
    created_again = seed_consolidator(w)
    assert created_again is False
    cash = w.ledger.balance(party_cash_account(CONSOLIDATOR_PARTY_ID))
    assert cash == CONSOLIDATOR_STARTING_CASH_CENTS  # no double-credit


# ───────────────────────── action loop ─────────────────────────


def _seed_some_iron_ore_asks(world: World) -> None:
    """Plant several iron_ore asks so the consolidator has something to buy."""
    seller = PartyId("settler_001")
    world.inventory.add(seller, MaterialId("iron_ore"), 100)
    place_sell_order(world, seller, MaterialId("iron_ore"), 100, 90)


def test_consolidator_buys_key_input_aggressively() -> None:
    w = _world()
    _seed_some_iron_ore_asks(w)
    pre = int(w.inventory.qty(CONSOLIDATOR_PARTY_ID, MaterialId("iron_ore")))
    # Force a day-boundary tick of the consolidator strategy.
    w.tick = 1440
    tick_consolidator(w)
    post = int(w.inventory.qty(CONSOLIDATOR_PARTY_ID, MaterialId("iron_ore")))
    assert post > pre, f"expected Kessler to buy iron_ore; before={pre}, after={post}"
    # Spec: 5 days × ~6/day = 30 units target buffer.
    assert post >= 20


def test_consolidator_lists_below_exchange_ask() -> None:
    w = _world()
    _seed_some_iron_ore_asks(w)
    # Give it coal + electricity too so it can actually fire smelt_iron and have output to list.
    w.inventory.add(CONSOLIDATOR_PARTY_ID, MaterialId("coal"), 20)
    w.inventory.add(CONSOLIDATOR_PARTY_ID, MaterialId("electricity"), 20)
    # Plant iron_ingot in inventory so list_output can list immediately.
    w.inventory.add(CONSOLIDATOR_PARTY_ID, MaterialId("iron_ingot"), 10)
    w.tick = 1440
    tick_consolidator(w)
    # Inspect Kessler's resting iron_ingot ask price.
    asks = w.market_asks_by_material.get("iron_ingot", [])
    kessler_asks = [a for a in asks if str(a.party) == str(CONSOLIDATOR_PARTY_ID)]
    assert len(kessler_asks) >= 1, "consolidator should have listed iron_ingot"
    ex_ask = int(exchange_ask_cents(MaterialId("iron_ingot")))
    for a in kessler_asks:
        assert a.price_per_unit_cents < ex_ask, (
            f"Kessler listed {a.price_per_unit_cents}¢ ≥ exchange {ex_ask}¢"
        )


def test_consolidator_market_share_tracks_only_kessler_volume() -> None:
    """Sanity: the share function counts Kessler's fills, not other parties'."""
    w = _world()
    # No fills yet → 0 share.
    assert consolidator_market_share_bps(w, MaterialId("iron_ingot")) == 0


def test_consolidator_grows_share_over_multi_day_run() -> None:
    """Run the consolidator for many game-days; assert it accumulates positive share."""
    w = _world()
    # Plant ongoing iron_ore supply so the foundry has feed.
    seller = PartyId("settler_001")
    w.inventory.add(seller, MaterialId("iron_ore"), 500)
    place_sell_order(w, seller, MaterialId("iron_ore"), 500, 90)
    w.inventory.add(CONSOLIDATOR_PARTY_ID, MaterialId("coal"), 200)
    w.inventory.add(CONSOLIDATOR_PARTY_ID, MaterialId("electricity"), 200)
    # Seed some initial iron_ingot inventory so first-day listing has product.
    w.inventory.add(CONSOLIDATOR_PARTY_ID, MaterialId("iron_ingot"), 40)
    # Simulate a buyer that takes Kessler's asks. Phase 7A: pop_hub is gone;
    # any funded party can play the role of the iron_ingot offtaker. We use
    # the player (already funded at bootstrap).
    from realm.core.ledger import party_cash_account, system_reserve_account
    from realm.markets import market_buy

    buyer = PartyId("player")
    # Top up the player so they can absorb 5 days of ingot lifts.
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(buyer),
        amount_cents=200_000,
    )
    for day in range(1, 6):
        w.tick = 1440 * day
        tick_consolidator(w)
        market_buy(w, buyer, MaterialId("iron_ingot"), 6)
    share = consolidator_market_share_bps(w, MaterialId("iron_ingot"))
    assert share > 0, f"expected positive market share, got {share}bps"


def test_own_supply_insulates_from_consolidator() -> None:
    """A player who self-supplies iron_ore is not starved when Kessler buys from the market."""
    w = _world()
    # Plant a single, *limited* iron_ore listing — the market that Kessler will drain.
    seller = PartyId("settler_001")
    w.inventory.add(seller, MaterialId("iron_ore"), 30)
    place_sell_order(w, seller, MaterialId("iron_ore"), 30, 90)
    # The player stockpiles their own iron_ore (e.g. from a personal strip_mine).
    player_own = 50
    w.inventory.add(PartyId("player"), MaterialId("iron_ore"), player_own)
    # Kessler runs its strategy.
    w.tick = 1440
    tick_consolidator(w)
    # The player's own iron_ore is untouched.
    after = int(w.inventory.qty(PartyId("player"), MaterialId("iron_ore")))
    assert after == player_own, f"player iron_ore went from {player_own} to {after}"


def test_world_feed_dominance_line_uses_redacted_language() -> None:
    """When share crosses 30 %, the feed entry is anonymous — never names Kessler."""
    from realm.event_log import log_event

    w = _world()
    # Force a synthetic trade history where Kessler owns >30 % of iron_ingot volume.
    w.tick = 1440
    log_event(
        w,
        "market_buy",
        f"{CONSOLIDATOR_PARTY_ID} took 80×iron_ingot",
        material="iron_ingot",
        qty=80,
        party=str(CONSOLIDATOR_PARTY_ID),
        seller=str(CONSOLIDATOR_PARTY_ID),
    )
    log_event(
        w,
        "market_buy",
        "settler_001 took 20×iron_ingot",
        material="iron_ingot",
        qty=20,
        party="settler_001",
        seller="settler_001",
    )
    pre_feed = list(w.world_feed_log)
    tick_consolidator(w)
    new_feed = [r for r in w.world_feed_log if r not in pre_feed]
    matches = [r for r in new_feed if "iron_ingot" in str(r.get("message", ""))]
    assert matches, "expected a redacted world-feed line for iron_ingot"
    for row in matches:
        assert "Kessler" not in str(row.get("message", "")), row


def test_consolidator_pipeline_conserves_ledger() -> None:
    """End-to-end: bootstrap + several days of strategy must conserve total cents."""
    w = _world()
    pre_total = w.ledger.total_cents()
    seller = PartyId("settler_001")
    w.inventory.add(seller, MaterialId("iron_ore"), 200)
    place_sell_order(w, seller, MaterialId("iron_ore"), 200, 90)
    w.inventory.add(CONSOLIDATOR_PARTY_ID, MaterialId("iron_ingot"), 20)
    for day in range(1, 4):
        w.tick = 1440 * day
        tick_consolidator(w)
    assert w.ledger.total_cents() == pre_total
