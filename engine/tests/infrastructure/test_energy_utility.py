"""Grid energy service — Wh draws, no commodity electricity on market."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from plot_helpers import claimable_land_plot_id
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.economy.markets import place_sell_order
from realm.infrastructure.energy_service import (
    LEGACY_ELECTRICITY_MATERIAL,
    recipe_energy_wh,
)
from realm.infrastructure.plot_logistics import try_add_plot_output
from realm.production.recipes import RECIPES
from realm.world import bootstrap_frontier


def test_electricity_not_carried_material() -> None:
    from realm.production.storage_caps import is_carried_material

    assert not is_carried_material(LEGACY_ELECTRICITY_MATERIAL)


def test_recipe_energy_wh_from_legacy_input() -> None:
    r = RECIPES["sawmill"]
    assert recipe_energy_wh(r) == 1000


def test_cannot_list_electricity_on_market() -> None:
    w = bootstrap_frontier(seed=7, grid_width=12, grid_height=10)
    player = PartyId("player")
    pid = claimable_land_plot_id(w, player)
    assert claim_plot(w, player, pid)["ok"]
    try_add_plot_output(w, pid, player, MaterialId("coal"), 5)
    r = place_sell_order(
        w,
        player,
        LEGACY_ELECTRICITY_MATERIAL,
        1,
        100,
        from_plot_id=pid,
    )
    assert not r.get("ok")


def test_production_draws_grid_not_inventory() -> None:
    w = bootstrap_frontier(seed=8, grid_width=6, grid_height=4)
    player = PartyId("player")
    pid = claimable_land_plot_id(w, player)
    assert claim_plot(w, player, pid)["ok"]
    assert w.inventory.qty(player, LEGACY_ELECTRICITY_MATERIAL) == 0
