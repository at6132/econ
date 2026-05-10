"""Deterministic biome fields for frontier plot generation (coherent regions, not iid tiles)."""

from __future__ import annotations

import math

from realm.rng import make_rng
from realm.terrain import Terrain


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
