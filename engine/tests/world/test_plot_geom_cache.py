"""Plot geometry / valuation caches invalidate on claim."""

from __future__ import annotations

from realm.actions.plot_actions import claim_plot
from realm.core.ids import PlotId
from realm.production.recipe_sites import plot_is_coastal, waterfront_build_cells
from realm.world import bootstrap_genesis
from realm.world.plot_geom_cache import (
    _gen,
    _waterfront,
    cached_compute_plot_value,
    invalidate_plot_geom_caches,
)
from realm.world.real_estate import compute_plot_value


def test_waterfront_cache_reuses_within_generation() -> None:
    world = bootstrap_genesis(seed=42)
    pid = next(iter(world.plots))
    plot = world.plots[pid]
    invalidate_plot_geom_caches()
    _waterfront.clear()
    a = waterfront_build_cells(world, plot)
    b = waterfront_build_cells(world, plot)
    assert a is b
    assert len(_waterfront) == 1


def test_plot_geom_cache_invalidates_on_claim() -> None:
    from tests.plot_helpers import ensure_party_can_claim, first_land_plot_id

    world = bootstrap_genesis(seed=7)
    pid = first_land_plot_id(world)
    plots_id = id(world.plots)
    gen_before = int(_gen.get(plots_id, 0))
    v_before = cached_compute_plot_value(world, pid)
    assert v_before == compute_plot_value(world, pid)

    party = next(p for p in world.parties if str(p).startswith("settler_"))
    ensure_party_can_claim(world, party, pid)
    r = claim_plot(world, party, pid)
    assert r["ok"], r
    gen_after = int(_gen.get(plots_id, 0))
    assert gen_after == gen_before + 1


def test_coastal_matches_uncached_after_invalidate() -> None:
    world = bootstrap_genesis(seed=99)
    coastal = [
        pid
        for pid, p in world.plots.items()
        if plot_is_coastal(world, p) and p.owner is None
    ]
    if not coastal:
        return
    pid = coastal[0]
    plot = world.plots[pid]
    invalidate_plot_geom_caches()
    assert bool(waterfront_build_cells(world, plot)) == plot_is_coastal(world, plot)


def test_compute_plot_value_stable_across_calls() -> None:
    world = bootstrap_genesis(seed=11)
    pid = PlotId(next(iter(world.plots)))
    assert compute_plot_value(world, pid) == compute_plot_value(world, pid)
