"""Building book value — straight-line depreciation and construction activation."""

from __future__ import annotations

from realm.world import World
from realm.world.placed_buildings import sync_plot_buildings_from_placed

_TICKS_PER_GAME_YEAR: int = 525_600


def tick_placed_building_activation(world: World) -> None:
    """Flip ``construction`` → ``active`` when ``built_at_tick`` is reached."""
    changed = False
    for pb in world.placed_buildings.values():
        if str(pb.status) != "construction":
            continue
        if int(world.tick) >= int(pb.built_at_tick):
            pb.status = "active"
            changed = True
    if changed:
        sync_plot_buildings_from_placed(world)


def tick_asset_depreciation(world: World) -> None:
    """Once per game-year: reduce book value by 5% of original construction cost."""
    if int(world.tick) % _TICKS_PER_GAME_YEAR != 0:
        return
    for pb in world.placed_buildings.values():
        if int(pb.original_cost_cents) <= 0:
            continue
        annual_dep = int(pb.original_cost_cents * pb.depreciation_rate_per_year)
        pb.book_value_cents = max(0, int(pb.book_value_cents) - annual_dep)
