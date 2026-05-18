"""Deterministic biome fields for frontier plot generation (coherent regions, not iid tiles).

Genesis layouts:

* **Continental** (default on large grids) — seed-derived land lobes scattered across
  the map with ``make_rng`` placement, FBM coast wobble, and archipelago speckle.
  Same seed always yields the same coastlines (Law 9).
"""

from __future__ import annotations

import math
from collections.abc import Callable

from realm.core.ids import PlotId
from realm.core.rng import make_rng
from realm.world.terrain import Terrain

## Deep-ocean ring around the world map (cells from each edge).
MAP_OCEAN_BORDER_DEPTH: int = 2

_n01_cache: dict[tuple[int, int, int], float] = {}


def _n01(seed: int, ix: int, iy: int) -> float:
    key = (seed, ix, iy)
    v = _n01_cache.get(key)
    if v is not None:
        return v
    v = make_rng(seed, f"sn:{ix}:{iy}").random()
    _n01_cache[key] = v
    return v


def clear_noise_cache() -> None:
    """Release memory after worldgen completes."""
    _n01_cache.clear()
    _continental_lobes_cache.clear()


def _smooth(seed: int, fx: float, fy: float) -> float:
    x0 = math.floor(fx)
    y0 = math.floor(fy)
    tx = fx - x0
    ty = fy - y0

    def lerp(a: float, b: float, t: float) -> float:
        s = t * t * (3 - 2 * t)
        return a + (b - a) * s

    xi0 = int(x0)
    yi0 = int(y0)
    n00 = _n01(seed, xi0, yi0)
    n10 = _n01(seed, xi0 + 1, yi0)
    n01 = _n01(seed, xi0, yi0 + 1)
    n11 = _n01(seed, xi0 + 1, yi0 + 1)
    return lerp(lerp(n00, n10, tx), lerp(n01, n11, tx), ty)


def fbm(seed: int, x: float, y: float, octaves: int = 4) -> float:
    v = 0.0
    amp = 1.0
    freq = 1.0
    tot = 0.0
    for _ in range(octaves):
        v += amp * _smooth(seed, x * freq, y * freq)
        tot += amp
        amp *= 0.5
        freq *= 2.0
    return v / tot if tot else 0.0


