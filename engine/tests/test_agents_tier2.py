"""Tier 2 optimizing agents — conservation + per-archetype behavioral checks."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.markets import place_buy_order, place_sell_order
from realm.tick import advance_tick
from realm.world import bootstrap_frontier


def test_tier2_parties_exist_in_bootstrap() -> None:
    w = bootstrap_frontier(seed=1, grid_width=2, grid_height=2)
    for name in (
        "t2_ele_bidstack",
        "t2_lumber_bid",
        "t2_timber_spread",
        "t2_clay_sweep",
        "t2_coal_spread",
    ):
        assert PartyId(name) in w.parties


def test_advance_tick_with_tier2_conserves_ledger_total() -> None:
    w = bootstrap_frontier(seed=90, grid_width=3, grid_height=3)
    t0 = w.ledger.total_cents()
    for _ in range(80):
        advance_tick(w)
    assert w.ledger.total_cents() == t0


def test_tier2_coal_spread_posts_resting_ask_when_tick_mod_23() -> None:
    """Coal spread agent runs on tick % 23 == 0 (including bootstrap tick 0)."""
    w = bootstrap_frontier(seed=11, grid_width=2, grid_height=2)
    party = PartyId("t2_coal_spread")
    assert w.inventory.qty(party, MaterialId("coal")) == 1
    advance_tick(w)
    assert w.inventory.qty(party, MaterialId("coal")) == 0
    asks = w.market_asks_by_material.get("coal", [])
    ours = [a for a in asks if a.party == party]
    assert len(ours) == 1
    assert ours[0].qty >= 1
    assert ours[0].price_per_unit_cents >= 8


def _best_bid_cents(w, material: str) -> int | None:
    bids = w.market_bids_by_material.get(material, [])
    if not bids:
        return None
    return max(b.max_price_per_unit_cents for b in bids)


def _best_ask_cents(w, material: str) -> int | None:
    asks = w.market_asks_by_material.get(material, [])
    if not asks:
        return None
    return min(a.price_per_unit_cents for a in asks)


def test_t2_ele_bidstack_posts_electricity_bid_within_one_tick() -> None:
    """Observable depth: electricity bid from t2_ele_bidstack at tick 0 (cadence % 20)."""
    w = bootstrap_frontier(seed=3, grid_width=2, grid_height=2)
    party = PartyId("t2_ele_bidstack")
    assert w.tick == 0
    advance_tick(w)
    bids = w.market_bids_by_material.get("electricity", [])
    ours = [b for b in bids if b.party == party]
    assert len(ours) >= 1
    assert ours[0].qty >= 1
    assert 18 <= ours[0].max_price_per_unit_cents <= 120


def test_t2_timber_spread_posts_timber_ask_within_one_tick() -> None:
    """Sell-side refresh: timber resting ask after first tick (cadence % 21)."""
    w = bootstrap_frontier(seed=5, grid_width=2, grid_height=2)
    party = PartyId("t2_timber_spread")
    assert w.inventory.qty(party, MaterialId("timber")) == 1
    advance_tick(w)
    assert w.inventory.qty(party, MaterialId("timber")) == 0
    asks = w.market_asks_by_material.get("timber", [])
    ours = [a for a in asks if a.party == party]
    assert len(ours) == 1
    assert ours[0].qty >= 1
    assert ours[0].price_per_unit_cents >= 12


def test_t2_clay_sweep_increases_clay_inventory_within_one_tick() -> None:
    """Conservative sweep: buy one clay when best ask <= 54 (cadence % 18)."""
    w = bootstrap_frontier(seed=7, grid_width=2, grid_height=2)
    party = PartyId("t2_clay_sweep")
    before = w.inventory.qty(party, MaterialId("clay"))
    assert before >= 1
    assert _best_ask_cents(w, "clay") == 54
    advance_tick(w)
    assert w.inventory.qty(party, MaterialId("clay")) == before + 1


def test_t2_lumber_bid_improves_wide_spread_within_25_ticks() -> None:
    """Wide-spread improver: after seeding the book at tick 24, bid moves up by 1¢."""
    w = bootstrap_frontier(seed=13, grid_width=2, grid_height=2)
    player = PartyId("player")
    consumer = PartyId("t1_consumer")
    mat = MaterialId("lumber")
    # Avoid tick 0: tier1 lumber_buyer would lift the ask before tier2 runs.
    for _ in range(24):
        advance_tick(w)
    assert w.tick == 24
    w.inventory.add(player, mat, 2)
    assert place_sell_order(w, player, mat, 1, 95)["ok"] is True
    assert place_buy_order(w, consumer, mat, 1, 70)["ok"] is True
    assert _best_ask_cents(w, "lumber") == 95
    assert _best_bid_cents(w, "lumber") == 70
    t2 = PartyId("t2_lumber_bid")
    advance_tick(w)
    assert w.tick == 25
    ours = [b for b in w.market_bids_by_material.get("lumber", []) if b.party == t2]
    assert len(ours) == 1
    assert ours[0].max_price_per_unit_cents == 71
