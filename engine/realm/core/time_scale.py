"""Simulation calendar: **1 tick = 1 in-game minute**; **1440 ticks = 1 game-day**.

Durations that were tuned in an abstract “short tick” prototype are scaled by
``LEGACY_TICK_MULTIPLIER`` so batch production, transit, and narrative cadences
land in a sensible calendar band.

Wall-clock pacing (host loop sleep, speed multipliers) lives next to the
calendar so every layer reads the same constants instead of hard-coding
``1440`` / ``3600`` / ``2.5`` in scattered places. Game logic still uses
``world.tick`` only — wall clock affects **how fast** ticks happen, never
**what** a tick computes (Law 9 — determinism).
"""

from __future__ import annotations

from typing import Final

TICKS_PER_GAME_DAY: Final[int] = 1440

# Old recipe durations (2–5) implied “few sim steps”; map to ~2–5 in-game hours.
LEGACY_TICK_MULTIPLIER: Final[int] = 60

# Construction: cash/materials commit immediately; structure becomes usable after this many ticks.
BUILD_SIMPLE_TICKS: Final[int] = 60  # 1 hour — sheds, stockades
BUILD_CONTRACTED_TICKS: Final[int] = 180  # 3 hours — workshops / contracted shells

# Shipping: Manhattan distance × per-tile minutes + base handling.
TRANSIT_TICKS_PER_TILE: Final[int] = 15
TRANSIT_BASE_TICKS: Final[int] = 30

# ── Wall-clock pacing ────────────────────────────────────────────────────────
# Canon (Law 2 / doc 09): one in-game day = one real hour at 1× speed.
REAL_SECONDS_PER_GAME_DAY: Final[int] = 3600

# Derived: 1440 ticks / 3600 s = 0.4 ticks per real second → 2.5 s per tick at 1×.
TICKS_PER_REAL_SECOND_AT_1X: Final[float] = TICKS_PER_GAME_DAY / REAL_SECONDS_PER_GAME_DAY
REAL_SECONDS_PER_TICK_AT_1X: Final[float] = REAL_SECONDS_PER_GAME_DAY / TICKS_PER_GAME_DAY

# Speed multipliers a solo player can pick. ``0.0`` = paused (host loop sleeps
# until resumed). Public-mode shards run at 1× and ignore client speed entirely.
SPEED_MULTIPLIERS: Final[tuple[float, ...]] = (0.0, 1.0, 2.0, 4.0)
DEFAULT_SPEED_MULTIPLIER: Final[float] = 1.0


def real_seconds_per_tick(speed_mult: float) -> float:
    """Wall-clock seconds the host should sleep between ticks at ``speed_mult``.

    ``speed_mult <= 0`` is "paused" and returns ``+inf`` (no ticking).
    """
    if speed_mult <= 0.0:
        return float("inf")
    return REAL_SECONDS_PER_TICK_AT_1X / float(speed_mult)


def ticks_per_real_second(speed_mult: float) -> float:
    """Inverse of :func:`real_seconds_per_tick` — useful for UI display."""
    if speed_mult <= 0.0:
        return 0.0
    return TICKS_PER_REAL_SECOND_AT_1X * float(speed_mult)


def legacy_scaled(n: int) -> int:
    """Scale a small integer from the abstract-tick prototype to minute-ticks."""
    return max(1, int(n) * LEGACY_TICK_MULTIPLIER)


def building_operational(row: dict, *, at_tick: int) -> bool:
    """False while ``completes_at_tick`` is in the future (construction in flight)."""
    c = row.get("completes_at_tick")
    if c is None:
        return True
    return at_tick >= int(c)
