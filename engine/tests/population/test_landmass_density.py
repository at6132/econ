"""Landmass-density bootstrap targets for Genesis."""

from __future__ import annotations

import inspect

from realm.population.landmass_density import (
    genesis_settler_count_for_world,
    laborer_target_count_for_landmass,
    total_laborer_target_for_world,
)
from realm.world.biome_noise import continental_layout_supported
from realm.world import bootstrap_genesis


_DEFAULT_GW, _DEFAULT_GH = 192, 144


def test_genesis_defaults_use_continental_grid_size() -> None:
    sig = inspect.signature(bootstrap_genesis)
    assert int(sig.parameters["grid_width"].default) == _DEFAULT_GW
    assert int(sig.parameters["grid_height"].default) == _DEFAULT_GH
    assert continental_layout_supported(_DEFAULT_GW, _DEFAULT_GH)


def test_labor_and_settler_counts_scale_with_landmass_size() -> None:
    w = bootstrap_genesis(seed=42, grid_width=100, grid_height=100, settler_count=0)
    target = total_laborer_target_for_world(w)
    assert len(w.laborers) == target
    assert target >= 500
    boot = genesis_settler_count_for_world(w)
    assert boot >= 250


def test_continental_layout_density_matches_seeded_labor() -> None:
    w = bootstrap_genesis(
        seed=42,
        grid_width=64,
        grid_height=48,
        settler_count=0,
        map_layout="continental",
    )
    for lid in sorted((w.landmass_plot_count or {}).keys()):
        assert laborer_target_count_for_landmass(w, lid) >= 40
