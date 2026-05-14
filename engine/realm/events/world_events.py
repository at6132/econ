"""Phase 8 — Volatility Engine.

World events are exogenous shocks: drought, blight, mine collapse, storm,
seismic, flood. They fire stochastically based on terrain, season, and
maintenance state, then attach themselves to the world for a duration.

The design contract:

* **Deterministic** — all rolls use ``world.rng(world.tick, purpose)``.
  Same seed + same tick → same events.
* **Observable** — every event emits a ``world_feed`` row at start and end;
  some emit a pre-event signal 1–3 game-days before they fire.
* **Local** — events are scoped (island, plot, or set of plots) so
  unaffected regions keep operating.
* **Survivable** — well-maintained operations don't collapse; players who
  watch the feed get advance warning. Nothing one-shots a careful player.

Public surface
--------------
* ``WorldEvent`` dataclass + ``active_events`` accessor.
* Trigger helpers (used by the tick loop and by tests/admin to fire on demand):
  ``trigger_drought``, ``trigger_storm``, ``trigger_mine_collapse``,
  ``trigger_blight``, ``trigger_seismic``, ``trigger_flood``.
* ``tick_world_events(world)`` — main loop entry. Rolls new events, ages
  existing ones, applies per-tick effects, and resolves expired ones.
* ``yield_modifier_for_event(event_kind, severity)`` — composes with the
  seasonal multiplier in ``effective_outputs_for_completion``.
* ``recipe_blocked_by_active_event(world, recipe_id, plot)`` — start-time
  refusal for ``grow_grain`` during drought etc.
* ``active_event_for_island(world, island_id, kinds=…)`` — quick lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable

from realm.core.ids import PlotId
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event
from realm.events.seasons import (
    Season,
    current_game_day_of_year,
    current_season,
)

if TYPE_CHECKING:  # pragma: no cover
    from realm.world.world import World


# ─────────────────────────────────────────────────────────────────────────
# Event dataclass
# ─────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class WorldEvent:
    """A single active world event (drought, storm, mine_collapse, …).

    ``event_type`` is a short stable identifier. ``island_id`` is set for
    island-scoped events (drought, blight, epidemic). ``affected_plots``
    is set for plot-scoped events (mine_collapse, flood, seismic).
    Either one or both may be empty for global events.

    ``severity`` ∈ [0.0, 1.0] scales the impact. ``announced`` toggles when
    the start-of-event world_feed row has been emitted (idempotent re-fire).
    """

    event_id: str
    event_type: str
    started_tick: int
    end_tick: int
    severity: float
    island_id: int | None = None
    affected_plots: list[PlotId] = field(default_factory=list)
    announced: bool = False
    resolved: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


# Back-compat keys used by older ``WorldEvent(**row)`` deserialization.
_LEGACY_ROW_KEYS = {"id": "event_id", "kind": "event_type"}


def _coerce_event_row(row: dict[str, Any]) -> WorldEvent:
    """Build a ``WorldEvent`` from a stored dict, tolerating legacy field names."""
    payload = {k: v for k, v in row.items()}
    for legacy, new in _LEGACY_ROW_KEYS.items():
        if legacy in payload and new not in payload:
            payload[new] = payload.pop(legacy)
    plots = payload.get("affected_plots") or []
    payload["affected_plots"] = [PlotId(str(p)) for p in plots]
    payload.setdefault("severity", 0.5)
    payload.setdefault("started_tick", 0)
    payload.setdefault("end_tick", 0)
    payload.setdefault("event_type", "unknown")
    payload.setdefault("event_id", "evt-?")
    payload.setdefault("payload", {})
    return WorldEvent(
        event_id=str(payload["event_id"]),
        event_type=str(payload["event_type"]),
        started_tick=int(payload["started_tick"]),
        end_tick=int(payload["end_tick"]),
        severity=float(payload["severity"]),
        island_id=(
            int(payload["island_id"])
            if payload.get("island_id") not in (None, "")
            else None
        ),
        affected_plots=list(payload["affected_plots"]),
        announced=bool(payload.get("announced", False)),
        resolved=bool(payload.get("resolved", False)),
        payload=dict(payload["payload"]),
    )


def _events_store(world: "World") -> list[WorldEvent]:
    """In-memory cache attached to the world. Initialised on first read."""
    cache = getattr(world, "_world_events_cache", None)
    if cache is None:
        raw = world.scenario_state.get("world_events") or []
        cache = [_coerce_event_row(r) for r in raw] if isinstance(raw, list) else []
        setattr(world, "_world_events_cache", cache)
    return cache


def _flush_events_store(world: "World") -> None:
    """Persist the cache back to ``world.scenario_state`` for snapshot save."""
    cache = _events_store(world)
    world.scenario_state["world_events"] = [
        {
            "event_id": ev.event_id,
            "event_type": ev.event_type,
            "started_tick": int(ev.started_tick),
            "end_tick": int(ev.end_tick),
            "severity": float(ev.severity),
            "island_id": ev.island_id,
            "affected_plots": [str(p) for p in ev.affected_plots],
            "announced": bool(ev.announced),
            "resolved": bool(ev.resolved),
            "payload": dict(ev.payload),
        }
        for ev in cache
    ]


def active_events(world: "World") -> list[WorldEvent]:
    """Currently active (non-resolved) events on the world."""
    return [ev for ev in _events_store(world) if not ev.resolved]


def all_events(world: "World") -> list[WorldEvent]:
    """All events (active + resolved). For Chronicle / regional risk reports."""
    return list(_events_store(world))


def active_event_for_island(
    world: "World", island_id: int, kinds: Iterable[str] | None = None
) -> WorldEvent | None:
    """First active event matching ``island_id`` and (optional) kind whitelist."""
    kind_set = set(kinds) if kinds else None
    for ev in active_events(world):
        if ev.island_id is None or int(ev.island_id) != int(island_id):
            continue
        if kind_set is not None and ev.event_type not in kind_set:
            continue
        return ev
    return None


def active_event_for_plot(
    world: "World", plot_id: PlotId, kinds: Iterable[str] | None = None
) -> WorldEvent | None:
    """First active event with ``plot_id`` in ``affected_plots`` (and optionally a matching kind)."""
    kind_set = set(kinds) if kinds else None
    pid_s = str(plot_id)
    for ev in active_events(world):
        if kind_set is not None and ev.event_type not in kind_set:
            continue
        if any(str(p) == pid_s for p in ev.affected_plots):
            return ev
    return None


# ─────────────────────────────────────────────────────────────────────────
# Tunables — frequencies and impact magnitudes
# ─────────────────────────────────────────────────────────────────────────


# Drought (per island per game-day during summer/autumn).
DROUGHT_BASE_DAILY_PROB: float = 0.002
DROUGHT_ARID_DAILY_PROB: float = 0.004  # Island D (arid bias)
DROUGHT_MIN_DAYS: int = 7
DROUGHT_MAX_DAYS: int = 20
DROUGHT_MAX_YIELD_REDUCTION: float = 0.40  # at severity 1.0
DROUGHT_PREDISASTER_DAYS: int = 2  # advance warning lead time

# Blight (per island per week during summer).
BLIGHT_WEEKLY_PROB: float = 0.01
BLIGHT_MIN_DAYS: int = 5
BLIGHT_MAX_DAYS: int = 10

# Mine collapse (per strip_mine per game-day; scales with missed_cycles).
MINE_BASE_DAILY_PROB: float = 0.0001
MINE_MISSED_CYCLE_MULT: float = 1.0  # P = base × (missed_cycles + 1)
MINE_COLLAPSE_INJURY_HEALTH: float = 0.30
MINE_RUBBLE_DAYS: int = 2

# Storm (per island per game-day during autumn/winter).
STORM_BASE_DAILY_PROB: float = 0.003
STORM_WINTER_MULT: float = 1.5
STORM_MIN_TRANSIT_DELAY_TICKS: int = TICKS_PER_GAME_DAY
STORM_MAX_TRANSIT_DELAY_TICKS: int = TICKS_PER_GAME_DAY * 7 // 2  # ~3.5 days
STORM_MIN_DAYS: int = 2
STORM_MAX_DAYS: int = 5
STORM_FLOOD_FOLLOWUP_PROB: float = 0.30

# Seismic (per highland plot per week on islands A and D).
SEISMIC_WEEKLY_PROB_PER_PLOT: float = 0.001
SEISMIC_RADIUS_TILES: int = 2
SEISMIC_AFFECTED_EFFICIENCY: int = 60  # forced down to 60% (1 missed cycle)
SEISMIC_GRADE_DECAY: float = 0.95
SEISMIC_HIGH_RISK_ISLANDS: frozenset[int] = frozenset({0, 3})

# Flood (spawned from storms on low-elevation plots adjacent to coast).
FLOOD_MIN_DAYS: int = 3
FLOOD_MAX_DAYS: int = 5
FLOOD_BLOCKED_RECIPES: frozenset[str] = frozenset(
    {"grow_grain", "hand_dig_clay"}
)

# Epidemic (per town per game-month, scaled by town health).
EPIDEMIC_MONTHLY_PROB: float = 0.02
EPIDEMIC_HEALTH_DECAY_MULT: float = 3.0
EPIDEMIC_MIN_DAYS: int = 10
EPIDEMIC_MAX_DAYS: int = 20
EPIDEMIC_SPREAD_PROB: float = 0.20  # per migration carrier
EPIDEMIC_MEDICINE_HEAL_AMOUNT: float = 0.30
TICKS_PER_GAME_MONTH: int = TICKS_PER_GAME_DAY * 30

# Master kill-switch (mostly for tests that need a quiet world).
ENABLED_FLAG_KEY: str = "world_events_enabled"


def events_enabled(world: "World") -> bool:
    """Whether stochastic event rolls fire this tick.

    Default is ``True``. Tests that need to construct a world without any
    background shocks (e.g. clean conservation checks) can set
    ``world.scenario_state["world_events_enabled"] = False``.
    """
    flag = world.scenario_state.get(ENABLED_FLAG_KEY)
    if flag is None:
        return True
    return bool(flag)


# ─────────────────────────────────────────────────────────────────────────
# Event lifecycle helpers
# ─────────────────────────────────────────────────────────────────────────


def _next_event_id(world: "World", prefix: str) -> str:
    seq = int(world.scenario_state.get("next_world_event_seq", 1))
    world.scenario_state["next_world_event_seq"] = seq + 1
    return f"{prefix}-{seq:05d}"


def _create_event(
    world: "World",
    *,
    event_type: str,
    severity: float,
    duration_ticks: int,
    island_id: int | None = None,
    affected_plots: list[PlotId] | None = None,
    payload: dict[str, Any] | None = None,
) -> WorldEvent:
    store = _events_store(world)
    ev = WorldEvent(
        event_id=_next_event_id(world, event_type),
        event_type=event_type,
        started_tick=int(world.tick),
        end_tick=int(world.tick) + max(1, int(duration_ticks)),
        severity=max(0.0, min(1.0, float(severity))),
        island_id=island_id,
        affected_plots=list(affected_plots or []),
        payload=dict(payload or {}),
    )
    store.append(ev)
    _flush_events_store(world)
    return ev


def _announce_start(world: "World", ev: WorldEvent, message: str, **fields: Any) -> None:
    ev.announced = True
    log_event(
        world,
        "world_feed",
        message,
        event_class="world_event_start",
        event_id=ev.event_id,
        event_type=ev.event_type,
        island_id=ev.island_id,
        severity=round(ev.severity, 3),
        **fields,
    )
    _flush_events_store(world)


def _announce_end(world: "World", ev: WorldEvent, message: str, **fields: Any) -> None:
    ev.resolved = True
    log_event(
        world,
        "world_feed",
        message,
        event_class="world_event_end",
        event_id=ev.event_id,
        event_type=ev.event_type,
        island_id=ev.island_id,
        **fields,
    )
    _flush_events_store(world)


# ─────────────────────────────────────────────────────────────────────────
# Effect lookups (called from production / movement / laborers)
# ─────────────────────────────────────────────────────────────────────────


def yield_modifier_for_plot(world: "World", recipe_id: str, plot: Any) -> float:
    """Per-plot multiplicative output modifier from any active event.

    Composes with the seasonal modifier in
    ``production.effective_outputs_for_completion``. Returns 1.0 when no
    event applies.
    """
    if plot is None:
        return 1.0
    isl = _plot_island(world, plot)
    mod = 1.0
    # Drought: reduces all agricultural output on the affected island.
    if recipe_id == "grow_grain":
        drought = active_event_for_island(world, isl, {"drought"}) if isl is not None else None
        if drought is not None:
            mod *= max(0.0, 1.0 - DROUGHT_MAX_YIELD_REDUCTION * drought.severity)
        blight = active_event_for_island(world, isl, {"blight"}) if isl is not None else None
        if blight is not None and str(blight.payload.get("recipe_id")) == recipe_id:
            mod *= 0.0  # blight zeros the affected recipe entirely
    # Flood: blocks listed recipes on flooded plots.
    if recipe_id in FLOOD_BLOCKED_RECIPES:
        flood = active_event_for_plot(world, plot.plot_id, {"flood"})
        if flood is not None:
            mod *= 0.0
    return mod


def recipe_blocked_by_active_event(
    world: "World", recipe_id: str, plot: Any
) -> tuple[bool, str]:
    """Start-time refusal hook used by ``production.start_production``.

    Returns ``(blocked, reason)``. ``blocked=False`` means no active event
    forbids this recipe right now on this plot.
    """
    if plot is None:
        return False, ""
    if yield_modifier_for_plot(world, recipe_id, plot) > 0.0:
        return False, ""
    isl = _plot_island(world, plot)
    if recipe_id == "grow_grain":
        if isl is not None and active_event_for_island(world, isl, {"blight"}):
            return True, f"grain blight active on island {isl} — sowing suspended"
        if isl is not None and active_event_for_island(world, isl, {"drought"}):
            return True, f"severe drought on island {isl} — sowing suspended"
    if recipe_id in FLOOD_BLOCKED_RECIPES:
        if active_event_for_plot(world, plot.plot_id, {"flood"}):
            return True, f"plot {plot.plot_id} is flooded"
    return True, f"recipe {recipe_id} suppressed by world event"


def _plot_island(world: "World", plot: Any) -> int | None:
    """Resolve a plot to its island id (None if not on the island map)."""
    if plot is None:
        return None
    mapping = world.scenario_state.get("plot_islands") if hasattr(world, "scenario_state") else None
    if not mapping:
        return None
    raw = mapping.get(str(plot.plot_id))
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────
# Trigger helpers (test-callable + tick-loop-callable)
# ─────────────────────────────────────────────────────────────────────────


def trigger_drought(
    world: "World",
    island_id: int,
    *,
    severity: float = 0.6,
    duration_days: int | None = None,
) -> WorldEvent:
    """Open a drought event on ``island_id``. Idempotent if one is already active."""
    existing = active_event_for_island(world, island_id, {"drought"})
    if existing is not None:
        return existing
    if duration_days is None:
        rng = world.rng(f"drought-duration:{island_id}")
        duration_days = rng.randint(DROUGHT_MIN_DAYS, DROUGHT_MAX_DAYS)
    ev = _create_event(
        world,
        event_type="drought",
        severity=severity,
        duration_ticks=duration_days * TICKS_PER_GAME_DAY,
        island_id=int(island_id),
    )
    _announce_start(
        world,
        ev,
        f"Drought conditions forming on island {island_id}. Agricultural output falling.",
        duration_days=int(duration_days),
    )
    return ev


def trigger_blight(
    world: "World",
    island_id: int,
    *,
    recipe_id: str = "grow_grain",
    severity: float = 0.7,
    duration_days: int | None = None,
) -> WorldEvent:
    """Open a blight event affecting one specific crop recipe on ``island_id``."""
    existing = active_event_for_island(world, island_id, {"blight"})
    if existing is not None:
        return existing
    if duration_days is None:
        rng = world.rng(f"blight-duration:{island_id}:{recipe_id}")
        duration_days = rng.randint(BLIGHT_MIN_DAYS, BLIGHT_MAX_DAYS)
    ev = _create_event(
        world,
        event_type="blight",
        severity=severity,
        duration_ticks=duration_days * TICKS_PER_GAME_DAY,
        island_id=int(island_id),
        payload={"recipe_id": recipe_id},
    )
    _announce_start(
        world,
        ev,
        f"{recipe_id.replace('_', ' ').title()} blight reported on island {island_id}. "
        f"Affected plots suspending {recipe_id}.",
        recipe_id=recipe_id,
        duration_days=int(duration_days),
    )
    return ev


def trigger_storm(
    world: "World",
    island_id: int,
    *,
    severity: float = 0.6,
    duration_days: int | None = None,
) -> WorldEvent:
    """Open a storm event impacting vessels and coastal construction near ``island_id``."""
    existing = active_event_for_island(world, island_id, {"storm"})
    if existing is not None:
        return existing
    if duration_days is None:
        rng = world.rng(f"storm-duration:{island_id}")
        duration_days = rng.randint(STORM_MIN_DAYS, STORM_MAX_DAYS)
    ev = _create_event(
        world,
        event_type="storm",
        severity=severity,
        duration_ticks=duration_days * TICKS_PER_GAME_DAY,
        island_id=int(island_id),
    )
    _announce_start(
        world,
        ev,
        f"Storm making landfall on island {island_id}. Coastal operations suspended. "
        f"Active shipments delayed.",
        duration_days=int(duration_days),
    )
    # Storms delay every currently-in-transit shipment originating from or
    # arriving at this island, and spawn a follow-on flood with some probability.
    _apply_storm_transit_delays(world, ev)
    rng = world.rng(f"storm-flood-roll:{ev.event_id}")
    if rng.random() < STORM_FLOOD_FOLLOWUP_PROB:
        _spawn_flood_followup(world, ev)
    return ev


def trigger_mine_collapse(
    world: "World",
    plot_id: PlotId,
    *,
    severity: float = 0.8,
    instance_id: str | None = None,
) -> WorldEvent | None:
    """Destroy a single strip_mine instance on ``plot_id``.

    Returns the WorldEvent that was created, or ``None`` if there is no
    strip_mine on the plot.
    """
    target_row: dict | None = None
    pid_s = str(plot_id)
    for b in world.plot_buildings:
        if b.get("plot_id") != pid_s:
            continue
        if b.get("building_id") != "strip_mine":
            continue
        if b.get("status") != "complete":
            continue
        if instance_id is not None and str(b.get("instance_id")) != str(instance_id):
            continue
        target_row = b
        break
    if target_row is None:
        return None
    instance = str(target_row.get("instance_id") or "")
    party = str(target_row.get("party") or "")
    ev = _create_event(
        world,
        event_type="mine_collapse",
        severity=severity,
        duration_ticks=MINE_RUBBLE_DAYS * TICKS_PER_GAME_DAY,
        island_id=_plot_island(world, world.plots.get(plot_id)),
        affected_plots=[plot_id],
        payload={
            "instance_id": instance,
            "party": party,
            "building_id": "strip_mine",
        },
    )
    # Destroy the building. Maintenance record is dropped; the plot enters a
    # rubble window during which nothing can be built (handled at start_build).
    world.plot_buildings = [
        b for b in world.plot_buildings if b is not target_row
    ]
    world.building_maintenance.pop(instance, None)
    # Injure laborers employed at this plot.
    _injure_laborers_at_plot(world, plot_id)
    _announce_start(
        world,
        ev,
        f"{party}'s strip_mine at {plot_id} collapsed. Building destroyed. Workers injured.",
        plot_id=str(plot_id),
        party=party,
        instance_id=instance,
    )
    return ev


def trigger_seismic(
    world: "World",
    plot_id: PlotId,
    *,
    severity: float = 0.5,
    duration_days: int = 1,
) -> WorldEvent | None:
    """Open a seismic event centred on ``plot_id`` damaging buildings within radius."""
    plot = world.plots.get(plot_id)
    if plot is None:
        return None
    isl = _plot_island(world, plot)
    affected: list[PlotId] = []
    for p2 in world.plots.values():
        if max(abs(p2.x - plot.x), abs(p2.y - plot.y)) <= SEISMIC_RADIUS_TILES:
            affected.append(p2.plot_id)
    ev = _create_event(
        world,
        event_type="seismic",
        severity=severity,
        duration_ticks=max(1, duration_days) * TICKS_PER_GAME_DAY,
        island_id=isl,
        affected_plots=affected,
        payload={"epicentre": str(plot_id)},
    )
    _apply_seismic_damage(world, ev)
    _announce_start(
        world,
        ev,
        f"Seismic activity detected near {plot_id}. Buildings in the affected area have sustained damage.",
        affected_count=len(affected),
        epicentre=str(plot_id),
    )
    return ev


def trigger_flood(
    world: "World",
    plots: list[PlotId],
    *,
    severity: float = 0.5,
    duration_days: int | None = None,
    island_id: int | None = None,
) -> WorldEvent | None:
    """Open a flood event on the given plot list."""
    if not plots:
        return None
    if duration_days is None:
        rng = world.rng(f"flood-duration:{plots[0]}")
        duration_days = rng.randint(FLOOD_MIN_DAYS, FLOOD_MAX_DAYS)
    ev = _create_event(
        world,
        event_type="flood",
        severity=severity,
        duration_ticks=duration_days * TICKS_PER_GAME_DAY,
        island_id=island_id,
        affected_plots=list(plots),
    )
    _announce_start(
        world,
        ev,
        f"Flooding reported on {len(plots)} plots following the storm. "
        f"Agricultural operations temporarily suspended.",
        duration_days=int(duration_days),
    )
    return ev


# ─────────────────────────────────────────────────────────────────────────
# Effect appliers (called from triggers and from tick loop)
# ─────────────────────────────────────────────────────────────────────────


def _apply_storm_transit_delays(world: "World", ev: WorldEvent) -> None:
    """Push back ``arrive_tick`` for every shipment touching this island."""
    rng = world.rng(f"storm-delays:{ev.event_id}")
    mapping = world.scenario_state.get("plot_islands") or {}
    isl = ev.island_id
    delayed = 0
    for s in world.in_transit:
        from_isl = mapping.get(str(s.from_plot_id)) if s.from_plot_id else None
        to_isl = mapping.get(str(s.dest_plot_id))
        if isl is not None:
            from_match = from_isl is not None and int(from_isl) == int(isl)
            to_match = to_isl is not None and int(to_isl) == int(isl)
            if not (from_match or to_match):
                continue
        extra = rng.randint(STORM_MIN_TRANSIT_DELAY_TICKS, STORM_MAX_TRANSIT_DELAY_TICKS)
        s.arrive_tick = int(s.arrive_tick) + extra
        delayed += 1
    ev.payload["delayed_shipments"] = int(delayed)
    if delayed:
        log_event(
            world,
            "storm_delay",
            f"Storm delayed {delayed} shipment(s) touching island {isl}.",
            event_id=ev.event_id,
            island_id=isl,
            count=int(delayed),
        )


def _spawn_flood_followup(world: "World", storm: WorldEvent) -> None:
    """30% of storms spawn a flood on coastal-adjacent low plots of the same island."""
    isl = storm.island_id
    if isl is None:
        return
    mapping = world.scenario_state.get("plot_islands") or {}
    # Pick up to 6 random plots on this island as the flood footprint.
    candidates = [
        PlotId(pid_s)
        for pid_s, pisl in mapping.items()
        if int(pisl) == int(isl)
    ]
    if not candidates:
        return
    rng = world.rng(f"flood-pick:{storm.event_id}")
    rng.shuffle(candidates)
    chosen = candidates[: min(6, len(candidates))]
    trigger_flood(world, chosen, severity=storm.severity * 0.7, island_id=isl)


def _apply_seismic_damage(world: "World", ev: WorldEvent) -> None:
    """All buildings within radius drop to 60% efficiency; fragile ones destroyed."""
    affected_set = {str(p) for p in ev.affected_plots}
    destroyed: list[str] = []
    damaged: list[str] = []
    for b in list(world.plot_buildings):
        if b.get("plot_id") not in affected_set:
            continue
        if b.get("status") != "complete":
            continue
        iid = str(b.get("instance_id") or "")
        rec = world.building_maintenance.get(iid)
        if rec is not None and int(rec.get("missed_cycles", 0)) >= 2:
            destroyed.append(iid)
            world.plot_buildings = [bb for bb in world.plot_buildings if bb is not b]
            world.building_maintenance.pop(iid, None)
            continue
        if rec is not None:
            rec["efficiency_pct"] = min(int(rec.get("efficiency_pct", 100)), SEISMIC_AFFECTED_EFFICIENCY)
            rec["missed_cycles"] = max(int(rec.get("missed_cycles", 0)), 1)
            damaged.append(iid)
    # Tiny subsurface depletion on the epicentre plot (~5% across the board).
    # SubsurfaceRoll is frozen so we rebuild via dataclasses.replace.
    epic = ev.payload.get("epicentre")
    if epic:
        import dataclasses as _dc

        epic_plot = world.plots.get(PlotId(str(epic)))
        if epic_plot is not None:
            try:
                sub = epic_plot.subsurface
                updates = {
                    f.name: max(0.0, float(getattr(sub, f.name)) * SEISMIC_GRADE_DECAY)
                    for f in _dc.fields(sub)
                    if isinstance(getattr(sub, f.name), float)
                }
                if updates:
                    epic_plot.subsurface = _dc.replace(sub, **updates)
            except Exception:  # pragma: no cover - defensive
                pass
    ev.payload["destroyed"] = destroyed
    ev.payload["damaged"] = damaged


def _injure_laborers_at_plot(world: "World", plot_id: PlotId) -> None:
    """Drop health on laborers employed at this plot (mine collapse aftermath)."""
    pid_s = str(plot_id)
    # Laborers employed *at* this plot: cross-reference plot ownership.
    plot = world.plots.get(plot_id)
    if plot is None or plot.owner is None:
        return
    employer_s = str(plot.owner)
    injured: list[str] = []
    for lab in world.laborers.values():
        if lab.employer is None:
            continue
        if str(lab.employer) != employer_s:
            continue
        if lab.health <= MINE_COLLAPSE_INJURY_HEALTH:
            continue
        lab.health = MINE_COLLAPSE_INJURY_HEALTH
        injured.append(lab.laborer_id)
    if injured:
        log_event(
            world,
            "mine_injury",
            f"{len(injured)} laborer(s) injured by mine collapse at {plot_id}.",
            plot_id=pid_s,
            count=len(injured),
        )


# ─────────────────────────────────────────────────────────────────────────
# Stochastic roll loop (called from advance_tick once per game-day)
# ─────────────────────────────────────────────────────────────────────────


def _is_day_boundary(world: "World") -> bool:
    """True when ``world.tick`` is the first tick of a new game-day."""
    return int(world.tick) > 0 and int(world.tick) % TICKS_PER_GAME_DAY == 0


def _is_week_boundary(world: "World") -> bool:
    """True roughly once per game-week (7 game-days)."""
    return int(world.tick) > 0 and int(world.tick) % (TICKS_PER_GAME_DAY * 7) == 0


def _roll_droughts(world: "World") -> None:
    season = current_season(world)
    if season not in (Season.SUMMER, Season.AUTUMN):
        return
    mapping = world.scenario_state.get("plot_islands") or {}
    if not mapping:
        return
    islands = sorted({int(v) for v in mapping.values()})
    for isl in islands:
        if active_event_for_island(world, isl, {"drought"}) is not None:
            continue
        prob = DROUGHT_ARID_DAILY_PROB if isl == 3 else DROUGHT_BASE_DAILY_PROB
        rng = world.rng(f"drought-roll:y{int(world.tick) // TICKS_PER_GAME_DAY}:i{isl}")
        if rng.random() >= prob:
            # Optionally emit a pre-disaster signal a couple days before by
            # peeking at the upcoming RNG stream for this island. Pre-signals
            # are themselves recorded in scenario_state so we don't repeat.
            _maybe_emit_predisaster_signal(world, isl, prob)
            continue
        severity = 0.4 + world.rng(f"drought-sev:i{isl}:t{world.tick}").random() * 0.6
        trigger_drought(world, isl, severity=severity)


def _maybe_emit_predisaster_signal(world: "World", island_id: int, current_prob: float) -> None:
    """Emit a subtle "watch this island" feed line shortly before a drought lands.

    The signal is probabilistic and idempotent within a window so the player
    sees at most one warning per island per drought.
    """
    state = world.scenario_state.setdefault("predisaster_signals", {})
    key = f"island_{island_id}"
    last = int(state.get(key, -10_000_000))
    # 14-day cooldown so the channel doesn't spam.
    if int(world.tick) - last < 14 * TICKS_PER_GAME_DAY:
        return
    rng = world.rng(f"predisaster:i{island_id}:t{world.tick}")
    if rng.random() >= current_prob * 4.0:  # ~4× the base prob → roughly 2-day lead
        return
    state[key] = int(world.tick)
    log_event(
        world,
        "world_feed",
        f"Dry conditions reported on island {island_id} — agricultural watchers are monitoring closely.",
        event_class="predisaster_signal",
        island_id=int(island_id),
        signal_for="drought",
    )


def _roll_blights(world: "World") -> None:
    if current_season(world) is not Season.SUMMER:
        return
    if not _is_week_boundary(world):
        return
    mapping = world.scenario_state.get("plot_islands") or {}
    islands = sorted({int(v) for v in mapping.values()})
    for isl in islands:
        if active_event_for_island(world, isl, {"blight"}) is not None:
            continue
        rng = world.rng(f"blight-roll:w{int(world.tick) // (TICKS_PER_GAME_DAY * 7)}:i{isl}")
        if rng.random() < BLIGHT_WEEKLY_PROB:
            trigger_blight(world, isl, recipe_id="grow_grain")


def _roll_mine_collapses(world: "World") -> None:
    # Snapshot — trigger_mine_collapse mutates plot_buildings.
    rows = [
        b for b in world.plot_buildings
        if b.get("building_id") == "strip_mine" and b.get("status") == "complete"
    ]
    for row in rows:
        iid = str(row.get("instance_id") or "")
        pid_s = str(row.get("plot_id") or "")
        if not iid or not pid_s:
            continue
        rec = world.building_maintenance.get(iid)
        missed = int(rec.get("missed_cycles", 0)) if rec is not None else 0
        prob = MINE_BASE_DAILY_PROB * (1.0 + MINE_MISSED_CYCLE_MULT * missed)
        rng = world.rng(f"mine-roll:i{iid}:t{world.tick}")
        if rng.random() < prob:
            trigger_mine_collapse(world, PlotId(pid_s), severity=min(1.0, 0.4 + 0.2 * missed))


def _roll_storms(world: "World") -> None:
    season = current_season(world)
    if season not in (Season.AUTUMN, Season.WINTER):
        return
    mapping = world.scenario_state.get("plot_islands") or {}
    if not mapping:
        return
    islands = sorted({int(v) for v in mapping.values()})
    mult = STORM_WINTER_MULT if season is Season.WINTER else 1.0
    for isl in islands:
        if active_event_for_island(world, isl, {"storm"}) is not None:
            continue
        prob = STORM_BASE_DAILY_PROB * mult
        rng = world.rng(f"storm-roll:i{isl}:t{world.tick}")
        if rng.random() < prob:
            severity = 0.4 + world.rng(f"storm-sev:i{isl}:t{world.tick}").random() * 0.6
            trigger_storm(world, isl, severity=severity)


def _roll_seismic(world: "World") -> None:
    if not _is_week_boundary(world):
        return
    mapping = world.scenario_state.get("plot_islands") or {}
    if not mapping:
        return
    # Highland plots on islands 0 and 3 (per spec). Use terrain MOUNTAIN as proxy.
    from realm.world.terrain import Terrain

    rng = world.rng(f"seismic-roll:w{int(world.tick) // (TICKS_PER_GAME_DAY * 7)}")
    for plot in world.plots.values():
        if plot.terrain is not Terrain.MOUNTAIN:
            continue
        isl_raw = mapping.get(str(plot.plot_id))
        if isl_raw is None or int(isl_raw) not in SEISMIC_HIGH_RISK_ISLANDS:
            continue
        if rng.random() < SEISMIC_WEEKLY_PROB_PER_PLOT:
            trigger_seismic(world, plot.plot_id, severity=0.5)


# ─────────────────────────────────────────────────────────────────────────
# Phase 8C — Epidemic system
# ─────────────────────────────────────────────────────────────────────────


def trigger_epidemic(
    world: "World",
    town_id: str,
    *,
    severity: float = 0.6,
    duration_days: int | None = None,
) -> WorldEvent | None:
    """Open an epidemic event in ``town_id``.

    Returns the event or ``None`` if the town is unknown / already infected.
    """
    if town_id not in world.towns:
        return None
    # Don't double-fire on a town that already has an active epidemic.
    for ev in active_events(world):
        if ev.event_type == "epidemic" and ev.payload.get("town_id") == town_id:
            return ev
    if duration_days is None:
        rng = world.rng(f"epidemic-duration:{town_id}")
        duration_days = rng.randint(EPIDEMIC_MIN_DAYS, EPIDEMIC_MAX_DAYS)
    town = world.towns[town_id]
    isl = int(town.island_id) if str(town.island_id).lstrip("-").isdigit() else None
    ev = _create_event(
        world,
        event_type="epidemic",
        severity=severity,
        duration_ticks=duration_days * TICKS_PER_GAME_DAY,
        island_id=isl,
        payload={
            "town_id": town_id,
            "deaths": 0,
            "treated": [],
        },
    )
    _announce_start(
        world,
        ev,
        f"Epidemic reported in {town.name} on island {town.island_id}. "
        f"Laborers falling ill.",
        town_id=town_id,
        duration_days=int(duration_days),
    )
    return ev


def active_epidemic_for_town(world: "World", town_id: str) -> WorldEvent | None:
    """Return the active epidemic affecting ``town_id``, if any."""
    for ev in active_events(world):
        if ev.event_type == "epidemic" and ev.payload.get("town_id") == town_id:
            return ev
    return None


def epidemic_health_decay_multiplier(world: "World", town_id: str | None) -> float:
    """Health-decay multiplier for laborers in a town with an active epidemic.

    Laborers who have been treated this epidemic (``treated`` list in
    ``ev.payload``) decay at the normal rate; everyone else decays 3× faster.
    """
    if town_id is None:
        return 1.0
    ev = active_epidemic_for_town(world, town_id)
    if ev is None:
        return 1.0
    return EPIDEMIC_HEALTH_DECAY_MULT


def consume_medicine_for_treatment(
    world: "World", town_id: str, laborer_id: str
) -> bool:
    """Mark a laborer as treated for the active epidemic in their town.

    Called by ``stores.tick_laborer_spending`` after the laborer pays for
    medicine. Returns ``True`` if treatment was applied (i.e. epidemic
    active + laborer not yet treated this round); the caller is then
    responsible for the +0.30 health bump.
    """
    ev = active_epidemic_for_town(world, town_id)
    if ev is None:
        return False
    treated = ev.payload.setdefault("treated", [])
    if laborer_id in treated:
        return False
    treated.append(laborer_id)
    _flush_events_store(world)
    return True


def _roll_epidemics(world: "World") -> None:
    """Once per game-month per town: stochastic outbreak weighted by town health."""
    if not world.towns:
        return
    if int(world.tick) % TICKS_PER_GAME_MONTH != 0:
        return
    if int(world.tick) <= 0:
        return
    for town_id, town in list(world.towns.items()):
        if active_epidemic_for_town(world, town_id) is not None:
            continue
        # Town health = mean laborer health, defaulting to 1.0 if empty.
        residents = [
            lab for lab in world.laborers.values() if lab.home_town == town_id
        ]
        if not residents:
            continue
        town_health = sum(float(lab.health) for lab in residents) / len(residents)
        prob = EPIDEMIC_MONTHLY_PROB * max(0.0, 1.0 - town_health)
        if prob <= 0.0:
            continue
        rng = world.rng(f"epidemic-roll:m{int(world.tick) // TICKS_PER_GAME_MONTH}:t{town_id}")
        if rng.random() < prob:
            severity = 0.4 + world.rng(f"epidemic-sev:{town_id}:t{world.tick}").random() * 0.6
            trigger_epidemic(world, town_id, severity=severity)


def _kill_epidemic_victims(world: "World", ev: WorldEvent) -> None:
    """Apply death rolls to seriously ill laborers in the epidemic town.

    Called daily while the epidemic is active. Laborers with health <= 0.1
    die at the normal laborer-tick path; this helper is purely a no-op
    accounting hook for ``ev.payload["deaths"]`` so the end-of-epidemic
    feed entry can summarise.
    """
    town_id = ev.payload.get("town_id")
    if not town_id:
        return
    count_before = sum(
        1 for lab in world.laborers.values() if lab.home_town == town_id
    )
    ev.payload["last_count"] = int(count_before)


def _expire_finished_events(world: "World") -> None:
    """Close out events whose ``end_tick`` has passed."""
    for ev in active_events(world):
        if int(world.tick) < int(ev.end_tick):
            continue
        if ev.event_type == "drought":
            _announce_end(
                world,
                ev,
                f"Drought conditions on island {ev.island_id} have broken. "
                f"Agricultural output recovering.",
            )
        elif ev.event_type == "blight":
            _announce_end(
                world,
                ev,
                f"Blight on island {ev.island_id} has subsided. Sowing may resume.",
            )
        elif ev.event_type == "storm":
            _announce_end(
                world,
                ev,
                f"Storm on island {ev.island_id} has passed. Shipping resumed.",
            )
        elif ev.event_type == "flood":
            _announce_end(
                world,
                ev,
                f"Flood waters on island {ev.island_id} have receded.",
            )
        elif ev.event_type == "seismic":
            _announce_end(
                world,
                ev,
                f"Seismic aftershocks near {ev.payload.get('epicentre')} have ceased.",
            )
        elif ev.event_type == "mine_collapse":
            _announce_end(
                world,
                ev,
                f"Rubble cleared at {ev.affected_plots[0] if ev.affected_plots else '?'}. "
                f"Site may be rebuilt.",
            )
        elif ev.event_type == "epidemic":
            town_id = str(ev.payload.get("town_id", ""))
            deaths = int(ev.payload.get("deaths", 0))
            town_name = town_id
            if town_id and town_id in world.towns:
                town_name = world.towns[town_id].name
            _announce_end(
                world,
                ev,
                f"Epidemic in {town_name} has subsided. {deaths} laborer(s) lost.",
                town_id=town_id,
                deaths=int(deaths),
            )
        else:
            ev.resolved = True
            _flush_events_store(world)


def tick_world_events(world: "World") -> None:
    """Phase 8 — main entry point. Called once per ``advance_tick``."""
    if not events_enabled(world):
        # Still expire any pre-existing events so we don't strand them on
        # toggle-off.
        _expire_finished_events(world)
        return
    if _is_day_boundary(world):
        _roll_droughts(world)
        _roll_blights(world)
        _roll_mine_collapses(world)
        _roll_storms(world)
        _roll_seismic(world)
        _roll_epidemics(world)
    _expire_finished_events(world)


# ─────────────────────────────────────────────────────────────────────────
# Force-majeure helper for contracts (Phase 8B brief — storms shouldn't
# unfairly breach supply contracts when shipments are delayed).
# ─────────────────────────────────────────────────────────────────────────


def storm_force_majeure_extension_ticks(world: "World", island_id: int | None) -> int:
    """Return the number of ticks to extend a contract deadline when an
    active storm is delaying deliveries.

    Used by ``contracts.tick_supply_contract_breaches`` to grant grace when
    the affected ocean route is blockaded.
    """
    if island_id is None:
        return 0
    ev = active_event_for_island(world, island_id, {"storm"})
    if ev is None:
        return 0
    remaining = max(0, int(ev.end_tick) - int(world.tick))
    return int(remaining + TICKS_PER_GAME_DAY)
