"""Phase 7D — stores, laborer spending, consumer economy, conservation."""

from __future__ import annotations

import pytest

from realm.actions import claim_plot
from realm.production.buildings import BUILDINGS, build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.population.laborers import (
    LABORER_STARTING_CASH_CENTS,
    TICKS_PER_GAME_DAY,
    laborer_cash_account,
)
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.population.stores import (
    FOOD_PER_UNIT,
    FUEL_PER_UNIT,
    GENESIS_STORE_RETAIL_CENTS,
    NPC_STORE_COAL_QTY,
    NPC_STORE_GRAIN_QTY,
    SPENDING_TRIGGER_NEED,
    is_store_plot,
    seed_genesis_npc_stores,
    set_store_price,
    stock_store,
    store_inventory_qty,
    store_price_cents,
    stores_for_town,
    tick_laborer_spending,
    withdraw_store_stock,
)
from realm.world.terrain import Terrain
from realm.population.towns import town_for_plot
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick
from turnkey_fixtures import grant_turnkey_self_materials


# ───────────────────────── seeded NPC stores ─────────────────────────


def test_genesis_store_inventory_counts_as_store_plot():
    """Bootstrap stores must be discoverable even without a plot_buildings row."""
    w = bootstrap_genesis(seed=7, settler_count=4)
    pid = next(iter(w.store_inventories.keys()))
    assert int(w.store_inventories[pid].get("grain", 0)) > 0
    assert is_store_plot(w, PlotId(pid))


def test_laborers_buy_food_from_genesis_stores_over_two_days():
    w = bootstrap_genesis(seed=7, settler_count=10)
    for tid, town in w.towns.items():
        stores = stores_for_town(w, tid)
        assert len(stores) > 0, f"Town {tid} ({town.name}) has no discoverable stores"
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    for _ in range(2 * 1440):
        advance_tick(w)
    purchases = sum(
        1
        for e in w.event_log
        if e.get("kind") in ("store_purchase", "laborer_purchase")
    )
    assert purchases > 0, "No store purchases after 2 days"
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_store_restocks_after_depletion():
    w = bootstrap_genesis(seed=1, settler_count=10)
    pid = list(w.store_inventories.keys())[0]
    w.store_inventories[pid]["grain"] = 0
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    for _ in range(1440):
        advance_tick(w)
    assert int(w.store_inventories[pid].get("grain", 0)) > 0
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_tick_store_restock_fires_on_day_boundary():
    w = bootstrap_genesis(seed=3, settler_count=4)
    pid = next(iter(w.towns.values())).store_plots[0]
    w.store_inventories[str(pid)]["grain"] = 0
    w.tick = 1439
    advance_tick(w)
    assert int(w.store_inventories[str(pid)].get("grain", 0)) > 0


def test_genesis_seeds_one_npc_store_per_town():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    assert len(w.towns) == 4
    for t in w.towns.values():
        active_stores = stores_for_town(w, t.town_id)
        assert len(active_stores) == 1


def test_npc_stores_carry_grain_and_coal_with_subsistence_prices():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    grain_mid = MaterialId("grain")
    coal_mid = MaterialId("coal")
    for t in w.towns.values():
        for sp in t.store_plots:
            assert store_inventory_qty(w, sp, grain_mid) == NPC_STORE_GRAIN_QTY
            assert store_inventory_qty(w, sp, coal_mid) == NPC_STORE_COAL_QTY
            assert store_price_cents(w, sp, grain_mid) == GENESIS_STORE_RETAIL_CENTS["grain"]
            assert store_price_cents(w, sp, coal_mid) == GENESIS_STORE_RETAIL_CENTS["coal"]


