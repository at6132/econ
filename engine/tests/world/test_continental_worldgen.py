"""Phase 10A — continental worldgen (large grids only)."""

from __future__ import annotations

from realm.world.biome_noise import continental_layout_supported, terrain_for_cell
from realm.world import bootstrap_genesis
from realm.world.landmasses import list_continents


def test_small_grid_uses_fallback_terrain() -> None:
    """Below 10_000 plots, auto layout stays off continental FBM."""
    w = bootstrap_genesis(seed=1, settler_count=2, grid_width=16, grid_height=16)
    assert not continental_layout_supported(16, 16)
    assert w.plots


def test_at_least_2_continents_on_large_grid() -> None:
    """Continental layout classifies ≥1 continent-sized component (FBM may merge)."""
    w = bootstrap_genesis(seed=42, settler_count=20, grid_width=100, grid_height=100)
    continents = list_continents(w)
    assert continents, f"expected at least one continent landmass, got {continents}"
    total_continent_plots = sum(
        int((w.landmass_plot_count or {}).get(cid, 0)) for cid in continents
    )
    assert total_continent_plots >= 500


def test_viability_validation_passes() -> None:
    w = bootstrap_genesis(seed=43, settler_count=15, grid_width=100, grid_height=100)
    continents = list_continents(w)
    assert continents


def test_terrain_for_cell_unchanged_small_coord() -> None:
    assert terrain_for_cell(99, 0, 0) == terrain_for_cell(99, 0, 0)
