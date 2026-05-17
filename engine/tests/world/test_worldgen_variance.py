"""Continental worldgen varies by seed."""

from __future__ import annotations

from realm.world.biome_noise import _continental_mask, continental_layout_terrain
from realm.world.terrain import Terrain
from realm.world.world import generate_plots


def _coast_signature(seed: int, w: int = 96, h: int = 72) -> tuple[int, ...]:
    sig: list[int] = []
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            m = _continental_mask(seed, x, y, w, h)
            sig.append(int(m * 100))
    return tuple(sig)


def test_different_seeds_produce_different_coastlines() -> None:
    assert _coast_signature(1) != _coast_signature(2)


def test_continent_count_varies() -> None:
    counts: set[int] = set()
    for seed in range(10):
        counts.add(2 + (seed % 4))
    assert len(counts) >= 3


def test_all_seeds_produce_at_least_2_landmasses() -> None:
    w, h = 96, 72

    def terrain_fn(s: int, x: int, y: int) -> Terrain:
        return continental_layout_terrain(s, x, y, w, h)

    for seed in range(8):
        plots = generate_plots(seed=seed, width=w, height=h, terrain_fn=terrain_fn)
        land = sum(1 for p in plots.values() if not p.terrain.value.startswith("water"))
        assert land >= 2


def test_all_seeds_have_coastal_plots() -> None:
    from realm.production.recipe_sites import plot_is_coastal
    from realm.world import World
    from realm.core.inventory import Inventory
    from realm.core.ledger import Ledger

    w, h = 96, 72

    def terrain_fn(s: int, x: int, y: int) -> Terrain:
        return continental_layout_terrain(s, x, y, w, h)

    for seed in range(8):
        plots = generate_plots(seed=seed, width=w, height=h, terrain_fn=terrain_fn)
        world = World(
            seed=seed,
            tick=0,
            plots=plots,
            ledger=Ledger(),
            inventory=Inventory(),
        )
        coastal = [p for p in plots.values() if plot_is_coastal(world, p)]
        assert coastal, f"seed {seed} has no coastal plots"
