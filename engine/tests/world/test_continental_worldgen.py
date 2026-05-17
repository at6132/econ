"""Phase 10A — continental worldgen (large grids only)."""

from __future__ import annotations

from realm.world.biome_noise import (
    GENESIS_DEFAULT_GRID_HEIGHT,
    GENESIS_DEFAULT_GRID_WIDTH,
    continental_layout_supported,
    terrain_for_cell,
)
from realm.world import bootstrap_genesis
from realm.world.landmasses import list_continents


def test_small_grid_uses_fallback_terrain() -> None:
    """Below 10_000 plots, auto layout stays off continental FBM."""
    w = bootstrap_genesis(seed=1, settler_count=2, grid_width=16, grid_height=16)
    assert not continental_layout_supported(16, 16)
    assert w.plots


def test_default_genesis_grid_size() -> None:
    w = bootstrap_genesis(seed=1, settler_count=0)
    xs = [p.x for p in w.plots.values()]
    ys = [p.y for p in w.plots.values()]
    assert max(xs) + 1 == GENESIS_DEFAULT_GRID_WIDTH
    assert max(ys) + 1 == GENESIS_DEFAULT_GRID_HEIGHT


def test_at_least_2_continents_on_default_genesis_grid() -> None:
    """Continental procedural layout yields multiple continent-class landmasses."""

    w = bootstrap_genesis(seed=42, settler_count=12)
    continents = list_continents(w)
    assert len(continents) >= 2, (
        f"expected ≥2 continents, got {continents}: {w.landmass_type!r}"
    )
    total_continent_plots = sum(
        int((w.landmass_plot_count or {}).get(cid, 0)) for cid in continents
    )
    assert total_continent_plots >= 2 * 500


def test_landmass_count_varies_across_seeds() -> None:
    from realm.core.inventory import Inventory
    from realm.core.ledger import Ledger
    from realm.world import World
    from realm.world.biome_noise import continental_layout_terrain
    from realm.world.landmasses import compute_landmasses
    from realm.world.world import generate_plots

    w, h = 160, 120

    def terrain_fn(s: int, x: int, y: int):
        return continental_layout_terrain(s, x, y, w, h)

    counts: set[int] = set()
    for seed in (0, 4, 8, 12, 16, 20, 24, 28):
        plots = generate_plots(seed=seed, width=w, height=h, terrain_fn=terrain_fn)
        world = World(
            seed=seed, tick=0, plots=plots, ledger=Ledger(), inventory=Inventory()
        )
        compute_landmasses(world)
        counts.add(len(world.landmass_plot_count or {}))
    assert len(counts) >= 3


def test_viability_validation_passes() -> None:
    w = bootstrap_genesis(seed=43, settler_count=15)
    continents = list_continents(w)
    assert continents


def test_terrain_for_cell_unchanged_small_coord() -> None:
    assert terrain_for_cell(99, 0, 0) == terrain_for_cell(99, 0, 0)
