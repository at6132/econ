"""World state, geography, time progression.

This package re-exports the canonical public types and functions from
``realm.world.world``, ``realm.world.terrain``, etc. so that ``from
realm.world import World`` (the legacy import path that ~63 files still use)
continues to work.

Submodules:
  * ``realm.world.world``         — World dataclass, plot/building dataclasses,
                                     bootstrap_* functions
  * ``realm.world.subsurface``    — ``SubsurfaceRoll`` + terrain-correlated roll
  * ``realm.world.serialization`` — ``world_public_dict`` / ``world_compact_dict``
                                     / ``world_summary_dict`` (read-only DTOs)
  * ``realm.world.terrain``       — Terrain enum
  * ``realm.world.biome_noise``   — Procedural biome generator
  * ``realm.world.geo``           — Manhattan distance, plot coords
  * ``realm.world.islands``       — Island worldgen helpers
  * ``realm.world.geo_clustering`` — Cluster nearby plots into regions
  * ``realm.world.regions``       — 3x3 region grid for shipping market
  * ``realm.world.tick``          — advance_tick() simulation loop
"""

from realm.world.world import (  # noqa: F401
    ActiveProduction,
    BusinessRecord,
    InTransit,
    Plot,
    RoadSegment,
    SubsurfaceRoll,
    SurveyReport,
    World,
    bootstrap_by_scenario,
    bootstrap_frontier,
    bootstrap_genesis,
    claim_cost_cents_for_plot,
    ensure_party_recipe_book,
    generate_plots,
    population_density_for,
    tier1_recipe_ids,
    world_compact_dict,
    world_public_dict,
    world_summary_dict,
)
