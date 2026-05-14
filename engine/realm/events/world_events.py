"""World events — exogenous shocks, scripted incidents (Phase 8 stub).

This module defines the dataclass and registry shape that Phase 8 will use to
inject world events (storms, epidemics, tariff shifts, war scares, etc.) into
the simulation. It is intentionally minimal: just the types and an empty
active-events list attached to the world.

Phase 8 will add:
  * Event triggers (probability rolls per tick, conditional triggers from
    world state).
  * Effect appliers (tick handlers per event kind).
  * Resolution (events that expire, get resolved by player action, or
    cascade into other events).

Until then, no production code path emits or resolves world events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from realm.world import World


@dataclass(slots=True)
class WorldEvent:
    """A single active world event.

    ``kind`` is a short stable identifier (e.g. ``"storm"``, ``"plague"``).
    ``payload`` is event-kind-specific structured data.
    ``started_at_tick`` and ``expires_at_tick`` define the active window;
    ``None`` for ``expires_at_tick`` means open-ended (must be resolved by
    explicit action).
    """

    id: str
    kind: str
    started_at_tick: int
    expires_at_tick: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def active_events(world: World) -> list[WorldEvent]:
    """Return the currently-active world events.

    Stub: reads ``world.scenario_state["world_events"]`` if present, else [].
    """
    raw = world.scenario_state.get("world_events") if hasattr(world, "scenario_state") else None
    if not raw:
        return []
    return [WorldEvent(**row) for row in raw]
