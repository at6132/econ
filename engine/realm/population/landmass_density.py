"""Landmass-scaled Genesis population targets (labor + entrepreneurs).

Labor and settler counts derive from each connected landmass's land-plot
count and its continent / island / islet classification — not fixed per-id
tables. Keeps small test grids cheap while continental worlds seed proportionally.
"""

from __future__ import annotations

from typing import Final

from realm.world import World

# Target: roughly one laborer per N land plots (non-ocean cells in component).
PLOTS_PER_LABORER_BY_LANDMASS_TYPE: Final[dict[str, int]] = {
    "continent": 8,
    "island": 4,
    "islet": 3,
}

MIN_LABORERS_BY_LANDMASS_TYPE: Final[dict[str, int]] = {
    "continent": 80,
    "island": 40,
    "islet": 12,
}

# Boot settlers ≈ half the labor target, bounded for solo perf / design caps.
SETTLER_PER_LABORER_DIVISOR: Final[int] = 2
GENESIS_MIN_BOOT_SETTLERS: Final[int] = 250
GENESIS_MAX_BOOT_SETTLERS: Final[int] = 1000

__all__ = [
    "PLOTS_PER_LABORER_BY_LANDMASS_TYPE",
    "MIN_LABORERS_BY_LANDMASS_TYPE",
    "landmass_land_plot_count",
    "laborer_target_count_for_landmass",
    "total_laborer_target_for_world",
    "genesis_settler_count_for_world",
]


def landmass_land_plot_count(world: World, landmass_id: int) -> int:
    return int((world.landmass_plot_count or {}).get(int(landmass_id), 0))


def _landmass_type(world: World, landmass_id: int) -> str:
    return str((world.landmass_type or {}).get(int(landmass_id), "island"))


def laborer_target_count_for_landmass(world: World, landmass_id: int) -> int:
    """Deterministic laborer headcount for one landmass at bootstrap."""
    plots = landmass_land_plot_count(world, landmass_id)
    if plots <= 0:
        return 0
    ltype = _landmass_type(world, landmass_id)
    plots_per = PLOTS_PER_LABORER_BY_LANDMASS_TYPE.get(ltype, 4)
    floor = MIN_LABORERS_BY_LANDMASS_TYPE.get(ltype, 40)
    from_density = plots // max(1, plots_per)
    return max(floor, from_density)


def total_laborer_target_for_world(world: World) -> int:
    counts = world.landmass_plot_count or {}
    return sum(laborer_target_count_for_landmass(world, lid) for lid in counts)


def genesis_settler_count_for_world(world: World) -> int:
    """Initial settler cohort size from seeded labor demand (after landmasses exist)."""
    labor_target = total_laborer_target_for_world(world)
    if labor_target <= 0:
        return GENESIS_MIN_BOOT_SETTLERS
    raw = max(GENESIS_MIN_BOOT_SETTLERS, labor_target // SETTLER_PER_LABORER_DIVISOR)
    return min(GENESIS_MAX_BOOT_SETTLERS, raw)
