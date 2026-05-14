"""Seasons — calendar-driven modifiers (Phase 8 stub).

Phase 8 will use this module to apply season-of-year modifiers to:
  * Crop yields (winter -> 0% farm output, spring -> +10%, etc.).
  * Movement costs (winter -> +20% transit time on roads).
  * Heating energy demand (winter -> baseline coal/oil draw per dwelling).
  * Sickness probability, etc.

Until then, ``current_season`` always returns ``Season.SPRING`` and the
modifier helpers always return 1.0 (no effect).
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from realm.core.time_scale import TICKS_PER_GAME_DAY

if TYPE_CHECKING:  # pragma: no cover
    from realm.world import World


DAYS_PER_SEASON = 90  # 90-day quarters
DAYS_PER_YEAR = DAYS_PER_SEASON * 4
TICKS_PER_YEAR = TICKS_PER_GAME_DAY * DAYS_PER_YEAR


class Season(str, Enum):
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"


def current_season(world: World) -> Season:
    """Return the current season based on ``world.tick`` modulo a game-year.

    Stub: always returns ``Season.SPRING`` until Phase 8 enables the calendar.
    Real implementation will be:

        day_of_year = (world.tick // TICKS_PER_GAME_DAY) % DAYS_PER_YEAR
        return Season(_SEASON_BY_DAY_BUCKET[day_of_year // DAYS_PER_SEASON])
    """
    return Season.SPRING


def yield_modifier(world: World, kind: str) -> float:  # noqa: ARG001
    """Return a multiplicative modifier on production output for ``kind``.

    Stub: always 1.0. Phase 8 will return e.g. 0.0 for winter farm yield.
    """
    return 1.0


def movement_cost_modifier(world: World) -> float:  # noqa: ARG001
    """Return a multiplicative modifier on transit ticks. Stub: always 1.0."""
    return 1.0
