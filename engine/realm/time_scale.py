"""Simulation calendar: **1 tick = 1 in-game minute**; **1440 ticks = 1 game-day**.

Durations that were tuned in an abstract “short tick” prototype are scaled by
``LEGACY_TICK_MULTIPLIER`` so batch production, transit, and narrative cadences
land in a sensible calendar band. Real-time playback (solo UI sleep, public
shard tick pacing) stays outside the engine — see ``realm_docs/09_TECH_ARCHITECTURE.md``.
"""

from __future__ import annotations

from typing import Final

TICKS_PER_GAME_DAY: Final[int] = 1440

# Old recipe durations (2–5) implied “few sim steps”; map to ~2–5 in-game hours.
LEGACY_TICK_MULTIPLIER: Final[int] = 60

# Construction: cash/materials commit immediately; structure becomes usable after this many ticks.
BUILD_SIMPLE_TICKS: Final[int] = 120  # 2 hours — sheds, stockades
BUILD_CONTRACTED_TICKS: Final[int] = 360  # 6 hours — workshops / contracted shells

# Shipping: Manhattan distance × per-tile minutes + base handling.
TRANSIT_TICKS_PER_TILE: Final[int] = 15
TRANSIT_BASE_TICKS: Final[int] = 30


def legacy_scaled(n: int) -> int:
    """Scale a small integer from the abstract-tick prototype to minute-ticks."""
    return max(1, int(n) * LEGACY_TICK_MULTIPLIER)


def building_operational(row: dict, *, at_tick: int) -> bool:
    """False while ``completes_at_tick`` is in the future (construction in flight)."""
    c = row.get("completes_at_tick")
    if c is None:
        return True
    return at_tick >= int(c)