def test_broke_laborer_can_buy_one_grain_when_two_units_unaffordable():
    """Partial refill: 224¢ must still buy one grain at 60¢, not fail on 2×60."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    lab = next(l for l in w.laborers.values() if l.home_town)
    acct = laborer_cash_account(lab.laborer_id)
    bal = w.ledger.balance(acct)
    w.ledger.transfer(debit=acct, credit=system_reserve_account(), amount_cents=bal)
    w.ledger.transfer(debit=system_reserve_account(), credit=acct, amount_cents=224)
    lab.cash_cents = 224
    lab.needs["food"] = 0.30
    w.tick += TICKS_PER_GAME_DAY
    stats = tick_laborer_spending(w)
    assert stats["purchases"] >= 1
    assert lab.needs["food"] > 0.30


# ───────────────────────── owner actions ─────────────────────────


def _build_player_store_in_a_town(
    w, *, town_id: str | None = None
) -> tuple[PartyId, PlotId]:
    """Helper: claim & build a turnkey store next to an existing town."""
    player = PartyId("player")
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(player),
        amount_cents=1_000_000,
    )
    grant_turnkey_self_materials(w, player, "store")
    # Pick a town to plant in.
    town = (
        w.towns[town_id]
        if town_id is not None
        else next(iter(w.towns.values()))
    )
    # Find an unowned plot adjacent to the town center.
    center = w.plots[town.center_plot]
    target: PlotId | None = None
    for p in w.plots.values():
        if p.owner is not None:
            continue
        if p.terrain in (Terrain.WATER_DEEP, Terrain.WATER_SHALLOW):
            continue
        if max(abs(p.x - center.x), abs(p.y - center.y)) > 8:
            continue
        target = p.plot_id
        break
    assert target is not None, "no candidate plot near town center"
    assert claim_plot(w, player, target)["ok"]
    res = build_on_plot(w, player, target, "store", build_mode="turnkey")
    assert res["ok"], res
    w.tick = max(int(w.tick), int(res["completes_at_tick"]) + 1)
    return player, target


def test_stock_store_moves_inventory_and_records_revenue_account():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player, plot = _build_player_store_in_a_town(w)
    ad = w.inventory.add(player, MaterialId("grain"), 50)
    assert not isinstance(ad, MatterErr)
    res = stock_store(w, player, plot, MaterialId("grain"), 30)
    assert res["ok"], res
    assert store_inventory_qty(w, plot, MaterialId("grain")) == 30
    assert w.inventory.qty(player, MaterialId("grain")) == 20


def test_withdraw_store_stock_returns_to_owner_inventory():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player, plot = _build_player_store_in_a_town(w)
    w.inventory.add(player, MaterialId("coal"), 40)
    stock_store(w, player, plot, MaterialId("coal"), 40)
    res = withdraw_store_stock(w, player, plot, MaterialId("coal"), 10)
    assert res["ok"]
    assert store_inventory_qty(w, plot, MaterialId("coal")) == 30
    assert w.inventory.qty(player, MaterialId("coal")) == 10


def test_stock_rejected_when_party_does_not_own_plot():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player, plot = _build_player_store_in_a_town(w)
    other = PartyId("settler_001")
    w.inventory.add(other, MaterialId("grain"), 5)
    res = stock_store(w, other, plot, MaterialId("grain"), 5)
    assert not res["ok"]
    assert "not your plot" in res["reason"]


def test_set_store_price_rejects_negative():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    player, plot = _build_player_store_in_a_town(w)
    res = set_store_price(w, player, plot, MaterialId("grain"), -5)
    assert not res["ok"]


# ───────────────────────── tick_laborer_spending ─────────────────────────


def _force_hungry_housed_laborers(w, n: int = 5) -> list:
    housed = [lab for lab in w.laborers.values() if lab.home_town]
    assert len(housed) >= n
    out = housed[:n]
    for lab in out:
        lab.needs["food"] = 0.30
        lab.needs["fuel"] = 0.40
    return out


def test_laborer_spending_restores_food_need_and_moves_cash():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    targets = _force_hungry_housed_laborers(w, 5)
    pre_cash = {lab.laborer_id: lab.cash_cents for lab in targets}
    pre_total = w.ledger.total_cents()
    # Advance a game-day so the spend tick fires.
    w.tick += TICKS_PER_GAME_DAY
    stats = tick_laborer_spending(w)
    assert stats["purchases"] > 0
    assert stats["laborers_serviced"] >= len(targets)
    for lab in targets:
        assert lab.needs["food"] >= 0.95, (
            f"{lab.laborer_id}: food only restored to {lab.needs['food']:.2f}"
        )
    # Cash moved out of laborer accounts.
    for lab in targets:
        post = w.ledger.balance(laborer_cash_account(lab.laborer_id))
        assert post < pre_cash[lab.laborer_id], (
            f"{lab.laborer_id}: cash did not decrease"
        )
        assert lab.cash_cents == post  # mirror in sync
    # Conservation.
    assert w.ledger.total_cents() == pre_total


def test_store_owner_cash_increases_by_exactly_total_spent():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    _force_hungry_housed_laborers(w, 5)
    # Pick first town's store + its owner.
    town = next(iter(w.towns.values()))
    store_plot = town.store_plots[0]
    owner = w.plots[store_plot].owner
    assert owner is not None
    owner_acct = party_cash_account(owner)
    pre_owner = w.ledger.balance(owner_acct)
    w.tick += TICKS_PER_GAME_DAY
    tick_laborer_spending(w)
    post_owner = w.ledger.balance(owner_acct)
    daily_rev = w.store_revenue_today.get(str(store_plot), 0)
    assert daily_rev > 0
    assert post_owner - pre_owner == daily_rev


def test_empty_store_does_not_serve_laborers():
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    # Drain every NPC store of all grain (food).
    grain = MaterialId("grain")
    coal = MaterialId("coal")
    for inv in w.store_inventories.values():
        inv[str(grain)] = 0
        inv[str(coal)] = 0
    targets = _force_hungry_housed_laborers(w, 3)
    pre = {lab.laborer_id: lab.cash_cents for lab in targets}
    w.tick += TICKS_PER_GAME_DAY
    tick_laborer_spending(w)
    for lab in targets:
        assert lab.cash_cents == pre[lab.laborer_id], "no purchase should occur"
        assert lab.needs["food"] == pytest.approx(0.30), "food need should be unchanged"


def test_laborer_with_no_cash_cannot_buy():
    """Drain the laborer's cash; verify the spend tick does nothing for them."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    targets = _force_hungry_housed_laborers(w, 1)
    lab = targets[0]
    # Sweep all cash back to the system reserve.
    acct = laborer_cash_account(lab.laborer_id)
    bal = w.ledger.balance(acct)
    w.ledger.transfer(
        debit=acct, credit=system_reserve_account(), amount_cents=bal
    )
    lab.cash_cents = 0
    w.tick += TICKS_PER_GAME_DAY
    tick_laborer_spending(w)
    assert lab.needs["food"] == pytest.approx(0.30)


