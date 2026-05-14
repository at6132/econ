"""World events, observability feed, alerts, seasonal modifiers.

Public surface (Phase 7+):
  * ``log_event``                — append a row to ``world.event_log``
  * ``WorldEvent`` / ``active_events`` — Phase 8 stub for exogenous shocks
  * ``Season`` / ``current_season`` / ``yield_modifier`` / ``movement_cost_modifier``
                                  — Phase 8 stub for season-of-year modifiers
"""

from realm.events.event_log import log_event  # noqa: F401
from realm.events.seasons import (  # noqa: F401
    DAYS_PER_SEASON,
    DAYS_PER_YEAR,
    Season,
    TICKS_PER_YEAR,
    current_season,
    movement_cost_modifier,
    yield_modifier,
)
from realm.events.world_events import WorldEvent, active_events  # noqa: F401