def map_ocean_border_depth(
    width: int, height: int, depth: int = MAP_OCEAN_BORDER_DEPTH
) -> int:
    """Effective border thickness (clamped so tiny grids stay playable)."""
    if width < 1 or height < 1:
        return 1
    return max(1, min(depth, width // 2, height // 2))


def is_world_map_edge(
    x: int,
    y: int,
    width: int,
    height: int,
    depth: int = MAP_OCEAN_BORDER_DEPTH,
) -> bool:
    """True when ``(x, y)`` lies in the ocean border band (map must not end on land)."""
    d = map_ocean_border_depth(width, height, depth)
    return x < d or y < d or x >= width - d or y >= height - d


def enforce_map_ocean_border(
    plots: dict[PlotId, Plot],
    width: int,
    height: int,
    *,
    seed: int | None = None,
) -> None:
    """Ensure border-band cells are dedicated 1×1 ``water_deep`` plots.

    Multi-cell deeds that straddle the border are split so interior tiles keep
    their deed while edge tiles become ocean plots (``p-{x}-{y}``).
    """
    from realm.core.rng import make_rng
    from realm.world.plot_scale import plot_world_cells_tuple
    from realm.world.world import Plot, _subsurface_roll

    if width < 1 or height < 1:
        return

    def _water_subsurface(cx: int, cy: int) -> object:
        rng = make_rng(seed if seed is not None else 0, f"ocean-border:{cx}:{cy}")
        return _subsurface_roll(rng, Terrain.WATER_DEEP, correlate=False)

    for y in range(height):
        for x in range(width):
            if not is_world_map_edge(x, y, width, height):
                continue
            water_pid = PlotId(f"p-{x}-{y}")
            cell = (x, y)

            holder: Plot | None = None
            holder_id: PlotId | None = None
            for pid, plot in plots.items():
                if cell in plot_world_cells_tuple(plot):
                    holder = plot
                    holder_id = pid
                    break

            if holder is None:
                plots[water_pid] = Plot(
                    plot_id=water_pid,
                    x=x,
                    y=y,
                    terrain=Terrain.WATER_DEEP,
                    owner=None,
                    subsurface=_water_subsurface(x, y),
                    world_cells=(cell,),
                )
                continue

            cells = list(plot_world_cells_tuple(holder))
            remnant_terrain = holder.terrain
            remnant_owner = holder.owner
            remnant_sub = holder.subsurface
            remnant_surveyed = holder.surveyed
            remnant_deep = holder.deep_surveyed

            if len(cells) == 1:
                holder.terrain = Terrain.WATER_DEEP
                holder.owner = None
                holder.x = x
                holder.y = y
                holder.world_cells = (cell,)
                if holder_id != water_pid:
                    plots[water_pid] = holder
                    del plots[holder_id]  # type: ignore[arg-type]
                continue

            remaining = tuple(c for c in cells if c != cell)
            plots[water_pid] = Plot(
                plot_id=water_pid,
                x=x,
                y=y,
                terrain=Terrain.WATER_DEEP,
                owner=None,
                subsurface=_water_subsurface(x, y),
                world_cells=(cell,),
            )
            if not remaining:
                if holder_id is not None and holder_id != water_pid:
                    del plots[holder_id]
                continue

            min_x = min(c[0] for c in remaining)
            min_y = min(c[1] for c in remaining)
            remnant_pid = PlotId(f"p-{min_x}-{min_y}")
            if remnant_pid == water_pid:
                ax, ay = next(c for c in sorted(remaining) if c != cell)
                remnant_pid = PlotId(f"p-{ax}-{ay}")
            if holder_id == water_pid:
                plots[remnant_pid] = Plot(
                    plot_id=remnant_pid,
                    x=min_x,
                    y=min_y,
                    terrain=remnant_terrain,
                    owner=remnant_owner,
                    subsurface=remnant_sub,
                    surveyed=remnant_surveyed,
                    deep_surveyed=remnant_deep,
                    world_cells=remaining,
                )
            else:
                holder.world_cells = remaining
                holder.x = min_x
                holder.y = min_y


def ensure_world_ocean_border(world: object) -> None:
    """Apply :func:`enforce_map_ocean_border` to a live :class:`World`."""
    from realm.world.plot_scale import plot_world_cells_tuple
    from realm.world.world import World

    if not isinstance(world, World):
        return
    scen = world.scenario_state if isinstance(world.scenario_state, dict) else {}
    gw = int(scen.get("grid_width", 0))
    gh = int(scen.get("grid_height", 0))
    if gw <= 0 or gh <= 0:
        gw = 0
        gh = 0
        for plot in world.plots.values():
            for cx, cy in plot_world_cells_tuple(plot):
                gw = max(gw, cx + 1)
                gh = max(gh, cy + 1)
    if gw <= 0 or gh <= 0:
        return
    scen["grid_width"] = gw
    scen["grid_height"] = gh
    enforce_map_ocean_border(world.plots, gw, gh, seed=int(world.seed))
    from realm.world.plot_parcels import refresh_world_cell_index

    refresh_world_cell_index(world)


def terrain_with_ocean_border(
    pick: Callable[[int, int, int], Terrain],
    *,
    width: int,
    height: int,
) -> Callable[[int, int, int], Terrain]:
    """Wrap a terrain picker so the map perimeter is always deep ocean."""

    def wrapped(seed: int, x: int, y: int) -> Terrain:
        if is_world_map_edge(x, y, width, height):
            return Terrain.WATER_DEEP
        return pick(seed, x, y)

    return wrapped


def terrain_for_cell(seed: int, x: int, y: int) -> Terrain:
    """Domain-warped FBM → terrain; same seed always yields the same map."""
    cx, cy = x + 0.5, y + 0.5
    wx = cx + 2.8 * fbm(seed + 101, cx * 0.08, cy * 0.08, 3)
    wy = cy + 2.8 * fbm(seed + 202, cx * 0.08 + 5.0, cy * 0.08 + 1.7, 3)
    elev = fbm(seed, wx * 0.11, wy * 0.11, 4)
    moist = fbm(seed + 11, wx * 0.13 + 20.0, wy * 0.13, 4)
    heat = fbm(seed + 23, wx * 0.09 + 40.0, wy * 0.09 + 2.0, 3)

    if elev < 0.24:
        return Terrain.WATER_DEEP if elev < 0.12 else Terrain.WATER_SHALLOW
    if elev > 0.68:
        return Terrain.MOUNTAIN
    if moist > 0.58 and 0.36 < heat < 0.64:
        return Terrain.SWAMP
    if moist > 0.52 and heat < 0.42:
        return Terrain.FOREST
    if heat > 0.62 and moist < 0.45:
        return Terrain.DESERT
    if heat < 0.28:
        return Terrain.TUNDRA
    return Terrain.PLAINS


# ─────────────────── Phase 10 — continental layout ───────────────────

# Layered FBM produces a continental mask: large land continents, scattered
# islands, wide ocean gaps. The mask is used as a multiplier on elevation so
# the noise still shapes terrain *within* a continent (mountains, hills,
# deserts), but ocean dominates everywhere outside the mask.

# Default Genesis solo map (continental layout when plot count ≥ threshold).
GENESIS_DEFAULT_GRID_WIDTH: int = 320
GENESIS_DEFAULT_GRID_HEIGHT: int = 240

# Below this many plots, fall back to ``terrain_for_cell`` (legacy single-
# continent map) so existing tests with tiny grids stay valid. Backwards
# compat is mandatory.
CONTINENTAL_LAYOUT_MIN_PLOTS: int = 10_000

# Mask thresholds (after FBM): below LAND_THRESHOLD is ocean, between LAND_
# and SHALLOW_THRESHOLD is the beach band, above is land.
_CONTINENTAL_LAND_THRESHOLD: float = 0.25
_CONTINENTAL_SHALLOW_THRESHOLD: float = 0.30


# (cx, cy, radius) in normalized map coords — cached per seed.
_ContinentalLobe = tuple[float, float, float]
_continental_lobes_cache: dict[int, list[_ContinentalLobe]] = {}


def continental_layout_lobes(seed: int) -> list[_ContinentalLobe]:
    """Seed-derived land lobes for the continental layout (for tests / debug).

    Each lobe is ``(center_x, center_y, radius)`` in ``[0, 1]`` space. Placement
    uses ``make_rng(seed, "continental_land_lobes")`` so the same seed always
    yields the same set; failed placements are skipped rather than retried with
    weaker spacing rules.
    """
    cached = _continental_lobes_cache.get(int(seed))
    if cached is not None:
        return cached

    rng = make_rng(int(seed), "continental_land_lobes")
    n_major = 5 + rng.randrange(5)
    n_minor = 10 + rng.randrange(8)
    lobes: list[_ContinentalLobe] = []

    def _spacing_ok(cx: float, cy: float, radius: float) -> bool:
        for ox, oy, orad in lobes:
            gap = math.hypot(cx - ox, cy - oy)
            min_gap = (radius + orad) * 1.05 + 0.04
            if gap < min_gap:
                return False
        return True

    def _try_place(r_lo: float, r_hi: float) -> bool:
        for _ in range(120):
            cx = 0.06 + rng.random() * 0.88
            cy = 0.06 + rng.random() * 0.88
            radius = r_lo + rng.random() * (r_hi - r_lo)
            if _spacing_ok(cx, cy, radius):
                lobes.append((cx, cy, radius))
                return True
        return False

    for _ in range(n_major):
        _try_place(0.07, 0.13)
    for _ in range(n_minor):
        _try_place(0.025, 0.055)

    _continental_lobes_cache[int(seed)] = lobes
    return lobes


def _continental_mask(seed: int, x: int, y: int, width: int, height: int) -> float:
    """Continental land mask in ``[0, 1]`` — nearest seed-placed lobe only.

    Taking the max influence across all lobes merges separate landmasses into a
    few mega-continents; assigning each cell to its nearest lobe centre keeps
    oceans between them.
    """
    cx = float(x) / max(1.0, float(width))
    cy = float(y) / max(1.0, float(height))
    lobes = continental_layout_lobes(seed)
    if not lobes:
        return 0.0

    nearest = min(lobes, key=lambda lb: math.hypot(cx - lb[0], cy - lb[1]))
    lx, ly, radius = nearest
    dist = math.hypot(cx - lx, cy - ly)
    wobble = (fbm(seed + int(lx * 733) + int(ly * 991), cx * 10.0, cy * 10.0, 3) - 0.5) * 0.06
    total = max(0.0, 1.0 - (dist - wobble) / max(radius, 0.02))

    pole_penalty = abs(cy - 0.5) * 0.28
    return max(0.0, total - pole_penalty)


def continental_layout_terrain(
    seed: int, x: int, y: int, width: int, height: int
) -> Terrain:
    """Procedural continental terrain via layered FBM noise (Phase 10).

    Produces a small number of large continents, several medium islands, a
    sprinkle of islets, and ocean covering most of the map. Each seed gives a
    different layout but the structural pattern (continents + ocean + islands)
    always emerges.

    Below ``CONTINENTAL_LAYOUT_MIN_PLOTS`` callers should fall back to
    :func:`terrain_for_cell` (the single-continent legacy map) — tiny test
    grids do not have room for the FBM stack to settle into recognisable
    landmasses.
    """
    if is_world_map_edge(x, y, width, height):
        return Terrain.WATER_DEEP
    mask = _continental_mask(seed, x, y, width, height)
    if mask < _CONTINENTAL_LAND_THRESHOLD:
        # Most of the world is ocean. Deeper ocean offshore, shallow ocean
        # in a narrow band right next to continents (the FBM hands us a
        # gradient automatically — values between 0.15 and 0.25 are the
        # offshore band).
        return Terrain.WATER_DEEP if mask < 0.15 else Terrain.WATER_SHALLOW
    if mask < _CONTINENTAL_SHALLOW_THRESHOLD:
        return Terrain.WATER_SHALLOW
    cx = float(x) / max(1.0, float(width))
    cy = float(y) / max(1.0, float(height))
    chaos = 0.6 + fbm(seed + 9999, 0.0, 0.0, 1) * 0.8
    elev = fbm(seed + 1, cx * 6.0, cy * 6.0, 6) * mask
    moist = fbm(seed + 2, cx * 5.0 + 10.0, cy * 5.0, 6)
    heat = 1.0 - abs(cy - 0.5) * 2.0
    heat += fbm(seed + 3, cx * 4.0 + 20.0, cy * 4.0, 3) * 0.3
    mtn_thr = 0.72 - (chaos - 0.6) * 0.08
    hill_thr = 0.55 - (chaos - 0.6) * 0.06
    if elev > mtn_thr:
        return Terrain.MOUNTAIN
    if elev > hill_thr and moist < 0.4:
        return Terrain.HILLS
    if moist > 0.60 and heat > 0.55:
        return Terrain.SWAMP
    if moist > 0.55 and heat < 0.50:
        return Terrain.FOREST
    if heat > 0.70 and moist < 0.38:
        return Terrain.DESERT
    if heat < 0.25:
        return Terrain.TUNDRA
    return Terrain.PLAINS


def continental_layout_supported(width: int, height: int) -> bool:
    """True when the grid is large enough for the continental layout."""
    return int(width) * int(height) >= CONTINENTAL_LAYOUT_MIN_PLOTS
