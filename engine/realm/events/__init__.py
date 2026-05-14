"""World events, observability feed, alerts, seasonal modifiers.

Public surface (Phase 8 / Sub-phase 8A):
  * ``log_event``                    — append a row to ``world.event_log``
  * ``WorldEvent`` / ``active_events`` — Phase 8B+ stub for exogenous shocks
  * Seasonal calendar:
    * ``Season``                       — enum: spring, summer, autumn, winter
    * ``current_season``               — which season ``world.tick`` falls in
    * ``current_game_day_of_year``     — 1..365
    * ``current_game_year``            — 0, 1, 2, ...
    * ``yield_modifier``               — output multiplier for production
    * ``recipe_blocked_by_season``     — start-time gate (e.g. winter grain)
    * ``fuel_decay_per_day_for_season`` — laborer fuel rate by season
    * ``tick_seasons``                 — emit world-feed transitions
    * ``TICKS_PER_GAME_YEAR`` / ``DAYS_PER_YEAR``
"""

from realm.events.event_log import log_event  # noqa: F401
from realm.events.seasons import (  # noqa: F401
    DAYS_PER_YEAR,
    Season,
    TICKS_PER_GAME_YEAR,
    current_game_day_of_year,
    current_game_year,
    current_season,
    fuel_decay_per_day_for_season,
    recipe_blocked_by_season,
    tick_seasons,
    yield_modifier,
)
from realm.events.world_events import WorldEvent, active_events  # noqa: F401
