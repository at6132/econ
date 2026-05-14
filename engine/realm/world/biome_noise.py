"""Deterministic biome fields for frontier plot generation (coherent regions, not iid tiles).

Genesis "four islands" layout (added 2026-05): see :func:`terrain_for_genesis_island_cell`
and :func:`genesis_island_centers`. Each quadrant of a sufficiently large map holds one
elliptical landmass with an FBM-wobbled coastline; deep water fills the cross-shaped gap
between them, forcing inter-island shipping for the demand layer in non-hub islands.
"""

from __future__ import annotations

import math

from realm.core.rng import make_rng
from realm.world.terrain import Terrain


def _n01(seed: int, ix: int, iy: int) -> float:
    return make_rng(seed, f"sn:{ix}:{iy}").random()


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


# ─────────────────── Genesis four-islands layout ───────────────────

# Minimum map size that supports the four-island mask. Below this we fall back
# to a regular continent map (tests with tiny grids stay valid). Tuned so each
# island has room for FBM-driven biome variation and a coastline buffer.
GENESIS_ISLAND_MIN_WIDTH: int = 48
GENESIS_ISLAND_MIN_HEIGHT: int = 36

# Beach (shallow water) thickness, in units of normalised ellipse distance
# beyond the island core. d_eff < 1.0 → land; 1.0..1.0+BEACH → shallow; beyond → deep.
_GENESIS_BEACH_BAND: float = 0.15

# Magnitude of the FBM coastline wobble (in units of normalised ellipse distance).
# Larger values produce more jagged / "organic" shorelines; smaller values are
# closer to smooth ellipses. ±0.18 → noticeable bays + peninsulas without ruining
# island integrity.
_GENESIS_COAST_WOBBLE: float = 0.18


def genesis_island_centers(width: int, height: int) -> list[tuple[int, int]]:
    """Return the four island centre coordinates (NW, NE, SW, SE) for a w × h map.

    Centres sit at the quadrant midpoints so islands are evenly spaced and the
    cross-shaped ocean has equal arm length in each direction.
    """
    w = max(1, int(width))
    h = max(1, int(height))
    return [
        (w // 4, h // 4),
        (3 * w // 4, h // 4),
        (w // 4, 3 * h // 4),
        (3 * w // 4, 3 * h // 4),
    ]


def genesis_island_radii(width: int, height: int) -> tuple[int, int]:
    """Half-axes (rx, ry) of each island ellipse for a w × h map.

    Tuned so adjacent islands are separated by a non-trivial ocean gap (~10–14
    tiles of open water) on the default 96 × 72 grid, while still occupying
    most of their quadrant. Both axes are >= 1.
    """
    w = max(1, int(width))
    h = max(1, int(height))
    rx = max(1, w // 6)
    ry = max(1, h // 6)
    return (rx, ry)


def genesis_island_layout_supported(width: int, height: int) -> bool:
    """True if the map is big enough for the four-island layout."""
    return int(width) >= GENESIS_ISLAND_MIN_WIDTH and int(height) >= GENESIS_ISLAND_MIN_HEIGHT


def _nearest_island_normalised_distance(
    x: int, y: int, centers: list[tuple[int, int]], rx: int, ry: int
) -> float:
    """Normalised elliptical distance to the closest island centre (0 at centre, 1 at edge)."""
    rx_f = float(max(1, rx))
    ry_f = float(max(1, ry))
    best = float("inf")
    for cx, cy in centers:
        dx = (x - cx) / rx_f
        dy = (y - cy) / ry_f
        d2 = dx * dx + dy * dy
        if d2 < best:
            best = d2
    return math.sqrt(best)


def terrain_for_genesis_island_cell(seed: int, x: int, y: int, width: int, height: int) -> Terrain:
    """Genesis "four islands" terrain for cell ``(x, y)`` on a ``width × height`` map.

    The world is partitioned into four ellipse-shaped islands (one per quadrant)
    separated by a cross-shaped ocean. Inside each island we delegate to
    :func:`terrain_for_cell` for natural biome variation; any water that the
    inland noise would have produced is coerced to PLAINS so islands feel
    solidly land. Around each island we emit a ring of WATER_SHALLOW (the
    "beach") that automatically makes the outer plots coastal. Beyond the beach
    is WATER_DEEP open ocean.

    Determinism: same ``(seed, x, y, width, height)`` always yields the same
    terrain (Law 9 — the wobble FBM is seeded with a fixed offset).
    """
    centers = genesis_island_centers(width, height)
    rx, ry = genesis_island_radii(width, height)
    d = _nearest_island_normalised_distance(x, y, centers, rx, ry)
    # Coastline wobble centred on 0 (so it can push the shoreline either way).
    wob = fbm(seed + 911, x * 0.09, y * 0.09, 3) - 0.5
    d_eff = d + _GENESIS_COAST_WOBBLE * 2.0 * wob
    if d_eff >= 1.0 + _GENESIS_BEACH_BAND:
        return Terrain.WATER_DEEP
    if d_eff >= 1.0:
        return Terrain.WATER_SHALLOW
    inland = terrain_for_cell(seed, x, y)
    if inland in (Terrain.WATER_DEEP, Terrain.WATER_SHALLOW):
        # Keep islands solid; lakes inside the landmass would visually break the
        # "four islands far apart" intent and would also create tiny isolated
        # ponds the shipping market cannot meaningfully use.
        return Terrain.PLAINS
    return inland
