"""Polyomino parcel footprints — variety + area truth."""

from __future__ import annotations

from collections import Counter

from realm.world import generate_plots
from realm.world.parcel_footprints import classify_parcel_shape
from realm.world.plot_scale import plot_area_sq_metres, plot_world_tile_count
from realm.world.plot_parcels import build_world_cell_index


def test_generate_includes_multiple_shape_kinds() -> None:
    plots = generate_plots(seed=4242, width=24, height=18)
    shapes = Counter(p.parcel_shape for p in plots.values())
    # Must see more than mono + rect on a decent grid.
    assert shapes["rect"] > 0 or shapes["line"] > 0
    multi_kinds = sum(1 for k in ("l", "zigzag", "t", "plus", "poly", "line") if shapes.get(k, 0) > 0)
    assert multi_kinds >= 2, f"expected shape variety, got {dict(shapes)}"


def test_area_truth_matches_tile_count() -> None:
    plots = generate_plots(seed=99, width=16, height=12)
    for p in plots.values():
        n = plot_world_tile_count(p)
        assert plot_area_sq_metres(p) == n * 10_000
        assert n == len(p.world_cells)


def test_classify_l_shape() -> None:
    cells = ((0, 0), (0, 1), (1, 0))
    assert classify_parcel_shape(cells) == "l"


def test_classify_zigzag() -> None:
    cells = ((0, 0), (1, 0), (1, 1), (2, 1))
    assert classify_parcel_shape(cells) == "zigzag"


def test_index_covers_all_cells() -> None:
    w, h = 14, 10
    plots = generate_plots(seed=7, width=w, height=h)
    assert len(build_world_cell_index(plots)) == w * h
    assert len(plots) < w * h
