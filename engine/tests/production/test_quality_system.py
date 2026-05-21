"""Commodity quality tiers, input substitution, and industrial cluster bonuses."""

from __future__ import annotations

from dataclasses import replace

from realm.actions import claim_plot, survey_plot
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.economy.markets import place_sell_order
from realm.production.buildings import build_on_plot
from realm.production.production import (
    CLUSTER_EFFICIENCY_BONUS,
    cluster_bonus_for_plot,
    start_production,
)
from realm.production.recipes import RECIPES
from realm.world import SubsurfaceRoll, bootstrap_frontier
from realm.world.placed_buildings import PlacedBuilding, register_placed_building
from realm.world.tick import advance_tick
from realm.world.terrain import Terrain

from plot_helpers import claimable_land_plot_id, first_terrain_plot_id
from turnkey_fixtures import grant_turnkey_self_materials


def _advance_until_building_ready(w, party: PartyId, plot_id: PlotId, building_id: str) -> None:
    while True:
        row = next(
            (
                b
                for b in w.plot_buildings
                if b.get("party") == str(party)
                and b.get("plot_id") == str(plot_id)
                and b.get("building_id") == building_id
            ),
            None,
        )
        assert row is not None
        ct = row.get("completes_at_tick")
        if ct is None or w.tick >= int(ct):
            return
        advance_tick(w)


def _complete_recipe(w, recipe_id: str) -> None:
    for _ in range(RECIPES[recipe_id].duration_ticks):
        advance_tick(w)


def _turnkey(w, party: PartyId, pid: PlotId, building_id: str) -> None:
    grant_turnkey_self_materials(w, party, building_id)
    r = build_on_plot(w, party, pid, building_id, build_mode="self")
    assert r["ok"] is True, r


def test_high_grade_mine_produces_high_quality_ore() -> None:
    w = bootstrap_frontier(seed=9, grid_width=8, grid_height=4)
    player = PartyId("player")
    pid = first_terrain_plot_id(w, Terrain.MOUNTAIN)
    assert claim_plot(w, player, pid)["ok"] is True
    w.plots[pid].subsurface = replace(
        w.plots[pid].subsurface,
        iron_ore_grade=0.75,
    )
    assert survey_plot(w, player, pid)["ok"] is True
    _turnkey(w, player, pid, "strip_mine")
    _advance_until_building_ready(w, player, pid, "strip_mine")
    assert start_production(w, player, pid, "mine_iron_ore")["ok"] is True
    _complete_recipe(w, "mine_iron_ore")
    assert w.inventory.qty(player, MaterialId("iron_ore"), "high") > 0


def test_grade_to_quality_thresholds() -> None:
    from realm.production.quality import (
        QUALITY_HIGH,
        QUALITY_LOW,
        QUALITY_STANDARD,
        grade_to_quality,
    )

    assert grade_to_quality(0.25) == QUALITY_LOW
    assert grade_to_quality(0.45) == QUALITY_STANDARD
    assert grade_to_quality(0.75) == QUALITY_HIGH


