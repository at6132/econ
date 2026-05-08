"""Best-ask snapshots per tick for solo market chart (Phase 1 observability)."""

from __future__ import annotations

from realm.world import World

_MAX_POINTS = 500


def record_market_snapshot(world: World) -> None:
    """Append lowest limit price per material (if any asks). Call once per tick after tick increments."""
    best: dict[str, int] = {}
    for mat_key, lst in world.market_asks_by_material.items():
        if not lst:
            continue
        best[mat_key] = min(o.price_per_unit_cents for o in lst)
    world.market_history.append({"tick": world.tick, "best_asks_cents": best})
    if len(world.market_history) > _MAX_POINTS:
        world.market_history = world.market_history[-_MAX_POINTS:]
