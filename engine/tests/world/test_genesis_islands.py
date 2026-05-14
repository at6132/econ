"""Genesis four-islands map layout — geographic isolation and economic plumbing.

The four-island layout (added 2026-05) replaces Genesis's single-continent map
with four ellipse-shaped landmasses in the four quadrants separated by a
cross-shaped ocean. These tests assert the structural invariants of that
layout (Pillar 3 — Geography matters; Law 3 — Distance has cost) and that the
existing engine subsystems (settlers, shippers, money conservation) still hold.
"""

from __future__ import annotations

from collections import deque

from realm.world.biome_noise import (
    GENESIS_ISLAND_MIN_HEIGHT,
    GENESIS_ISLAND_MIN_WIDTH,
    genesis_island_centers,
    genesis_island_layout_supported,
    terrain_for_genesis_island_cell,
)
from realm.core.ids import PartyId, PlotId
from realm.world.terrain import Terrain
from realm.world.tick import advance_tick
from realm.world import bootstrap_genesis


def _land_mask(world) -> dict[tuple[int, int], bool]:
    return {
        (p.x, p.y): p.terrain not in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP)
        for p in world.plots.values()
    }


def _flood_fill_land_components(world) -> list[set[tuple[int, int]]]:
    """4-connected land components ≥ 6 tiles (filters specks)."""
    mask = _land_mask(world)
    seen: set[tuple[int, int]] = set()
    out: list[set[tuple[int, int]]] = []
    for (x, y), is_land in mask.items():
        if not is_land or (x, y) in seen:
            continue
        comp: set[tuple[int, int]] = set()
        q: deque[tuple[int, int]] = deque([(x, y)])
        while q:
            cx, cy = q.popleft()
            if (cx, cy) in comp:
                continue
            if not mask.get((cx, cy), False):
                continue
            comp.add((cx, cy))
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if (nx, ny) not in comp and mask.get((nx, ny), False):
                    q.append((nx, ny))
        seen |= comp
        if len(comp) >= 6:
            out.append(comp)
    out.sort(key=len, reverse=True)
    return out


def test_genesis_islands_layout_supported_threshold() -> None:
    assert genesis_island_layout_supported(96, 72) is True
    assert genesis_island_layout_supported(GENESIS_ISLAND_MIN_WIDTH, GENESIS_ISLAND_MIN_HEIGHT) is True
    assert genesis_island_layout_supported(GENESIS_ISLAND_MIN_WIDTH - 1, GENESIS_ISLAND_MIN_HEIGHT) is False
    assert genesis_island_layout_supported(GENESIS_ISLAND_MIN_WIDTH, GENESIS_ISLAND_MIN_HEIGHT - 1) is False


def test_genesis_islands_terrain_centre_is_land_corners_are_ocean() -> None:
    w, h = 96, 72
    seed = 13
    for cx, cy in genesis_island_centers(w, h):
        t = terrain_for_genesis_island_cell(seed, cx, cy, w, h)
        assert t not in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP), (
            f"island centre ({cx},{cy}) must be land, got {t}"
        )
    # The geometric centre of the map sits in the cross-shaped ocean.
    mid = terrain_for_genesis_island_cell(seed, w // 2, h // 2, w, h)
    assert mid in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP)


def test_genesis_islands_default_bootstrap_produces_four_landmasses() -> None:
    """Default Genesis bootstrap (96 × 72) yields at least four distinct land components."""
    world = bootstrap_genesis(seed=42, settler_count=0)
    comps = _flood_fill_land_components(world)
    assert len(comps) >= 4, (
        f"expected ≥4 land components on Genesis default map, got {len(comps)}"
    )
    # Each of the four largest landmasses must contain a meaningful slice of plots.
    big = comps[:4]
    for comp in big:
        assert len(comp) >= 80, f"landmass too small to host a regional economy: {len(comp)}"
    # The four island centres should each fall inside one of the largest four components.
    centers = genesis_island_centers(96, 72)
    big_sets = [set(c) for c in big]
    for cx, cy in centers:
        assert any((cx, cy) in s for s in big_sets), f"centre ({cx},{cy}) not inside a major landmass"


