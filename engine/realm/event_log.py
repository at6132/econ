"""Append-only event feed for solo UI (Phase 1 — not a primitive, observability only)."""

from __future__ import annotations

import copy
from typing import Any

from realm.world import World

_MAX_EVENTS = 1200
# ``world_feed`` lines are mirrored here so a long day of headlines survives ``event_log`` trimming.
_MAX_WORLD_FEED_EVENTS = 4500


def log_event(world: World, kind: str, message: str, **fields: Any) -> None:
    """Record one line at current world.tick; trim oldest when over cap."""
    row: dict[str, Any] = {"tick": world.tick, "kind": kind, "message": message}
    for k in sorted(fields):
        row[k] = fields[k]
    world.event_log.append(row)
    if len(world.event_log) > _MAX_EVENTS:
        world.event_log = world.event_log[-_MAX_EVENTS:]
    if kind == "world_feed":
        world.world_feed_log.append(copy.deepcopy(row))
        if len(world.world_feed_log) > _MAX_WORLD_FEED_EVENTS:
            world.world_feed_log = world.world_feed_log[-_MAX_WORLD_FEED_EVENTS:]
