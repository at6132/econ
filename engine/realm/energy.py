"""Regional energy grid (Sprint 3 — Phase A).

A ``power_shed`` building covers every plot within Manhattan distance
``POWER_COVERAGE_RADIUS = 12`` of it. Any production recipe whose inputs
include ``electricity`` may run on a plot that is *either*:

1. Within coverage of at least one **active** ``power_shed`` (built and
   running for ≥ ``POWER_BUILDING_WARMUP_TICKS``), regardless of owner, **or**
2. Holds ``electricity`` in the plot's own staged inventory (shipped in).

When path (1) applies the electricity input requirement is *waived* — the
grid covers it. This is what makes near-grid land valuable: the ongoing
electricity cost disappears.

State is cached in ``world.scenario_state["energy_grid"]`` and recomputed
event-driven: a fingerprint over the (instance_id, completes_at_tick,
efficiency_pct, x, y) of every grid source is compared each lookup, and the
expensive O(n×m) recompute only fires when that fingerprint changes (i.e.
a power_shed was built, destroyed, mothballed, or moved). A periodic safety
recompute (every ``POWER_GRID_RECOMPUTE_INTERVAL_TICKS`` ticks) catches any
edge case that bypassed invalidation. — Sprint 6 — Phase D.5.
"""

from __future__ import annotations

from typing import Any, Final

from realm.ids import PartyId, PlotId
from realm.world import World


__all__ = [
    "POWER_COVERAGE_RADIUS",
    "POWER_GRID_RECOMPUTE_INTERVAL_TICKS",
    "POWER_BUILDING_WARMUP_TICKS",
    "POWER_SOURCE_BUILDING_IDS",
    "ensure_powered_plots_fresh",
    "recompute_powered_plots",
    "is_plot_powered",
    "power_sources_for_plot",
    "nearest_power_source",
    "invalidate_powered_plots_cache",
]


POWER_COVERAGE_RADIUS: Final[int] = 12
# Sprint 6 — Phase D.5: the safety cadence is loose because the
# fingerprint-driven invalidation in ``ensure_powered_plots_fresh`` already
# recomputes the instant a power source changes.
POWER_GRID_RECOMPUTE_INTERVAL_TICKS: Final[int] = 1_440  # 1 game-day
POWER_BUILDING_WARMUP_TICKS: Final[int] = 60  # 1 game-hour

# Building ids that count as a grid power source.
POWER_SOURCE_BUILDING_IDS: Final[set[str]] = {"power_shed", "tidal_mill"}


# ───────────────────────── state ─────────────────────────


def _power_state(world: World) -> dict[str, Any]:
    """Get-or-create the cached grid state in ``scenario_state``."""
    return world.scenario_state.setdefault(
        "energy_grid",
        {
            "powered_plots": [],        # list[str] for JSON-friendly snapshotting
            "last_recompute_tick": -10**9,
            # Sprint 6 — Phase D.5: fingerprint of grid sources at last recompute.
            "sources_fingerprint": "",
        },
    )


def _grid_sources_fingerprint(world: World) -> str:
    """Stable signature of all active power sources.

    Changes iff a power source is added, removed, mothballed, or its warm-up
    horizon passes — i.e. exactly when the powered-plot coverage might change.
    """
    parts: list[str] = []
    for row in world.plot_buildings:
        bid = str(row.get("building_id") or "")
        if bid not in POWER_SOURCE_BUILDING_IDS:
            continue
        iid = str(row.get("instance_id") or "")
        completes = int(row.get("completes_at_tick", 0))
        plot_id = str(row.get("plot_id") or "")
        eff = 100
        if iid:
            maint = world.building_maintenance.get(iid) or {}
            eff = int(maint.get("efficiency_pct", 100))
        # Mothballed sources (eff=0) drop out — track separately so transitions
        # from 0→positive (and vice versa) flip the fingerprint.
        parts.append(f"{iid}:{bid}:{plot_id}:{completes}:{eff}")
    # World tick is included only when sources still in warm-up exist, so that
    # the cadence rolls forward as warm-up completes.
    warm_threshold = int(world.tick) - POWER_BUILDING_WARMUP_TICKS
    has_warming = any(
        int(row.get("completes_at_tick", 0)) > warm_threshold
        for row in world.plot_buildings
        if str(row.get("building_id") or "") in POWER_SOURCE_BUILDING_IDS
    )
    parts.append("warmup_pending" if has_warming else "all_warm")
    parts.sort()
    return "|".join(parts)


def invalidate_powered_plots_cache(world: World) -> None:
    """Force the next ``ensure_powered_plots_fresh`` call to recompute.

    Call this from any code path that constructs, destroys, or mothballs a
    power source if you want the change visible *before* the next safety
    cadence tick.
    """
    state = _power_state(world)
    state["sources_fingerprint"] = "__invalidated__"