def test_genesis_islands_have_real_ocean_between_them() -> None:
    """The cross-shaped band between quadrants is dominated by water."""
    world = bootstrap_genesis(seed=42, settler_count=0)
    # Sample the vertical and horizontal ocean strips at the map midline.
    mid_x, mid_y = 96 // 2, 72 // 2
    h_strip = [
        world.plots[PlotId(f"p-{x}-{mid_y}")].terrain
        for x in range(96)
        if PlotId(f"p-{x}-{mid_y}") in world.plots
    ]
    v_strip = [
        world.plots[PlotId(f"p-{mid_x}-{y}")].terrain
        for y in range(72)
        if PlotId(f"p-{mid_x}-{y}") in world.plots
    ]
    h_water = sum(1 for t in h_strip if t in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP))
    v_water = sum(1 for t in v_strip if t in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP))
    # The midline crosses ocean between every pair of opposite islands, so
    # roughly half each strip should be water. Be conservative: ≥ 35 %.
    assert h_water / max(1, len(h_strip)) >= 0.35
    assert v_water / max(1, len(v_strip)) >= 0.35


def test_genesis_islands_centers_are_each_on_distinct_landmass() -> None:
    """Phase 7A: each of the four island centres sits on land, in its own component.

    Pre-Phase 7 this was tested via ``pop_hub_w / pop_hub_e`` coords. With
    hubs removed the same structural invariant is asserted directly against
    ``genesis_island_centers``: four centres → four distinct landmasses.
    """
    world = bootstrap_genesis(seed=42, settler_count=0)
    centers = genesis_island_centers(96, 72)
    comps = _flood_fill_land_components(world)
    seen_components: set[int] = set()
    for cx, cy in centers:
        p = world.plots[PlotId(f"p-{cx}-{cy}")]
        assert p.terrain not in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP), (
            f"island centre ({cx},{cy}) must be land"
        )
        idx = next((i for i, comp in enumerate(comps) if (cx, cy) in comp), -1)
        assert idx >= 0, f"island centre ({cx},{cy}) is not inside any land component"
        seen_components.add(idx)
    assert len(seen_components) == 4, (
        f"expected the four centres to belong to four distinct landmasses, "
        f"got {len(seen_components)} distinct components"
    )


def test_genesis_islands_force_continent_layout_when_requested() -> None:
    """Caller can opt out of islands with map_layout='continent' even on a large grid.

    Phase 7A: the continent layout has no ``plot_islands`` cache (it's a single
    landmass), so we just assert the bootstrap succeeds and produces plots.
    """
    world = bootstrap_genesis(seed=42, settler_count=0, map_layout="continent")
    assert len(world.plots) == 96 * 72
    assert world.scenario_state.get("plot_islands") == {}


def test_genesis_islands_small_grid_auto_falls_back_to_continent() -> None:
    """Tiny grids skip the island mask so legacy tiny-grid tests keep their shape."""
    world = bootstrap_genesis(seed=42, grid_width=12, grid_height=10, settler_count=0)
    # No island layout on tiny grids → no plot_islands cache.
    assert world.scenario_state.get("plot_islands") == {}


def test_genesis_islands_ledger_conserved_through_a_real_day() -> None:
    """Money conservation (Law 1) holds across a meaningful tick window on the full island map."""
    world = bootstrap_genesis(seed=42, settler_count=8)
    total = world.ledger.total_cents()
    for _ in range(120):
        advance_tick(world)
    assert world.ledger.total_cents() == total


def test_genesis_islands_settlers_claim_plots_across_multiple_islands() -> None:
    """With ocean centre, settlers naturally fan out and land on more than one island."""
    world = bootstrap_genesis(seed=42, settler_count=24)
    for _ in range(80):
        advance_tick(world)
    comps = _flood_fill_land_components(world)
    big = comps[:4]
    big_sets = [set(c) for c in big]
    islands_with_claims: set[int] = set()
    for plot in world.plots.values():
        if not str(plot.owner or "").startswith("settler_"):
            continue
        for i, comp_set in enumerate(big_sets):
            if (plot.x, plot.y) in comp_set:
                islands_with_claims.add(i)
                break
    assert len(islands_with_claims) >= 2, (
        f"expected settler claims to land on ≥2 islands; got {len(islands_with_claims)}"
    )
