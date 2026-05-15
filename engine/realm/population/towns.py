"""Phase 7C — towns: emergent residential clusters.

A *town* is not a placed object: it is what we call any cluster of three
or more residential buildings within 5 tiles of one another. When an
entrepreneur builds a residence, ``detect_towns`` recomputes the cluster
map and (if a cluster now has ≥3 residences) assigns it a town id and a
procedural name. Stores in 7D anchor to a town; laborer spending uses
the town as the catchment.

This module is intentionally idempotent: ``detect_towns`` reads the
current ``world.plot_buildings`` list (active residence buildings) and
produces the canonical ``world.towns`` mapping. Existing town ids are
preserved when the underlying residential cluster is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from realm.events.event_log import log_event
from realm.core.ids import PlotId
from realm.world import World


__all__ = [
    "Town",
    "TOWN_PROXIMITY_TILES",
    "TOWN_MIN_RESIDENCES",
    "SETTLEMENT_PARTY_ID",
    "detect_towns",
    "town_for_plot",
    "town_for_laborer",
    "laborers_for_town",
    "assign_laborer_residence",
    "residence_capacity",
    "residence_occupancy",
    "seed_genesis_starting_towns",
    "starting_residence_plot_count_for_island",
    "on_residence_built",
]


TOWN_PROXIMITY_TILES: Final[int] = 5
"""Two residences belong to the same cluster when their Chebyshev distance
is ≤ this value. 'Within 5 tiles of each other' in the Phase 7 spec."""

TOWN_MIN_RESIDENCES: Final[int] = 3
"""A cluster needs at least this many residences to be recognised as a
town. Smaller clusters are 'farmsteads' — visible on the map but not
yet town-eligible for stores/laborer purchases."""

RESIDENCE_BUILDING_ID: Final[str] = "residence"

SETTLEMENT_PARTY_ID: Final[str] = "genesis_settlement"
"""Owner of the bootstrap residences. Not an entrepreneur — it's a
synthetic placeholder so the four starting towns exist on day 1, before
any player has built anything. Players + entrepreneur NPCs build their
own residences on top of this baseline."""

STARTING_RESIDENCES_PER_ISLAND: Final[int] = 22
"""Legacy default when island laborer count is unknown. Prefer
:func:`starting_residence_plot_count_for_island`."""


def starting_residence_plot_count_for_island(world: World, island_id: int) -> int:
    """Residence buildings needed to seat the density-target laborers on this landmass."""
    from realm.population.landmass_density import laborer_target_count_for_landmass
    from realm.production.buildings import BUILDINGS

    cap = int(BUILDINGS[RESIDENCE_BUILDING_ID].get("capacity", 8))
    n_lab = laborer_target_count_for_landmass(world, int(island_id))
    need = (n_lab + cap - 1) // cap
    return max(TOWN_MIN_RESIDENCES, need)


# ───────────────────────── dataclass ─────────────────────────


@dataclass
class Town:
    """A named residential cluster (≥3 residences within 5 tiles)."""

    town_id: str
    name: str
    island_id: int
    center_plot: PlotId
    residential_plots: list[PlotId] = field(default_factory=list)
    laborer_count: int = 0
    store_plots: list[PlotId] = field(default_factory=list)
    """Phase 7D will populate these as stores are built."""


# ───────────────────────── name generation ─────────────────────────


_NAME_ROOTS: Final[tuple[str, ...]] = (
    "Ash", "Ember", "Hav", "Stone", "Cold", "Bryn", "Mara", "Salt",
    "Pine", "Black", "North", "South", "Far", "Twin", "Iron", "Frost",
    "Birch", "River", "Marsh", "Cliff", "Oak", "Reed", "Snow", "Linden",
)
_NAME_SUFFIXES: Final[tuple[str, ...]] = (
    "ford", "haven", "port", "stead", "field", "wick", "burn", "ridge",
    "vale", "hollow", "bridge", "rest", "mill", "moor", "bay", "brook",
)
_LANDING_FORMS: Final[tuple[str, ...]] = (
    "Kessler's Landing", "Mara's Crossing", "Port Sigrid", "Halberg Reach",
    "Vegg's Anchor", "Lindqvist Pier", "Stenholm Strand", "Roald's Cove",
)


def _generate_town_name(seed: int, town_seq: int) -> str:
    """Deterministic name from (seed, town_seq).

    Mixes the cheap "root+suffix" generator with a small pool of named
    landings so the four bootstrap towns get distinctive identities.
    """
    import random

    # Compose a single int seed so Python's RNG doesn't complain about
    # tuple-based seeding (deprecated since 3.9).
    composite = (int(seed) * 0x100000001B3) ^ (int(town_seq) * 0xA1F)
    rng = random.Random(composite)
    # Roughly 1 in 4 towns gets a "<surname>'s Landing"-style name.
    if rng.random() < 0.25:
        return rng.choice(_LANDING_FORMS)
    return rng.choice(_NAME_ROOTS) + rng.choice(_NAME_SUFFIXES)


# ───────────────────────── geometry / clustering ─────────────────────────


def _active_residences(world: World) -> list[tuple[str, int, int, str]]:
    """Return (plot_id_str, x, y, instance_id) for each completed residence."""
    now = int(world.tick)
    out: list[tuple[str, int, int, str]] = []
    for b in world.plot_buildings:
        if str(b.get("building_id")) != RESIDENCE_BUILDING_ID:
            continue
        completes_at = int(b.get("completes_at_tick", 0))
        if completes_at > now:
            # Still under construction; not yet a town node.
            continue
        plot_id = str(b.get("plot_id", ""))
        plot = world.plots.get(PlotId(plot_id))
        if plot is None:
            continue
        out.append((plot_id, int(plot.x), int(plot.y), str(b.get("instance_id", ""))))
    return out


def _chebyshev(ax: int, ay: int, bx: int, by: int) -> int:
    return max(abs(ax - bx), abs(ay - by))


def _cluster_residences(
    residences: list[tuple[str, int, int, str]],
) -> list[list[tuple[str, int, int, str]]]:
    """Group residences by ``TOWN_PROXIMITY_TILES`` Chebyshev neighbourhood.

    Simple union-find over the proximity graph. O(N²) in the number of
    residences — fine at our scale (towns won't exceed a few hundred
    nodes for the foreseeable future).
    """
    n = len(residences)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        _, xi, yi, _ = residences[i]
        for j in range(i + 1, n):
            _, xj, yj, _ = residences[j]
            if _chebyshev(xi, yi, xj, yj) <= TOWN_PROXIMITY_TILES:
                union(i, j)

    buckets: dict[int, list[tuple[str, int, int, str]]] = {}
    for i, r in enumerate(residences):
        root = find(i)
        buckets.setdefault(root, []).append(r)
    return [
        sorted(group, key=lambda r: (r[2], r[1], r[0]))  # (y, x, plot_id)
        for group in buckets.values()
    ]


# ───────────────────────── public detect ─────────────────────────


def detect_towns(world: World) -> dict[str, Town]:
    """Rebuild ``world.towns`` from the current residence inventory.

    - Clusters with < TOWN_MIN_RESIDENCES residences are dropped from the
      mapping (they may grow into towns later).
    - Town ids are stable across calls when the underlying clusters do
      not change: the canonical id is built from the seed-deterministic
      sort order of the cluster's first plot.
    - Names are generated deterministically from (world.seed, town_seq)
      so repeated calls don't rename existing towns.

    Returns the freshly built mapping (also written to ``world.towns``).
    """
    residences = _active_residences(world)
    clusters = _cluster_residences(residences)
    # Stable order: by (top-left y, top-left x).
    clusters.sort(key=lambda c: (c[0][2], c[0][1]))

    plot_islands = world.scenario_state.get("plot_islands") or {}
    prev_towns = dict(world.towns)
    new_towns: dict[str, Town] = {}
    next_seq = int(world.scenario_state.setdefault("next_town_seq", 1))

    for cluster in clusters:
        if len(cluster) < TOWN_MIN_RESIDENCES:
            continue
        sorted_plots = [PlotId(pid_s) for pid_s, _, _, _ in cluster]
        # Stable id derived from the cluster's first plot id (sorted).
        canonical_first = sorted(str(pid) for pid in sorted_plots)[0]
        # If we've already named a town that contains this anchor plot, reuse.
        reused: Town | None = None
        for prev in prev_towns.values():
            if canonical_first in {str(p) for p in prev.residential_plots}:
                reused = prev
                break
        if reused is not None:
            tid = reused.town_id
            name = reused.name
        else:
            tid = f"town_{next_seq:04d}"
            next_seq += 1
            name = _generate_town_name(int(world.seed), int(tid.split("_")[1]))
        island_id = 0
        for pid in sorted_plots:
            isl = plot_islands.get(str(pid))
            if isl is not None:
                island_id = int(isl)
                break
        center_pid = sorted_plots[len(sorted_plots) // 2]
        new_towns[tid] = Town(
            town_id=tid,
            name=name,
            island_id=island_id,
            center_plot=center_pid,
            residential_plots=sorted_plots,
            laborer_count=0,
            store_plots=[],
        )

    # Carry forward any store_plots and laborer counts the caller had
    # already assigned to a still-existing town.
    for tid, t in new_towns.items():
        prev = prev_towns.get(tid)
        if prev is not None:
            t.store_plots = list(prev.store_plots)
            t.laborer_count = int(prev.laborer_count)

    world.towns = new_towns
    world.scenario_state["next_town_seq"] = next_seq
    return new_towns


# ───────────────────────── helpers ─────────────────────────


def town_for_plot(world: World, plot_id: PlotId) -> Town | None:
    pid_s = str(plot_id)
    for t in world.towns.values():
        if pid_s in (str(p) for p in t.residential_plots):
            return t
        if pid_s in (str(p) for p in t.store_plots):
            return t
    return None


def town_for_laborer(world: World, laborer_id: str) -> Town | None:
    lab = world.laborers.get(laborer_id)
    if lab is None:
        return None
    if lab.home_town:
        return world.towns.get(lab.home_town)
    return town_for_plot(world, lab.home_plot_id)


def residence_capacity(world: World, plot_id: PlotId) -> int:
    """Total capacity of all completed residences on this plot (usually one)."""
    from realm.production.buildings import BUILDINGS

    cap = 0
    now = int(world.tick)
    for b in world.plot_buildings:
        if str(b.get("plot_id")) != str(plot_id):
            continue
        if str(b.get("building_id")) != RESIDENCE_BUILDING_ID:
            continue
        if int(b.get("completes_at_tick", 0)) > now:
            continue
        spec = BUILDINGS.get(RESIDENCE_BUILDING_ID, {})
        cap += int(spec.get("capacity", 0))
    return cap


def residence_occupancy(world: World, plot_id: PlotId) -> int:
    """Current laborer count whose ``home_plot_id`` is this residence."""
    pid_s = str(plot_id)
    return sum(1 for lab in world.laborers.values() if str(lab.home_plot_id) == pid_s)


def laborers_for_town(world: World, town_id: str) -> list[str]:
    """Laborer ids whose ``home_town`` matches this town."""
    return [lid for lid, lab in world.laborers.items() if lab.home_town == town_id]


# ───────────────────────── housing assignment ─────────────────────────


def assign_laborer_residence(
    world: World, laborer_id: str, plot_id: PlotId
) -> dict:
    """Move a laborer's home to ``plot_id``. Enforces residence capacity.

    Effects:
    - Sets ``laborer.home_plot_id``.
    - Sets ``laborer.needs["shelter"]`` to 1.0 (just moved in — sheltered).
    - Sets ``laborer.home_town`` if the new plot belongs to a town.

    Returns ``{"ok": True}`` on success, ``{"ok": False, "reason": ...}``
    when the residence is missing/under construction/full.
    """
    lab = world.laborers.get(laborer_id)
    if lab is None:
        return {"ok": False, "reason": "unknown laborer"}
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    from realm.production.recipe_sites import plot_allows_structure

    if not plot_allows_structure(plot):
        return {"ok": False, "reason": "cannot house laborers on water"}
    cap = residence_capacity(world, plot_id)
    if cap <= 0:
        return {"ok": False, "reason": "no completed residence on plot"}
    occupancy = residence_occupancy(world, plot_id)
    if str(lab.home_plot_id) != str(plot_id) and occupancy >= cap:
        return {"ok": False, "reason": "residence at capacity"}
    lab.home_plot_id = plot_id
    lab.needs["shelter"] = 1.0
    town = town_for_plot(world, plot_id)
    lab.home_town = town.town_id if town is not None else None
    return {"ok": True, "town_id": lab.home_town}


# ───────────────────────── build hook ─────────────────────────


def on_residence_built(world: World, plot_id: PlotId) -> None:
    """Refresh towns after a residence is built. Wired from ``build_on_plot``.

    Idempotent; safe to call from snapshot reload, settler agents, or
    direct construction. Logs a world_feed entry when the build creates
    a new town (i.e. crosses the 3-residence threshold).
    """
    prev_ids = set(world.towns.keys())
    detect_towns(world)
    new_ids = set(world.towns.keys()) - prev_ids
    for tid in new_ids:
        t = world.towns[tid]
        log_event(
            world,
            "world_feed",
            f"A new town has formed on island {t.island_id}: {t.name} ({len(t.residential_plots)} residences).",
            town_id=tid,
            island_id=t.island_id,
        )


# ───────────────────────── bootstrap ─────────────────────────


def _ensure_settlement_party(world: World) -> None:
    """Idempotent: create the synthetic ``genesis_settlement`` party once."""
    from realm.core.ids import PartyId
    from realm.core.ledger import party_cash_account

    pid = PartyId(SETTLEMENT_PARTY_ID)
    if pid in world.parties:
        return
    world.parties.add(pid)
    world.reputation[str(pid)] = {"honored": 0, "breached": 0}
    world.party_display_names[str(pid)] = "Settlement Authority"
    world.ledger.ensure_account(party_cash_account(pid))


def _pick_starting_residence_plots(world: World, island_id: int) -> list[PlotId]:
    """Pick enough land plots on this island for bootstrap residences.

    Count scales with ``DEFAULT_ISLAND_LABORER_COUNTS`` (8 occupants per
    residence). Prefer plots near the island's low (x+y) corner; fall back
    to the first N candidates if the proximity window is too small.
    """
    target_n = starting_residence_plot_count_for_island(world, island_id)
    plot_islands = world.scenario_state.get("plot_islands") or {}
    candidates: list[tuple[int, int, str]] = []
    for pid_s, isl in plot_islands.items():
        if int(isl) != int(island_id):
            continue
        plot = world.plots.get(PlotId(pid_s))
        if plot is None or plot.owner is not None:
            continue
        from realm.production.recipe_sites import plot_allows_structure

        if not plot_allows_structure(plot):
            continue
        candidates.append((int(plot.x), int(plot.y), pid_s))
    if not candidates:
        return []
    candidates.sort(key=lambda t: (t[0] + t[1], t[0], t[1]))
    anchor = candidates[0]
    cluster: list[str] = [anchor[2]]
    for x, y, pid_s in candidates[1:]:
        if _chebyshev(x, y, anchor[0], anchor[1]) <= TOWN_PROXIMITY_TILES:
            cluster.append(pid_s)
        if len(cluster) >= target_n:
            break
    if len(cluster) < target_n:
        cluster = [c[2] for c in candidates[:target_n]]
    return [PlotId(p) for p in cluster[:target_n]]


def _seed_residence_on_plot(world: World, owner_party_id: str, plot_id: PlotId) -> str:
    """Place a completed residence on ``plot_id``, owned by ``owner_party_id``.

    Direct insert (bypasses ``build_on_plot``) because these are
    pre-existing settlements at world bootstrap, not in-game constructions.
    No cash leaves the ledger; the building exists at tick 0.
    """
    from realm.production.buildings import BUILDINGS
    from realm.production.decay import BUILDING_CONDITION_FULL_BPS

    from realm.production.recipe_sites import plot_allows_structure

    plot = world.plots.get(plot_id)
    if plot is None or not plot_allows_structure(plot):
        raise ValueError(f"bootstrap residence requires dry land, got {plot_id}")
    spec = BUILDINGS[RESIDENCE_BUILDING_ID]
    world.next_building_instance_seq += 1
    instance_id = f"b{world.next_building_instance_seq:06d}"
    world.plot_buildings.append(
        {
            "instance_id": instance_id,
            "condition_bps": BUILDING_CONDITION_FULL_BPS,
            "plot_id": str(plot_id),
            "party": owner_party_id,
            "building_id": RESIDENCE_BUILDING_ID,
            "label": str(spec["label"]),
            "cost_cents": 0,
            "build_mode": "bootstrap",
            "completes_at_tick": 0,
        }
    )
    return instance_id


def seed_genesis_starting_towns(world: World) -> dict[int, str]:
    """Seed one starting town per island and assign laborers to its residences.

    Returns ``{island_id: town_id}`` for every island that successfully
    seated a town. Idempotent: re-running is a no-op (residences already
    exist; ``detect_towns`` re-finds the same cluster).
    """
    plot_islands = world.scenario_state.get("plot_islands") or {}
    if not plot_islands:
        return {}
    _ensure_settlement_party(world)
    distinct_islands = sorted({int(isl) for isl in plot_islands.values()})
    seeded_towns: dict[int, str] = {}
    for isl in distinct_islands:
        plot_ids = _pick_starting_residence_plots(world, isl)
        if len(plot_ids) < TOWN_MIN_RESIDENCES:
            continue
        from realm.core.ids import PartyId

        for pid in plot_ids:
            plot = world.plots.get(pid)
            if plot is None:
                continue
            plot.owner = PartyId(SETTLEMENT_PARTY_ID)
            _seed_residence_on_plot(world, SETTLEMENT_PARTY_ID, pid)
    # One pass to materialise the freshly-seeded towns.
    detect_towns(world)
    for isl in distinct_islands:
        for t in world.towns.values():
            if t.island_id == isl:
                seeded_towns[isl] = t.town_id
                break
    # Assign laborers on each island to their island's town, distributing
    # them across the residences up to capacity.
    _assign_initial_laborers_to_towns(world, seeded_towns)
    return seeded_towns


def _assign_initial_laborers_to_towns(
    world: World, seeded_towns: dict[int, str]
) -> None:
    """Pin each laborer to a residence on their home island, up to capacity.

    Laborers beyond residential capacity stay floating (no home_town,
    no residence assignment). They feed the demand pressure for new
    residences in 7C+ gameplay.
    """
    by_island: dict[int, list[str]] = {}
    for lid, lab in world.laborers.items():
        by_island.setdefault(int(lab.island_id), []).append(lid)
    for isl, town_id in seeded_towns.items():
        town = world.towns.get(town_id)
        if town is None:
            continue
        residence_slots: list[PlotId] = []
        for pid in town.residential_plots:
            cap = residence_capacity(world, pid)
            residence_slots.extend([pid] * cap)
        laborers = sorted(by_island.get(isl, []))
        for lid, pid in zip(laborers, residence_slots):
            lab = world.laborers.get(lid)
            if lab is None:
                continue
            lab.home_plot_id = pid
            lab.home_town = town_id
            lab.needs["shelter"] = 1.0
        town.laborer_count = min(len(laborers), len(residence_slots))


# ─────────────────── Phase 9G — homeless laborer assignment ───────────────────


_TICKS_PER_GAME_DAY: Final[int] = 1_440


def tick_assign_homeless_laborers(world: World) -> int:
    """Phase 9G — once per game-day, pull homeless laborers into towns
    with spare residence capacity.

    The new ``home_builder`` archetype steadily produces residences, but
    those rooms sat empty without a matching mover. This pass walks every
    town, counts free slots, and assigns the closest homeless laborers on
    the same island until either runs out. Sorting is by laborer_id so
    the choice is deterministic across runs.

    Returns the number of laborers newly housed this game-day.
    """
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return 0
    if not world.towns or not world.laborers:
        return 0
    # Build homeless-by-island index once.
    homeless_by_island: dict[int, list[str]] = {}
    for lid, lab in world.laborers.items():
        if lab.home_town is None:
            homeless_by_island.setdefault(int(lab.island_id), []).append(lid)
    if not homeless_by_island:
        return 0
    housed = 0
    for town in world.towns.values():
        free_slots: list[PlotId] = []
        for pid in town.residential_plots:
            cap = residence_capacity(world, pid)
            occ = sum(
                1
                for lab in world.laborers.values()
                if lab.home_plot_id == pid and lab.home_town is not None
            )
            for _ in range(max(0, cap - occ)):
                free_slots.append(pid)
        if not free_slots:
            continue
        pool = sorted(homeless_by_island.get(int(town.island_id), []))
        for lid, slot_pid in zip(pool, free_slots):
            lab = world.laborers.get(lid)
            if lab is None:
                continue
            lab.home_plot_id = slot_pid
            lab.home_town = town.town_id
            lab.needs["shelter"] = 1.0
            town.laborer_count = int(town.laborer_count) + 1
            housed += 1
            homeless_by_island[int(town.island_id)].remove(lid)
        if housed:
            from realm.events.event_log import log_event

            log_event(
                world,
                "homeless_assigned",
                f"{housed} laborer(s) moved into {town.town_id} on island {town.island_id}",
                town_id=town.town_id,
                island_id=int(town.island_id),
                housed=int(housed),
            )
    return housed