def test_subsurface_below_gate_still_maps_low_when_forced() -> None:
    """Recipes gate at 0.30; verify low-tier mapping on direct extraction helper."""
    from realm.production.production import _output_quality_for_plot

    w = bootstrap_frontier(seed=9, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = first_terrain_plot_id(w, Terrain.MOUNTAIN)
    w.plots[pid].subsurface = replace(w.plots[pid].subsurface, iron_ore_grade=0.22)
    assert _output_quality_for_plot(w, pid, MaterialId("iron_ore")) == "low"


def test_quality_price_premium_in_order_book() -> None:
    w = bootstrap_frontier(seed=3, grid_width=3, grid_height=2)
    player = PartyId("player")
    w.inventory.add(player, MaterialId("coal"), 10, quality="high")
    w.inventory.add(player, MaterialId("coal"), 10, quality="standard")
    assert place_sell_order(w, player, MaterialId("coal"), 5, 100, quality="high")["ok"]
    assert place_sell_order(w, player, MaterialId("coal"), 5, 80, quality="standard")["ok"]
    asks = w.market_asks_by_material.get(str(MaterialId("coal")), [])
    high_ask = next((a for a in asks if getattr(a, "quality", "standard") == "high"), None)
    std_ask = next((a for a in asks if getattr(a, "quality", "standard") == "standard"), None)
    assert high_ask is not None and std_ask is not None
    assert high_ask.price_per_unit_cents > std_ask.price_per_unit_cents


def test_substitution_used_when_primary_unavailable() -> None:
    w = bootstrap_frontier(seed=301, grid_width=4, grid_height=3)
    player = PartyId("player")
    pid = claimable_land_plot_id(w, player)
    plot = w.plots[pid]
    plot.terrain = Terrain.MOUNTAIN
    plot.subsurface = SubsurfaceRoll(
        iron_ore_grade=0.8,
        copper_ore_grade=0.6,
        clay_grade=0.5,
        coal_grade=0.7,
    )
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    grant_turnkey_self_materials(w, player, "foundry")
    br = build_on_plot(w, player, pid, "foundry", build_mode="turnkey")
    assert br["ok"] is True
    inst = br["instance_id"]
    for b in w.plot_buildings:
        if b.get("instance_id") == inst:
            b["completes_at_tick"] = -1
    while w.inventory.qty(player, MaterialId("coal"), "any") > 0:
        w.inventory.remove(
            player,
            MaterialId("coal"),
            w.inventory.qty(player, MaterialId("coal"), "any"),
            quality="any",
        )
    w.inventory.add(player, MaterialId("iron_ore"), 2)
    w.inventory.add(player, MaterialId("charcoal"), 4)
    w.inventory.add(player, MaterialId("electricity"), 4)
    charcoal_before = w.inventory.qty(player, MaterialId("charcoal"), "any")
    r = start_production(w, player, pid, "smelt_iron", run_count=1)
    assert r["ok"] is True, r
    assert w.inventory.qty(player, MaterialId("coal"), "any") == 0
    assert w.inventory.qty(player, MaterialId("charcoal"), "any") < charcoal_before


def test_cluster_bonus_requires_4_buildings() -> None:
    w = bootstrap_frontier(seed=5, grid_width=6, grid_height=6)
    player = PartyId("player")
    pid = claimable_land_plot_id(w, player)
    assert claim_plot(w, player, pid)["ok"] is True
    plot = w.plots[pid]
    px, py = int(plot.x), int(plot.y)
    for i in range(3):
        register_placed_building(
            w,
            PlacedBuilding(
                instance_id=f"pb-{i}",
                blueprint_id="strip_mine",
                plot_id=str(pid),
                grid_x=i,
                grid_y=0,
                built_at_tick=0,
                built_by=str(player),
                status="active",
                efficiency_pct=100,
                missed_maintenance_cycles=0,
                due_at_tick=0,
            ),
        )
    assert cluster_bonus_for_plot(w, player, pid) == 0.0
    register_placed_building(
        w,
        PlacedBuilding(
            instance_id="pb-4",
            blueprint_id="strip_mine",
            plot_id=str(pid),
            grid_x=3,
            grid_y=0,
            built_at_tick=0,
            built_by=str(player),
            status="active",
            efficiency_pct=100,
            missed_maintenance_cycles=0,
            due_at_tick=0,
        ),
    )
    assert cluster_bonus_for_plot(w, player, pid) == CLUSTER_EFFICIENCY_BONUS


def test_quality_conservation_money() -> None:
    w = bootstrap_frontier(seed=9, grid_width=8, grid_height=4)
    player = PartyId("player")
    pid = first_terrain_plot_id(w, Terrain.MOUNTAIN)
    assert claim_plot(w, player, pid)["ok"] is True
    w.plots[pid].subsurface = replace(w.plots[pid].subsurface, iron_ore_grade=0.75)
    assert survey_plot(w, player, pid)["ok"] is True
    _turnkey(w, player, pid, "strip_mine")
    _advance_until_building_ready(w, player, pid, "strip_mine")
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    assert start_production(w, player, pid, "mine_iron_ore")["ok"] is True
    _complete_recipe(w, "mine_iron_ore")
    assert_money_conserved(w.ledger, snap.ledger_total_cents)
