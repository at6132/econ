"""Market loop closure — demand spikes, supply response, disasters, equilibrium."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.economy.market_signals import (
    ask_depth_units,
    bid_depth_units,
    demand_supply_imbalance_bps,
    equilibrium_ask_cents,
    note_supply_capacity_feed,
    scarcity_premium_bps,
)
from realm.economy.markets import market_buy, place_buy_order, place_sell_order
from realm.economy.pricing import exchange_ask_cents, fair_value_cents
from realm.events.world_events import trigger_drought
from realm.genesis.procurement import tick_genesis_standing_demand
from realm.infrastructure.plot_logistics import add_party_plot_stock
from realm.population.stores import tick_store_restock
from realm.production.buildings import build_on_plot
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick
from turnkey_fixtures import grant_turnkey_self_materials


def _claim_open_plot(world, party: PartyId) -> PlotId:
    pid = next(
        p.plot_id
        for p in world.plots.values()
        if p.owner is None and str(p.terrain.value) not in ("water_deep", "water_shallow")
    )
    assert claim_plot(world, party, pid)["ok"]
    assert survey_plot(world, party, pid)["ok"]
    return pid


def _fund_party(world, party: PartyId, cents: int) -> None:
    acct = party_cash_account(party)
    world.ledger.ensure_account(acct)
    tr = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=acct,
        amount_cents=cents,
    )
    assert tr.ok, getattr(tr, "reason", tr)


def test_coal_demand_spike_player_supply_feed_and_equilibrium() -> None:
    """Simulate player-style market play: bid-heavy coal → plant news → ask fill → rebalance."""
    w = bootstrap_genesis(seed=77, settler_count=8, grid_width=28, grid_height=20)
    coal = MaterialId("coal")
    player = PartyId("player")
    snap = ConservationSnapshot.of(w.ledger, w.inventory)

    # Tighten visible supply — demand-heavy book.
    w.market_asks_by_material[str(coal)] = []
    fair = int(fair_value_cents(coal) or exchange_ask_cents(coal, world=w))
    buyers = [
        player,
        PartyId("genesis_storekeeper"),
    ]
    for town in w.towns.values():
        buyers.append(PartyId(f"store_{town.town_id}"))
    for buyer in buyers:
        if buyer not in w.parties:
            continue
        _fund_party(w, buyer, 500_000)
        place_buy_order(w, buyer, coal, 40, fair + 80)

    pre_imb = demand_supply_imbalance_bps(w, coal)
    assert pre_imb > 500, f"expected demand pressure, got {pre_imb} bps"
    assert bid_depth_units(w, coal) > ask_depth_units(w, coal)

    # Player builds strip_mine — capacity announcement hits the feed.
    pid = _claim_open_plot(w, player)
    grant_turnkey_self_materials(w, player, "strip_mine", plot_id=pid)
    res = build_on_plot(w, player, pid, "strip_mine", "turnkey")
    assert res.get("ok"), res
    note_supply_capacity_feed(w, "player", building_id="strip_mine", output_material=coal)
    feed = [
        e
        for e in w.event_log
        if e.get("kind") == "world_feed" and e.get("feed_source") == "supply_capacity"
    ]
    assert feed, "strip_mine capacity should emit supply_capacity feed"

    # Player lists bulk coal at equilibrium-target price.
    add_party_plot_stock(w, player, coal, 60, preferred_plot=pid)
    pre_ask_depth = ask_depth_units(w, coal)
    eq_px = equilibrium_ask_cents(w, coal)
    list_res = place_sell_order(w, player, coal, 35, eq_px, from_plot_id=pid)
    assert list_res.get("ok"), list_res
    post_list_ask = ask_depth_units(w, coal)
    assert post_list_ask > pre_ask_depth, "player supply should add resting ask depth"

    # Aggressive buyers walk the book — imbalance should ease vs spike.
    for buyer in buyers[:3]:
        if buyer in w.parties:
            market_buy(w, buyer, coal, 8, max_price_per_unit_cents=eq_px + 20)
    post_imb = demand_supply_imbalance_bps(w, coal)
    assert post_imb <= pre_imb, f"supply listing should ease imbalance ({pre_imb} → {post_imb})"
    assert ask_depth_units(w, coal) < post_list_ask or post_imb < pre_imb

    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_standing_procurement_maintains_bids_under_scarcity() -> None:
    """NPC procurement posts standing bids when imbalance exceeds threshold."""
    w = bootstrap_genesis(seed=55, settler_count=6, grid_width=24, grid_height=18)
    coal = MaterialId("coal")
    w.market_asks_by_material[str(coal)] = []
    fair = int(fair_value_cents(coal) or exchange_ask_cents(coal, world=w))
    _fund_party(w, PartyId("genesis_storekeeper"), 400_000)
    place_buy_order(w, PartyId("genesis_storekeeper"), coal, 30, fair + 60)
    pre_bids = bid_depth_units(w, coal)
    w.tick = TICKS_PER_GAME_DAY
    tick_genesis_standing_demand(w)
    post_bids = bid_depth_units(w, coal)
    assert post_bids >= pre_bids


def test_drought_raises_grain_demand_pressure() -> None:
    """Exogenous drought shock increases grain bid-side pressure on the book."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=6)
    grain = MaterialId("grain")
    pre_imb = demand_supply_imbalance_bps(w, grain)
    trigger_drought(w, island_id=1, severity=0.85, duration_days=14)
    drought_feed = [e for e in w.event_log if e.get("kind") == "world_feed" and "drought" in str(e.get("message", "")).lower()]
    assert drought_feed, "drought should emit world_feed"
    w.market_asks_by_material[str(grain)] = []
    fair = int(fair_value_cents(grain) or exchange_ask_cents(grain, world=w))
    for town in w.towns.values():
        sp = PartyId(f"store_{town.town_id}")
        if sp in w.parties:
            _fund_party(w, sp, 200_000)
            place_buy_order(w, sp, grain, 25, fair + int(40 * 0.85))
    for _ in range(TICKS_PER_GAME_DAY * 2):
        advance_tick(w)
    post_imb = demand_supply_imbalance_bps(w, grain)
    assert post_imb >= pre_imb
    assert scarcity_premium_bps(w, grain) >= 0


def test_store_revenue_reinvest_posts_bids_when_imbalanced() -> None:
    """Shelf revenue from prior day reinvests into wholesale bids on hot materials."""
    w = bootstrap_genesis(seed=11, settler_count=10)
    town = next(iter(w.towns.values()))
    pid = town.store_plots[0]
    store_party = PartyId(f"store_{town.town_id}")
    _ensure_store_party_cash(w, store_party)
    w.scenario_state.setdefault("store_sales_history", {})[str(pid)] = [
        {"day": 0, "sales": {"grain": 18, "coal": 12}},
    ]
    w.store_revenue_today[str(pid)] = 25_000
    w.market_asks_by_material["grain"] = []
    w.market_bids_by_material["grain"] = []
    pre = bid_depth_units(w, MaterialId("grain"))
    w.tick = TICKS_PER_GAME_DAY
    tick_store_restock(w)
    post = bid_depth_units(w, MaterialId("grain"))
    assert post > pre


def _ensure_store_party_cash(world, store_party: PartyId) -> None:
    if store_party not in world.parties:
        world.parties.add(store_party)
    acct = party_cash_account(store_party)
    world.ledger.ensure_account(acct)
    if world.ledger.balance(acct) < 100_000:
        tr = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=500_000,
        )
        assert tr.ok, getattr(tr, "reason", tr)
