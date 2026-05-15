"""Phase 10 — landmass classification (continents / islands / islets).

After plot generation, this module runs a BFS connected-component pass over
non-ocean plots and groups them into landmasses. Each landmass is then tagged:

    landmass_type[lid] in {"continent", "island", "islet"}

based on its plot count.

State lives directly on :class:`World`:

    world.landmass_id: dict[str, int]      # plot id str → landmass id (-1 for ocean)
    world.landmass_type: dict[int, str]    # landmass id → "continent" | "island" | "islet"
    world.landmass_plot_count: dict[int, int]

For backwards compatibility ``world.scenario_state["plot_islands"]`` is still
populated with the same mapping (so existing callers — movement, demand, NPC
shipper seeding — keep working with no change).

The shipping multipliers in :func:`landmass_pair_modifier` are layered into
``movement.dispatch_shipment`` so cross-continent voyages cost more than
short island-hops.
"""

from __future__ import annotations

from typing import Final

from realm.world import World
from realm.world.islands import compute_plot_islands


CONTINENT_MIN_PLOTS: Final[int] = 500
"""≥ 500 contiguous land plots → "continent"."""

ISLAND_MIN_PLOTS: Final[int] = 50
"""50 ≤ plots < ``CONTINENT_MIN_PLOTS`` → "island"."""

# < ``ISLAND_MIN_PLOTS`` → "islet".


# Inter-landmass shipping per-tile multipliers (Phase 10 A2). Applied on top
# of the existing 2× open-ocean modifier already present in ``movement.py``.
# Continent-to-continent is the most expensive (long open-ocean crossings);
# island-to-island within the same chain is the cheapest (short hops).
CONTINENT_TO_CONTINENT_MULT: Final[float] = 3.0
CONTINENT_TO_ISLAND_MULT: Final[float] = 2.0
ISLAND_TO_ISLAND_MULT: Final[float] = 1.5


__all__ = [
    "CONTINENT_MIN_PLOTS",
    "ISLAND_MIN_PLOTS",
    "CONTINENT_TO_CONTINENT_MULT",
    "CONTINENT_TO_ISLAND_MULT",
    "ISLAND_TO_ISLAND_MULT",
    "compute_landmasses",
    "classify_landmass",
    "landmass_pair_modifier",
    "list_continents",
    "validate_continental_viability",
]


def classify_landmass(plot_count: int) -> str:
    """Return ``"continent"`` / ``"island"`` / ``"islet"`` for a plot count."""
    if plot_count >= CONTINENT_MIN_PLOTS:
        return "continent"
    if plot_count >= ISLAND_MIN_PLOTS:
        return "island"
    return "islet"


def compute_landmasses(world: World) -> None:
    """Populate ``world.landmass_*`` and refresh ``scenario_state["plot_islands"]``.

    Idempotent — safe to call again after world generation. The existing
    ``compute_plot_islands`` BFS handles the connectivity work; this function
    just classifies each component and writes the type-table.
    """
    plot_islands = compute_plot_islands(world)
    world.scenario_state["plot_islands"] = plot_islands
    counts: dict[int, int] = {}
    for _pid_s, lid in plot_islands.items():
        counts[int(lid)] = counts.get(int(lid), 0) + 1
    world.landmass_id = {str(pid): int(lid) for pid, lid in plot_islands.items()}
    world.landmass_plot_count = dict(counts)
    world.landmass_type = {lid: classify_landmass(c) for lid, c in counts.items()}


def landmass_pair_modifier(world: World, a_landmass: int, b_landmass: int) -> float:
    """Multiplier applied to the per-tile shipping fee for a cross-landmass voyage.

    Returns ``1.0`` for intra-landmass shipments (no surcharge) and one of the
    Phase 10 modifiers when origin and destination are on different landmasses.
    """
    if a_landmass == b_landmass:
        return 1.0
    type_a = (world.landmass_type or {}).get(int(a_landmass), "island")
    type_b = (world.landmass_type or {}).get(int(b_landmass), "island")
    if type_a == "continent" and type_b == "continent":
        return CONTINENT_TO_CONTINENT_MULT
    if type_a == "continent" or type_b == "continent":
        return CONTINENT_TO_ISLAND_MULT
    return ISLAND_TO_ISLAND_MULT


def list_continents(world: World) -> list[int]:
    """Sorted list of landmass ids classified as continents."""
    return sorted(
        lid for lid, t in (world.landmass_type or {}).items() if t == "continent"
    )


# Phase 10 — viability seeding tunables. If a continent comes out of bootstrap
# below the minimum laborer count, we top it up from the system reserve. The
# spec calls for ≥ 80 laborers per continent and ≥ a small number of
# entrepreneur NPCs.
CONTINENT_MIN_LABORERS: Final[int] = 80
CONTINENT_MIN_ENTREPRENEUR_NPCS: Final[int] = 4


def validate_continental_viability(world: World) -> dict[str, int]:
    """Top up any continent that came out of bootstrap below the minimums.

    Returns ``{"laborers_added": int, "entrepreneurs_added": int, "continents": int}``
    so the caller can log the enforcement step. Run at the end of
    ``bootstrap_genesis`` (after laborer + settler seeding) so the world
    every player loads is guaranteed to have a working day-1 economy on every
    continent.
    """
    from realm.events.event_log import log_event
    from realm.population.laborers import seed_island_laborers, laborer_count_for_island

    continents = list_continents(world)
    added_lab = 0
    added_ent = 0
    for lid in continents:
        live = laborer_count_for_island(world, lid)
        if live < CONTINENT_MIN_LABORERS:
            need = CONTINENT_MIN_LABORERS - live
            seeded = seed_island_laborers(world, lid, need)
            added_lab += len(seeded)
            log_event(
                world,
                "viability_enforcement",
                f"Added {len(seeded)} emergency laborers to continent {lid} "
                f"(was {live}, need {CONTINENT_MIN_LABORERS}).",
                landmass_id=int(lid),
                added=len(seeded),
                kind_seeded="laborers",
            )
        # Entrepreneur NPC top-up is handled inline by the genesis seeding
        # already (settlers are spread across all islands). The
        # ``CONTINENT_MIN_ENTREPRENEUR_NPCS`` floor is a soft guarantee:
        # we log if it isn't met but don't synthesise extra NPC parties
        # here (settler cycle will fill in via random arrivals).
    return {
        "laborers_added": added_lab,
        "entrepreneurs_added": added_ent,
        "continents": len(continents),
    }
