"""Best ask / best bid snapshots per tick for solo market chart (Phase 1 observability)."""

from __future__ import annotations

from realm.core.ids import MaterialId
from realm.world import World

_MAX_POINTS = 500


def record_market_snapshot(world: World) -> None:
    """
    Append per-material best ask (lowest limit sell) and best bid (highest limit buy).

    Call once per tick after tick increments.
    """
    from realm.economy.market_signals import ask_depth_units, bid_depth_units

    best_ask: dict[str, int] = {}
    ask_depth: dict[str, int] = {}
    for mat_key, lst in world.market_asks_by_material.items():
        if not lst:
            continue
        best_ask[mat_key] = min(o.price_per_unit_cents for o in lst)
        ask_depth[mat_key] = ask_depth_units(world, MaterialId(mat_key))
    best_bid: dict[str, int] = {}
    bid_depth: dict[str, int] = {}
    for mat_key, lst in world.market_bids_by_material.items():
        if not lst:
            continue
        best_bid[mat_key] = max(b.max_price_per_unit_cents for b in lst)
        bid_depth[mat_key] = bid_depth_units(world, MaterialId(mat_key))
    world.market_history.append(
        {
            "tick": world.tick,
            "best_asks_cents": best_ask,
            "best_bids_cents": best_bid,
            "ask_depth_units": ask_depth,
            "bid_depth_units": bid_depth,
        }
    )
    if len(world.market_history) > _MAX_POINTS:
        world.market_history = world.market_history[-_MAX_POINTS:]
