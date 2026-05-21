"""Realism pass 4 — storage demurrage, trade balance, book value, demolish."""

from __future__ import annotations

from realm.actions.blueprint_actions import demolish_building
from realm.core.conservation import (
    ConservationSnapshot,
    assert_money_conserved,
)
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.core.player_economy import FREE_STORAGE_UNITS_PER_PARTY
from realm.economy.asset_depreciation import tick_asset_depreciation
from realm.economy.holding_costs import tick_holding_costs
from realm.economy.trade_balance import record_shipment_flow
from realm.production.buildings import build_on_plot
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick
from tests.turnkey_fixtures import grant_turnkey_self_materials


def _first_land_plot(world, party: PartyId) -> PlotId:
    for p in world.plots.values():
        if p.owner == party and p.terrain.value in ("plains", "forest", "hills"):
            return p.plot_id
    for p in world.plots.values():
        if p.owner is None:
            p.owner = party
            return p.plot_id
    raise AssertionError("no claimable plot")


def test_holding_cost_charged_for_excess_inventory() -> None:
    w = bootstrap_genesis(seed=1, settler_count=3)
    player = PartyId("player")
    w.inventory.add(player, MaterialId("coal"), 200)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    w.tick = 1440
    start_cash = w.ledger.balance(party_cash_account(player))
    tick_holding_costs(w)
    end_cash = w.ledger.balance(party_cash_account(player))
    excess = 200 - FREE_STORAGE_UNITS_PER_PARTY
    assert end_cash == start_cash - excess
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_warehouse_exempts_from_holding_costs() -> None:
    w = bootstrap_genesis(seed=2, settler_count=3)
    player = PartyId("player")
    pid = _first_land_plot(w, player)
    grant_turnkey_self_materials(w, player, "warehouse")
    build_on_plot(w, player, pid, "warehouse", build_mode="turnkey")
    for _ in range(3000):
        advance_tick(w)
    w.inventory.add(player, MaterialId("coal"), 500)
    w.tick = 1440
    start_cash = w.ledger.balance(party_cash_account(player))
    tick_holding_costs(w)
    end_cash = w.ledger.balance(party_cash_account(player))
    assert end_cash == start_cash


def test_trade_balance_recorded_on_shipment() -> None:
    w = bootstrap_genesis(seed=3, settler_count=5)
    plots = list(w.plots.values())
    from_pid = plots[0].plot_id
    to_pid = plots[-1].plot_id
    record_shipment_flow(w, from_pid, to_pid, MaterialId("coal"), 10, 830)
    flows = w.scenario_state.get("trade_flows_today", {})
    assert len(flows) > 0


def test_demolish_returns_half_book_value() -> None:
    w = bootstrap_genesis(seed=4, settler_count=3)
    player = PartyId("player")
    pid = _first_land_plot(w, player)
    grant_turnkey_self_materials(w, player, "power_shed")
    r = build_on_plot(w, player, pid, "power_shed", build_mode="turnkey")
    assert r["ok"]
    iid = str(r["instance_id"])
    for _ in range(200):
        advance_tick(w)
    pb = w.placed_buildings[iid]
    book_val = int(pb.book_value_cents)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    start_cash = w.ledger.balance(party_cash_account(player))
    r2 = demolish_building(w, player, iid)
    assert r2.get("ok")
    end_cash = w.ledger.balance(party_cash_account(player))
    assert end_cash == start_cash + book_val // 2
    assert_money_conserved(w.ledger, snap.ledger_total_cents)
    assert iid not in w.placed_buildings


def test_book_value_depreciates_yearly() -> None:
    w = bootstrap_genesis(seed=5, settler_count=3)
    player = PartyId("player")
    pid = _first_land_plot(w, player)
    grant_turnkey_self_materials(w, player, "foundry")
    build_on_plot(w, player, pid, "foundry", build_mode="turnkey")
    for _ in range(300):
        advance_tick(w)
    iid = next(
        pb.instance_id
        for pb in w.placed_buildings.values()
        if pb.blueprint_id == "foundry"
    )
    pb = w.placed_buildings[iid]
    orig_cost = int(pb.original_cost_cents)
    assert orig_cost > 0
    book_before = int(pb.book_value_cents)
    w.tick = 525_600
    tick_asset_depreciation(w)
    annual_dep = int(orig_cost * pb.depreciation_rate_per_year)
    assert int(pb.book_value_cents) == max(0, book_before - annual_dep)


def test_storage_service_requires_warehouse() -> None:
    from realm.contracts.stubs import propose_service_sub

    w = bootstrap_genesis(seed=6, settler_count=3)
    provider = PartyId("player")
    subscriber = PartyId("genesis_settlement")
    r = propose_service_sub(
        w,
        provider,
        subscriber,
        fee_cents=1000,
        duration_ticks=1440,
        service_id="storage",
        service_params={"max_units": 500, "materials": ["coal"]},
    )
    assert not r.get("ok")