def _active_power_sources(world: World) -> list[tuple[int, int, PartyId, str, str]]:
    """``(x, y, operator, building_id, instance_id)`` for every running grid source."""
    sources: list[tuple[int, int, PartyId, str, str]] = []
    warm_threshold = int(world.tick) - POWER_BUILDING_WARMUP_TICKS
    for row in world.plot_buildings:
        bid = str(row.get("building_id") or "")
        if bid not in POWER_SOURCE_BUILDING_IDS:
            continue
        completes = int(row.get("completes_at_tick", 0))
        if completes > warm_threshold:
            continue
        plot_id = PlotId(str(row.get("plot_id") or ""))
        plot = world.plots.get(plot_id)
        if plot is None:
            continue
        # Skip mothballed instances (efficiency 0 = building stopped).
        iid = str(row.get("instance_id") or "")
        if iid:
            maint = world.building_maintenance.get(iid) or {}
            if int(maint.get("efficiency_pct", 100)) <= 0:
                continue
        sources.append(
            (int(plot.x), int(plot.y), PartyId(str(row.get("party") or "")), bid, iid)
        )
    return sources


def recompute_powered_plots(world: World) -> set[str]:
    """Recompute the powered-plots cache from current building state and store it."""
    state = _power_state(world)
    sources = _active_power_sources(world)
    powered: set[str] = set()
    if sources:
        r = POWER_COVERAGE_RADIUS
        for plot in world.plots.values():
            px, py = int(plot.x), int(plot.y)
            for sx, sy, _, _, _ in sources:
                if abs(sx - px) + abs(sy - py) <= r:
                    powered.add(str(plot.plot_id))
                    break
    state["powered_plots"] = sorted(powered)
    state["last_recompute_tick"] = int(world.tick)
    state["sources_fingerprint"] = _grid_sources_fingerprint(world)
    return powered


def ensure_powered_plots_fresh(world: World) -> set[str]:
    """Sprint 6 — Phase D.5: event-driven recompute with a safety cadence.

    Recompute if (a) the cache was explicitly invalidated, (b) the grid-source
    fingerprint changed, or (c) the cache is older than the (loose) safety
    cadence. In steady state (no building changes), this is now O(power_sources)
    per call instead of O(plots × power_sources).
    """
    state = _power_state(world)
    last = int(state.get("last_recompute_tick", -10**9))
    cached_fp = str(state.get("sources_fingerprint") or "")
    if cached_fp == "__invalidated__":
        return recompute_powered_plots(world)
    if int(world.tick) - last >= POWER_GRID_RECOMPUTE_INTERVAL_TICKS:
        return recompute_powered_plots(world)
    fp = _grid_sources_fingerprint(world)
    if fp != cached_fp:
        return recompute_powered_plots(world)
    return set(state.get("powered_plots") or [])


def is_plot_powered(world: World, plot_id: PlotId) -> bool:
    """Quick lookup: is ``plot_id`` covered by the energy grid?"""
    powered = ensure_powered_plots_fresh(world)
    return str(plot_id) in powered


def power_sources_for_plot(world: World, plot_id: PlotId) -> list[dict[str, Any]]:
    """Every active grid source whose coverage circle contains ``plot_id``.

    Returns a deterministic list sorted by distance, then operator id.
    """
    plot = world.plots.get(plot_id)
    if plot is None:
        return []
    out: list[dict[str, Any]] = []
    r = POWER_COVERAGE_RADIUS
    for sx, sy, operator, bid, iid in _active_power_sources(world):
        d = abs(sx - int(plot.x)) + abs(sy - int(plot.y))
        if d <= r:
            out.append(
                {
                    "operator": str(operator),
                    "building_id": bid,
                    "instance_id": iid,
                    "distance_tiles": int(d),
                    "x": sx,
                    "y": sy,
                }
            )
    out.sort(key=lambda d: (int(d["distance_tiles"]), str(d["operator"])))
    return out


def nearest_power_source(world: World, plot_id: PlotId) -> dict[str, Any] | None:
    """Closest grid source anywhere (None if no power sources exist)."""
    plot = world.plots.get(plot_id)
    if plot is None:
        return None
    best: tuple[int, dict[str, Any]] | None = None
    for sx, sy, operator, bid, iid in _active_power_sources(world):
        d = abs(sx - int(plot.x)) + abs(sy - int(plot.y))
        entry = {
            "operator": str(operator),
            "building_id": bid,
            "instance_id": iid,
            "distance_tiles": int(d),
            "x": sx,
            "y": sy,
        }
        if best is None or d < best[0] or (d == best[0] and str(operator) < str(best[1]["operator"])):
            best = (d, entry)
    return best[1] if best else None
