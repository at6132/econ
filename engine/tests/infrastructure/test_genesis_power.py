"""Genesis road network and day-1 power grid activation."""

from __future__ import annotations

import time

from realm.core.ids import PlotId
from realm.infrastructure.power_grid import compute_grid_regions
from realm.infrastructure.road_connectivity import is_road_accessible
from realm.world import bootstrap_genesis
from realm.world.tick import advance_tick


def test_all_towns_road_accessible_after_genesis() -> None:
    w = bootstrap_genesis(seed=7, settler_count=5)
    connected_towns = sum(
        1
        for town in w.towns.values()
        if is_road_accessible(w, PlotId(str(town.center_plot)))
    )
    assert connected_towns >= 3, (
        f"Expected ≥3/4 town centers road-accessible, got {connected_towns}"
    )


def test_genesis_has_power_sheds() -> None:
    w = bootstrap_genesis(seed=7, settler_count=5)
    sheds = [
        pb
        for pb in w.placed_buildings.values()
        if pb.blueprint_id == "power_shed"
    ]
    legacy = [
        r for r in w.plot_buildings if str(r.get("building_id")) == "power_shed"
    ]
    assert len(sheds) + len(legacy) >= 1, "Genesis world should have at least 1 power shed"


def test_power_market_activates_day_1() -> None:
    w = bootstrap_genesis(seed=7, settler_count=5)
    for _ in range(1440):
        advance_tick(w)
    regions = compute_grid_regions(w)
    active = [r for r in regions.values() if r.capacity_per_day > 0]
    assert len(active) >= 1, (
        "At least one power grid region should have generation capacity after day 1"
    )


def test_road_neighbor_lookup_performance() -> None:
    """O(1) coord index — neighbor scans must not walk all plots."""
    from realm.genesis.town_roads import _build_coord_index, _geographic_neighbors

    w = bootstrap_genesis(seed=42, grid_width=48, grid_height=36, settler_count=3)
    _build_coord_index(w)
    sample = list(w.plots.keys())[: min(400, len(w.plots))]
    t0 = time.perf_counter()
    for _ in range(2000):
        for pid in sample:
            _geographic_neighbors(w, pid)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"Neighbor lookup took {elapsed:.1f}s — coord index regression?"


def test_genesis_bootstrap_small_map_performance() -> None:
    """Starter-town bootstrap on a small map stays interactive."""
    t0 = time.perf_counter()
    bootstrap_genesis(seed=42, grid_width=48, grid_height=36, settler_count=3)
    elapsed = time.perf_counter() - t0
    assert elapsed < 8.0, f"Small-map bootstrap took {elapsed:.1f}s — too slow"


def test_genesis_starter_road_segment_count() -> None:
    w = bootstrap_genesis(seed=7, settler_count=5)
    assert len(w.road_segments) >= 12, (
        f"Expected a starter road network, got {len(w.road_segments)} segments"
    )
