"""Geographic clustering layers (Sprint 3 — Phase B).

Mineral belts and population density are *emergent* from layered FBM noise:
the seed picks where each belt sits, but the structural pattern — a few
distinct belts per material — is constant.

All functions here are deterministic in ``(seed, x, y)``: re-rolling the
same seed always produces the same belts, but a different seed shifts them.

Two flavours of layer:

- ``mineral_bias_*`` returns a ``[0..1]`` bias factor that gets *blended*
  into the per-plot grade roll in :func:`realm.world._subsurface_roll`.
  Inside a belt the bias is high (≥ ~0.6); outside it falls off to ~0.1.
- :func:`population_density_for_cell` returns the density on the same
  ``[0..1]`` scale, defined as an exponential falloff from population hubs
  plus a small ambient layer.
"""

from __future__ import annotations

import math
from typing import Final

from realm.biome_noise import fbm


__all__ = [
    "mineral_bias_iron",
    "mineral_bias_coal",
    "mineral_bias_clay",
    "mineral_bias_copper",
    "mineral_bias_timber",
    "population_density_for_cell",
    "POPULATION_HUB_DENSITY_PEAK",
    "POPULATION_FRONTIER_DENSITY_BASELINE",
    "POP_HUB_DENSITY_DECAY",
    "CLAIM_COST_BASE_CENTS",
    "CLAIM_COST_PEAK_CENTS",
    "claim_cost_cents_from_density",
]


# ─────────────────── claim cost ───────────────────


CLAIM_COST_BASE_CENTS: Final[int] = 0
CLAIM_COST_PEAK_CENTS: Final[int] = 5_00  # $5 on the most-dense plots


def claim_cost_cents_from_density(density: float) -> int:
    """Quadratic ramp: frontier (≈0.05) ≈ free, dense (0.9+) approaches the peak."""
    d = max(0.0, min(1.0, float(density)))
    return CLAIM_COST_BASE_CENTS + int(round(d * d * CLAIM_COST_PEAK_CENTS))


# ─────────────────── belt noise primitives ───────────────────


def _belt_field(seed: int, x: int, y: int, *, key: int, scale: float) -> float:
    """A single low-frequency FBM channel used as a belt mask.

    The smaller ``scale`` is, the wider and more contiguous the belt becomes.
    """
    return fbm(seed + key, x * scale, y * scale, 3)


def mineral_bias_iron(seed: int, x: int, y: int) -> float:
    """Diagonal iron belt — high values trace an oblique band across the map."""
    base = _belt_field(seed, x, y, key=701, scale=0.045)
    # Oblique component: project (x, y) onto a diagonal direction picked from the
    # seed so the belt's orientation varies per world.
    angle = (math.tau * fbm(seed + 731, 0.0, 0.0, 1))
    proj = math.cos(angle) * x + math.sin(angle) * y
    # Convert ``proj`` to a 0..1 strip indicator with a soft cosine profile.
    period = 26.0  # ≈ a few tiles wider than POWER_COVERAGE_RADIUS
    strip = 0.5 + 0.5 * math.cos(proj / period * math.tau)
    return min(1.0, 0.5 * base + 0.5 * strip)


def mineral_bias_coal(seed: int, x: int, y: int) -> float:
    """Coal coast / inland-adjacent belt — wide, lower-frequency."""
    return _belt_field(seed, x, y, key=719, scale=0.035)


def mineral_bias_clay(seed: int, x: int, y: int) -> float:
    """Clay valley — concentrated mid-frequency lobe."""
    return _belt_field(seed, x, y, key=727, scale=0.05)


def mineral_bias_copper(seed: int, x: int, y: int) -> float:
    """Copper highlands — small, intense lobes."""
    return _belt_field(seed, x, y, key=733, scale=0.06)


def mineral_bias_timber(seed: int, x: int, y: int) -> float:
    """Timber ridge — broad coherent forest-region preference."""
    return _belt_field(seed, x, y, key=739, scale=0.04)


# ─────────────────── population density ───────────────────


POPULATION_HUB_DENSITY_PEAK: Final[float] = 0.95
POPULATION_FRONTIER_DENSITY_BASELINE: Final[float] = 0.05
POP_HUB_DENSITY_DECAY: Final[float] = 14.0  # tiles for ~37 % falloff


def population_density_for_cell(
    x: int,
    y: int,
    hubs: list[tuple[int, int]],
    *,
    decay_tiles: float = POP_HUB_DENSITY_DECAY,
) -> float:
    """Exponential falloff from the nearest population hub.

    Frontier regions saturate at :data:`POPULATION_FRONTIER_DENSITY_BASELINE`
    (≈ 0.05); plots adjacent to a hub approach
    :data:`POPULATION_HUB_DENSITY_PEAK` (≈ 0.95).
    """
    if not hubs:
        return POPULATION_FRONTIER_DENSITY_BASELINE
    best = min(abs(hx - x) + abs(hy - y) for hx, hy in hubs)
    falloff = math.exp(-best / max(1.0, decay_tiles))
    return (
        POPULATION_FRONTIER_DENSITY_BASELINE
        + (POPULATION_HUB_DENSITY_PEAK - POPULATION_FRONTIER_DENSITY_BASELINE) * falloff
    )
