"""Tick loop entry — advances simulation time (Law 2)."""

from __future__ import annotations

from realm.world import World


def advance_tick(world: World) -> None:
    """Single authoritative tick: time +1; systems hook in here later."""
    world.tick += 1
