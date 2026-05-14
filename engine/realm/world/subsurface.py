"""Worldgen subsurface composition: ``SubsurfaceRoll`` dataclass and
``_subsurface_roll`` generator.

Extracted from ``realm.world.world`` to keep that module focused on
world-state dataclasses and bootstrap. Imported back by ``world.py`` and
re-exported through ``realm.world`` so callers (Plot defaults, dev API)
keep their existing import paths.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from realm.world.terrain import Terrain


@dataclass(frozen=True, slots=True)
class SubsurfaceRoll:
    """Hidden composition until surveyed.

    Tier-1 (iron/copper/clay/coal) and Tier-2 grades (sulfur..silica) reveal on
    standard ``survey_plot``. Tier-3 (platinum/oil_shale/rare_earth) stay hidden
    from the API view until ``Plot.deep_surveyed`` flips to True.
    """

    iron_ore_grade: float  # 0..1
    copper_ore_grade: float
    clay_grade: float
    coal_grade: float
    # Tier-2 mineral grades — visible after standard survey, but extraction recipes
    # are locked behind discovery (assay system).
    sulfur_grade: float = 0.0
    saltpeter_grade: float = 0.0
    tin_grade: float = 0.0
    lead_grade: float = 0.0
    phosphate_grade: float = 0.0
    silica_grade: float = 0.0
    # Tier-3 ultra-rare grades — hidden from the API until ``deep_surveyed`` on the plot.
    platinum_grade: float = 0.0
    oil_shale_grade: float = 0.0
    rare_earth_grade: float = 0.0


def subsurface_roll(
    rng: random.Random,
    terrain: Terrain,
    *,
    correlate: bool,
    seed: int = 0,
    x: int = 0,
    y: int = 0,
    apply_belts: bool = False,
) -> SubsurfaceRoll:
    """Terrain-correlated subsurface when ``correlate`` (stronger ore under mountains, etc.).

    Tier-2 grades are rolled here too (sulfur/saltpeter/tin/lead/phosphate/silica). They are
    visible after standard ``survey_plot`` (same as Tier-1 grades), but the *recipes* that mine
    them are locked behind discovery (assay system) — so settlers/players cannot exploit them
    until they unlock the relevant recipe via assay.
    Tier-3 grades (platinum/oil_shale/rare_earth) are rolled rare and remain hidden from the
    ``/world`` API until a deep_survey reveals them on a per-plot basis (see ``deep_surveyed``).
    """
    ir = rng.random()
    cu = rng.random()
    cl = rng.random()
    co = rng.random()
    su = rng.random()
    sp = rng.random()
    tn = rng.random()
    ld = rng.random()
    ph = rng.random()
    si = rng.random()
    pt = rng.random()
    osh = rng.random()
    re = rng.random()
    if correlate:
        if terrain == Terrain.MOUNTAIN:
            ir = min(1.0, ir * 0.38 + 0.48)
            cu = min(1.0, cu * 0.42 + 0.44)
            co = min(1.0, co * 0.45 + 0.38)
            ld = min(1.0, ld * 0.48 + 0.34)
            tn = min(1.0, tn * 0.55 + 0.18)
        elif terrain == Terrain.FOREST:
            cl = min(1.0, cl * 0.48 + 0.34)
            ph = min(1.0, ph * 0.55 + 0.18)
        elif terrain == Terrain.PLAINS:
            cl = min(1.0, cl * 0.52 + 0.28)
            ph = min(1.0, ph * 0.48 + 0.30)
            sp = min(1.0, sp * 0.58 + 0.16)
        elif terrain == Terrain.SWAMP:
            cl = min(1.0, cl * 0.46 + 0.36)
            cu = min(1.0, cu * 0.48 + 0.32)
            su = min(1.0, su * 0.46 + 0.32)
            osh = min(1.0, osh * 0.62 + 0.08)
        elif terrain == Terrain.DESERT:
            co = min(1.0, co * 0.48 + 0.36)
            sp = min(1.0, sp * 0.42 + 0.40)
            si = min(1.0, si * 0.52 + 0.28)
        elif terrain == Terrain.TUNDRA:
            ir *= 0.85
            co *= 0.85
            su = min(1.0, su * 0.55 + 0.18)
        elif terrain in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP):
            damp = 0.28
            ir *= damp
            cu *= damp
            cl *= damp
            co *= damp
            su *= damp
            sp *= damp
            tn *= damp
            ld *= damp
            ph *= damp
            si *= damp
            pt *= damp
            osh *= damp
            re *= damp
    if apply_belts:
        # Sprint 3 — Phase B.1: layered low-frequency noise creates mineral belts.
        # The bias blends with the iid roll so within a belt the average grade
        # lands at ~0.55–0.65 while neighbouring tiles still vary plot-to-plot.
        from realm.world.geo_clustering import (
            mineral_bias_clay,
            mineral_bias_coal,
            mineral_bias_copper,
            mineral_bias_iron,
        )

        bi = mineral_bias_iron(seed, x, y)
        bc = mineral_bias_coal(seed, x, y)
        bcl = mineral_bias_clay(seed, x, y)
        bcu = mineral_bias_copper(seed, x, y)
        ir = min(1.0, ir * 0.45 + bi * 0.55)
        co = min(1.0, co * 0.55 + bc * 0.45)
        cl = min(1.0, cl * 0.55 + bcl * 0.45)
        cu = min(1.0, cu * 0.55 + bcu * 0.45)
    # Tier-3 rarity gates (cliff most plots to 0 so only a few are interesting).
    pt = pt if pt > 0.97 else 0.0
    osh = osh if osh > 0.95 else 0.0
    re = re if re > 0.98 else 0.0
    # Normalize Tier-3 to the 0..1 range for the few that survive the cliff (so 0.1 gate still bites).
    if pt > 0.0:
        pt = min(1.0, (pt - 0.97) / 0.03 * 0.8 + 0.15)
    if osh > 0.0:
        osh = min(1.0, (osh - 0.95) / 0.05 * 0.8 + 0.12)
    if re > 0.0:
        re = min(1.0, (re - 0.98) / 0.02 * 0.8 + 0.18)
    return SubsurfaceRoll(
        iron_ore_grade=ir,
        copper_ore_grade=cu,
        clay_grade=cl,
        coal_grade=co,
        sulfur_grade=su,
        saltpeter_grade=sp,
        tin_grade=tn,
        lead_grade=ld,
        phosphate_grade=ph,
        silica_grade=si,
        platinum_grade=pt,
        oil_shale_grade=osh,
        rare_earth_grade=re,
    )
