"""Append-only event feed for solo UI (Phase 1 — not a primitive, observability only)."""

from __future__ import annotations

from typing import Any

from realm.world import World

_MAX_EVENTS = 1200


def log_event(world: World, kind: str, message: str, **fields: Any) -> None:
    """Record one line at current world.tick; trim oldest when over cap."""
    row: dict[str, Any] = {"tick": world.tick, "kind": kind, "message": message}
    for k in sorted(fields):
        row[k] = fields[k]
    world.event_log.append(row)
    if len(world.event_log) > _MAX_EVENTS:
        world.event_log = world.event_log[-_MAX_EVENTS:]
