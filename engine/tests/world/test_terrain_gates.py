"""Sprint 1 / Phase C — terrain gates + per-terrain output bonuses."""

from __future__ import annotations

from realm.actions import claim_plot, start_production_on_plot, survey_plot
from realm.production.buildings import build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.production import effective_outputs_for_completion
from realm.production.recipe_sites import (
    plot_is_coastal,
    recipe_allowed_on_plot,
    recipe_allowed_on_terrain,
    recipe_terrain_bonus_bps,
)
from realm.production.recipes import RECIPES
from realm.world.terrain import Terrain
from realm.world import ActiveProduction, SubsurfaceRoll, bootstrap_frontier


def _seed_party_cash(w, party: PartyId, cents: int) -> None:
    w.ledger.ensure_account(party_cash_account(party))
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=cents,
    )


def _player_owned_plot(seed: int, terrain: Terrain) -> tuple:
    w = bootstrap_frontier(seed=seed, grid_width=4, grid_height=4)
    pid = PlotId("p-0-0")
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    w.plots[pid].terrain = terrain
    # Generic high subsurface so extraction can run.
    w.plots[pid].subsurface = SubsurfaceRoll(
        iron_ore_grade=0.7,
        copper_ore_grade=0.7,
        clay_grade=0.7,
        coal_grade=0.7,
    )
    assert survey_plot(w, player, pid)["ok"] is True
    return w, player, pid


# ─────────────────────────── strict terrain gates ───────────────────────────


def test_grow_grain_blocked_on_tundra() -> None:
    w, player, pid = _player_owned_plot(7, Terrain.TUNDRA)
    assert recipe_allowed_on_terrain(Terrain.TUNDRA, "grow_grain") is False
    ok, reason = recipe_allowed_on_plot(w, w.plots[pid], "grow_grain")
    assert ok is False
    assert reason is not None and "tundra" in reason


def test_grow_grain_allowed_on_plains() -> None:
    assert recipe_allowed_on_terrain(Terrain.PLAINS, "grow_grain") is True


def test_chop_timber_blocked_on_desert() -> None:
    assert recipe_allowed_on_terrain(Terrain.DESERT, "chop_timber") is False


def test_chop_timber_blocked_on_plains() -> None:
    """Sprint 1 tightened forestry to strict forest-only."""
    assert recipe_allowed_on_terrain(Terrain.PLAINS, "chop_timber") is False


def test_chop_timber_allowed_on_forest() -> None:
    assert recipe_allowed_on_terrain(Terrain.FOREST, "chop_timber") is True


def test_mine_coal_allowed_on_mountain() -> None:
    assert recipe_allowed_on_terrain(Terrain.MOUNTAIN, "mine_coal") is True


def test_mine_coal_blocked_on_water() -> None:
    assert recipe_allowed_on_terrain(Terrain.WATER_SHALLOW, "mine_coal") is False
    assert recipe_allowed_on_terrain(Terrain.WATER_DEEP, "mine_coal") is False


def test_start_production_rejects_grain_on_tundra() -> None:
    w, player, pid = _player_owned_plot(7, Terrain.TUNDRA)
    _seed_party_cash(w, player, 1_000_000)
    # The strict gate fires before any building check.
    r = start_production_on_plot(w, player, pid, "grow_grain")
    assert r["ok"] is False
    assert "terrain" in r["reason"] or "tundra" in r["reason"]


# ─────────────────────────── terrain output bonuses ───────────────────────────


def test_mountain_ore_bonus_table() -> None:
    """The terrain-bonus table declares +20% for mine_iron_ore on mountains."""
    assert recipe_terrain_bonus_bps("mine_iron_ore", Terrain.MOUNTAIN) == 12_000
    # Other terrains: no bonus.
    assert recipe_terrain_bonus_bps("mine_iron_ore", Terrain.PLAINS) == 10_000
    # Coal seam thickness bonus on mountains is +10%.
    assert recipe_terrain_bonus_bps("mine_coal", Terrain.MOUNTAIN) == 11_000


