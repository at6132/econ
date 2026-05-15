"""Landmass-density bootstrap targets for Genesis."""

from __future__ import annotations

from realm.population.landmass_density import (
    genesis_settler_count_for_world,
    laborer_target_count_for_landmass,
    total_laborer_target_for_world,
)
from realm.world.biome_noise import continental_layout_supported
from realm.world import bootstrap_genesis
from realm.world.landmasses import list_continents


def test_default_genesis_uses_continental_layout_and_large_grid() -> None:
    w = bootstrap_genesis(seed=7, settler_count=0)
    assert continental_layout_supported(128, 96)
    assert len(w.plots) == 128 * 96
    assert list_continents(w), "expected at least one continent on default map"


def test_labor_and_settler_counts_scale_with_landmass_size() -> None:
    w = bootstrap_genesis(seed=42, settler_count=0)
    target = total_laborer_target_for_world(w)
    assert len(w.laborers) == target
    assert target >= 500
    boot = genesis_settler_count_for_world(w)
    assert boot >= 250


def test_four_island_layout_density_matches_seeded_labor() -> None:
    w = bootstrap_genesis(
        seed=42,
        grid_width=64,
        grid_height=48,
        settler_count=0,
        map_layout="islands",
    )
    for lid in sorted((w.landmass_plot_count or {}).keys()):
        assert laborer_target_count_for_landmass(w, lid) >= 40
