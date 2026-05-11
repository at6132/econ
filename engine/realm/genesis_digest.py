"""Aggregate Genesis digest lines for the solo UI (``world_feed`` event kind)."""

from __future__ import annotations

from realm.event_log import log_event
from realm.world import World


def tick_genesis_world_feed(world: World) -> None:
    """Append a short digest when due (order-book depth + settler footprint)."""
    if world.scenario_id != "genesis":
        return
    if world.tick < 1 or world.tick % 48 != 0:
        return
    asks = sum(len(v) for v in world.market_asks_by_material.values())
    bids = sum(len(v) for v in world.market_bids_by_material.values())
    max_y = max((p.y for p in world.plots.values()), default=0)
    thr = max_y * 2 // 3 if max_y > 0 else 0
    south = sum(
        1
        for p in world.plots.values()
        if p.owner and str(p.owner).startswith("settler_") and p.y >= thr
    )
    deeds = sum(1 for p in world.plots.values() if p.owner and str(p.owner).startswith("settler_"))
    parts = [
        f"Order book — {asks} asks, {bids} bids.",
        f"Settlers hold {deeds} deeds; {south} are camped deep south (y ≥ {thr}).",
    ]
    log_event(world, "world_feed", " ".join(parts))