def test_mine_iron_ore_output_scales_on_mountain() -> None:
    """Production on mountain terrain yields ~120% of the base iron-ore output.

    Uses a rich subsurface grade (1.0) so the base extraction-scaling lands at a value
    where the +20% bonus is observable in integer output (small int outputs lose
    sub-unit bonuses to truncation, which is fine for gameplay but invisible here).
    """
    w, player, pid = _player_owned_plot(13, Terrain.MOUNTAIN)
    w.plots[pid].subsurface = SubsurfaceRoll(
        iron_ore_grade=1.0,
        copper_ore_grade=0.0,
        clay_grade=0.0,
        coal_grade=0.0,
    )
    recipe = RECIPES["mine_iron_ore"]
    run = ActiveProduction(
        run_id="rtest",
        party=player,
        plot_id=pid,
        recipe_id="mine_iron_ore",
        ticks_remaining=0,
    )
    out_mountain = effective_outputs_for_completion(w, run, recipe)
    # Identical run on a plains plot (mine_iron_ore is mountain-only in production but
    # ``effective_outputs_for_completion`` is gate-free: it scales the abstract output).
    w.plots[pid].terrain = Terrain.PLAINS
    out_plains = effective_outputs_for_completion(w, run, recipe)
    iron = MaterialId("iron_ore")
    assert out_mountain[iron] > out_plains[iron], (
        f"mountain should yield more iron_ore than plains "
        f"({out_mountain[iron]} vs {out_plains[iron]})"
    )


# ─────────────────────────── coastal detection (fishing) ───────────────────────────


def test_plot_is_coastal_when_water_neighbour() -> None:
    w = bootstrap_frontier(seed=1, grid_width=4, grid_height=4)
    # Force p-0-0 to plains and its right neighbour to water_shallow.
    w.plots[PlotId("p-0-0")].terrain = Terrain.PLAINS
    w.plots[PlotId("p-1-0")].terrain = Terrain.WATER_SHALLOW
    assert plot_is_coastal(w, w.plots[PlotId("p-0-0")]) is True


def test_plot_is_coastal_when_non_anchor_cell_touches_water() -> None:
    """Multi-tile deeds: coastal if any world cell borders water, not only (x, y)."""
    w = bootstrap_frontier(seed=1, grid_width=6, grid_height=6, uniform_plots=True)
    anchor = w.plots[PlotId("p-2-2")]
    anchor.terrain = Terrain.PLAINS
    anchor.world_cells = ((2, 2), (3, 2))
    w.plots[PlotId("p-3-2")].terrain = Terrain.WATER_SHALLOW
    for pid in ("p-1-2", "p-2-1", "p-2-3", "p-4-2"):
        w.plots[PlotId(pid)].terrain = Terrain.PLAINS
    from realm.world.plot_parcels import refresh_world_cell_index

    refresh_world_cell_index(w)
    assert plot_is_coastal(w, anchor) is True


def test_fishing_blocked_on_inland_plot() -> None:
    w = bootstrap_frontier(seed=1, grid_width=4, grid_height=4)
    # Fully landlocked: surround p-1-1 with non-water terrain.
    for pid in ("p-0-1", "p-2-1", "p-1-0", "p-1-2"):
        w.plots[PlotId(pid)].terrain = Terrain.PLAINS
    w.plots[PlotId("p-1-1")].terrain = Terrain.PLAINS
    ok, reason = recipe_allowed_on_plot(w, w.plots[PlotId("p-1-1")], "fishing")
    assert ok is False
    assert reason is not None and "coastal" in reason


def test_world_map_dict_includes_is_coastal() -> None:
    from realm.world.plot_parcels import refresh_world_cell_index
    from realm.world.serialization import world_map_dict

    w = bootstrap_frontier(seed=3, grid_width=6, grid_height=6, uniform_plots=True)
    w.plots[PlotId("p-2-2")].terrain = Terrain.PLAINS
    w.plots[PlotId("p-3-2")].terrain = Terrain.WATER_SHALLOW
    for pid in ("p-1-2", "p-2-1", "p-2-3", "p-4-2", "p-3-1", "p-3-3"):
        w.plots[PlotId(pid)].terrain = Terrain.PLAINS
    for pid in ("p-0-1", "p-1-0", "p-2-1", "p-1-2"):
        w.plots[PlotId(pid)].terrain = Terrain.PLAINS
    refresh_world_cell_index(w)
    payload = world_map_dict(w)
    by_id = {str(row["id"]): row for row in payload["plots"]}
    assert by_id["p-2-2"]["is_coastal"] is True
    assert plot_is_coastal(w, w.plots[PlotId("p-1-1")]) is False
    assert by_id["p-1-1"]["is_coastal"] is False


def test_fishing_allowed_on_coastal_plot() -> None:
    w = bootstrap_frontier(seed=1, grid_width=4, grid_height=4)
    w.plots[PlotId("p-0-0")].terrain = Terrain.PLAINS
    w.plots[PlotId("p-1-0")].terrain = Terrain.WATER_SHALLOW
    ok, _ = recipe_allowed_on_plot(w, w.plots[PlotId("p-0-0")], "fishing")
    assert ok is True
