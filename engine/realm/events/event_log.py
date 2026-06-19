"""Append-only event feed for solo UI (Phase 1 — not a primitive, observability only)."""

from __future__ import annotations

import copy
from typing import Any

from realm.world import World

# One Genesis game-day can emit ~1k+ mixed events; keep a longer tail so early
# bootstrap rows (e.g. consolidator seed) remain visible alongside day-1 trades.
_MAX_EVENTS = 10_000
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
    if kind in ("market_match", "market_buy", "market_sell"):
        from realm.economy.trade_volume_index import note_trade_event

        note_trade_event(world, row)
    if kind == "world_feed":
        world.world_feed_log.append(copy.deepcopy(row))
        if len(world.world_feed_log) > _MAX_WORLD_FEED_EVENTS:
            world.world_feed_log = world.world_feed_log[-_MAX_WORLD_FEED_EVENTS:]
