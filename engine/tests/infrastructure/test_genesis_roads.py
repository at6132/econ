"""Genesis starter roads and settler road-building."""

from __future__ import annotations

from realm.actions.plot_actions import claim_plot
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.genesis.settler_upgrades import _maybe_build_settler_road
from realm.infrastructure.power_grid import compute_grid_regions
from realm.infrastructure.road_connectivity import is_road_accessible
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick


def test_genesis_world_has_starter_roads() -> None:
    w = bootstrap_genesis(seed=42, settler_count=5)
    assert len(w.road_segments) > 0, "Genesis world should have starter roads"
    town_centers = [
        is_road_accessible(w, t.center_plot) for t in w.towns.values()
    ]
    assert any(town_centers), "At least one town center should be road-accessible"
    store_access = [
        is_road_accessible(w, sp)
        for t in w.towns.values()
        for sp in t.store_plots
    ]
    assert any(store_access), "At least one genesis store should be road-accessible"


def test_power_grid_forms_after_genesis_roads() -> None:
    w = bootstrap_genesis(seed=1, settler_count=5)
    for _ in range(1440):
        advance_tick(w)
    regions = compute_grid_regions(w)
    road_connected = [r for r in regions.values() if len(r.plot_ids) > 1]
    assert len(road_connected) > 0, (
        "Genesis roads should create multi-plot grid regions"
    )


def test_settler_builds_road_when_rich_conserves_money() -> None:
    w = bootstrap_genesis(seed=2, settler_count=5)
    settlers = sorted(p for p in w.parties if str(p).startswith("settler_"))
    assert settlers
    player = settlers[0]
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(player),
        amount_cents=5_000_000,
    )
    isolated = next(
        pid
        for pid, plot in w.plots.items()
        if plot.owner is None and not str(plot.terrain).lower().startswith("water")
    )
    assert claim_plot(w, player, PlotId(isolated))["ok"]
    for mat, qty in (("lumber", 20), ("stone", 20)):
        ad = w.inventory.add(player, MaterialId(mat), qty)
        assert not isinstance(ad, MatterErr)
    _maybe_build_settler_road(w, player)
    assert_money_conserved(w.ledger, snap.ledger_total_cents)
