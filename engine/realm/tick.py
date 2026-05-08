"""Tick loop entry — advances simulation time (Law 2)."""

from __future__ import annotations

from realm.production import tick_production
from realm.world import World


def advance_tick(world: World) -> None:
    """One simulation step: production advances, then global tick counter increments."""
    tick_production(world)
    world.tick += 1