def test_cheapest_store_wins_when_two_stores_present_in_same_town():
    """Plant a competing player store priced 15% below NPC retail."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    town = next(iter(w.towns.values()))
    player, plot = _build_player_store_in_a_town(w, town_id=town.town_id)
    # Confirm registered.
    assert plot in stores_for_town(w, town.town_id)
    # Stock player store with grain at a lower price.
    w.inventory.add(player, MaterialId("grain"), 100)
    stock_store(w, player, plot, MaterialId("grain"), 100)
    npc_price = next(
        store_price_cents(w, sp, MaterialId("grain"))
        for sp in town.store_plots
        if sp != plot
    )
    assert npc_price is not None
    undercut = int(npc_price * 0.85)
    set_store_price(w, player, plot, MaterialId("grain"), undercut)
    # Force a few laborers in this town hungry.
    targets = [
        lab for lab in w.laborers.values() if lab.home_town == town.town_id
    ][:3]
    for lab in targets:
        lab.needs["food"] = 0.30
    pre_player = w.ledger.balance(party_cash_account(player))
    npc_store_plot = next(sp for sp in town.store_plots if sp != plot)
    npc_owner = w.plots[npc_store_plot].owner
    pre_npc = (
        w.ledger.balance(party_cash_account(npc_owner)) if npc_owner else 0
    )
    w.tick += TICKS_PER_GAME_DAY
    tick_laborer_spending(w)
    post_player = w.ledger.balance(party_cash_account(player))
    post_npc = (
        w.ledger.balance(party_cash_account(npc_owner)) if npc_owner else 0
    )
    # Player's store should have captured the bulk of spending.
    player_gain = post_player - pre_player
    npc_gain = post_npc - pre_npc
    assert player_gain > 0
    assert player_gain > npc_gain, (
        f"undercut player should outearn npc for the same hungry laborers: "
        f"player +{player_gain}, npc +{npc_gain}"
    )


def test_no_pop_hub_market_buy_events_during_real_demand_cycle():
    """Phase 7D removed the pop_hub layer entirely — no hub events should fire."""
    w = bootstrap_genesis(seed=42, grid_width=64, grid_height=48, settler_count=4)
    _force_hungry_housed_laborers(w, 5)
    w.tick += TICKS_PER_GAME_DAY
    tick_laborer_spending(w)
    bad = [
        e
        for e in w.event_log
        if "pop_hub" in str(e.get("party", ""))
        or "pop_hub" in str(e.get("buyer", ""))
        or "pop_hub" in str(e.get("seller", ""))
    ]
    assert not bad, f"unexpected pop_hub events: {bad}"


def test_exchange_quoting_tick_is_no_longer_called():
    """Phase 7D removed the managed/unmanaged exchange backstop. Confirm
    the exchange is *not* in tick_genesis_agents anymore."""
    import realm.agents.genesis as ag
    import inspect

    src = inspect.getsource(ag.tick_genesis_agents)
    assert "tick_genesis_exchange_quoting" not in src, (
        "exchange auto-quoting must not run in the per-tick pipeline"
    )
