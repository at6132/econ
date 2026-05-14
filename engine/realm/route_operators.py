"""Route operators — shipping fees flow to the cheapest registered operator.

Sprint 2 — Phase A.

A "route" is an unordered pair of regions (see :mod:`realm.regions`). Any
party that owns a plot in either endpoint region with the right building
(``dock`` for coastal, ``waystation`` for inland-only) and the right capital
goods (``vessel`` for coastal) can register as the route's operator. The
operator sets a ``fee_per_tile_cents``; multiple operators may register on
the same route — the cheapest collects every shipment fee that flows on
that route.

State is persisted under ``world.scenario_state["route_operators"]``:

    {
        "<route_key>": [
            {
                "operator_party": <party_id>,
                "operator_plot": <plot_id>,
                "building": "dock" | "waystation",
                "fee_per_tile_cents": int,
                "registered_at_tick": int,
            },
            ...
        ]
    }

JSON-safe; round-trips through ``state_io`` without a snapshot bump.
"""

from __future__ import annotations

from typing import Any

from realm.events.event_log import log_event
from realm.core.ids import PartyId, PlotId
from realm.world.regions import region_for_plot, route_key
from realm.world import World


__all__ = [
    "ensure_route_state_initialised",
    "register_route",
    "list_route_operators",
    "find_cheapest_operator",
    "remove_party_operators",
    "set_operator_fee",
    "route_revenue_by_party_today",
    "record_route_fee_collected",
]


_ROUTE_OPERATING_BUILDINGS: frozenset[str] = frozenset({"dock", "waystation"})


def ensure_route_state_initialised(world: World) -> dict[str, Any]:
    """Get-or-create ``scenario_state["route_operators"]`` and its companions."""
    state = world.scenario_state
    operators = state.setdefault("route_operators", {})
    # Per-day revenue tally: ``{ "<party>": {"earned": int, "day": int} }``.
    state.setdefault("route_revenue", {})
    return operators


# ────────────────────────── building / vessel preconditions ──────────────────────────


def _party_has_operating_building(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    *,
    require_dock: bool,
) -> tuple[bool, str | None]:
    """Return (ok, building_id_used).

    Looks for a completed building on ``plot_id`` belonging to ``party`` that
    qualifies as a route-operating structure. When ``require_dock`` is True,
    only ``dock`` counts; when False, ``waystation`` is also acceptable.
    """
    wanted = {"dock"} if require_dock else _ROUTE_OPERATING_BUILDINGS
    for row in world.plot_buildings:
        if str(row.get("plot_id")) != str(plot_id):
            continue
        if str(row.get("party")) != str(party):
            continue
        bid = str(row.get("building_id"))
        if bid not in wanted:
            continue
        completes_at = int(row.get("completes_at_tick", 0))
        if int(world.tick) < completes_at:
            continue  # still under construction
        return (True, bid)
    return (False, None)


def _party_owns_vessel(world: World, party: PartyId) -> bool:
    from realm.core.ids import MaterialId

    return world.inventory.qty(party, MaterialId("vessel")) >= 1


# ────────────────────────── public API ──────────────────────────


def register_route(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    from_region: str,
    to_region: str,
    fee_per_tile_cents: int,
) -> dict:
    """Register ``party`` as an operator for the route between two regions.

    Preconditions (all enforced):
    - Plot must be owned by ``party`` and must lie in ``from_region`` or ``to_region``.
    - Plot must host a completed ``dock`` (coastal) or ``waystation`` (inland).
      Coastal routes (where either endpoint contains a coastal plot) require ``dock``;
      inland-only routes accept ``waystation``.
    - For coastal routes, ``party`` must hold at least one ``vessel`` (not consumed).
    - ``fee_per_tile_cents`` must be ≥ 1.
    - Same ``party`` cannot have two simultaneous registrations on the same route — a
      second call overwrites their previous entry (price revision).

    Returns ``{"ok": True, "route_key": ..., "building": ..., "fee_per_tile_cents": ...}``
    or ``{"ok": False, "reason": ...}``.
    """
    if int(fee_per_tile_cents) < 1:
        return {"ok": False, "reason": "fee_per_tile_cents must be >= 1"}
    if from_region == to_region:
        return {"ok": False, "reason": "from_region and to_region must differ"}
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    home = region_for_plot(world, plot_id)
    if home not in (from_region, to_region):
        return {
            "ok": False,
            "reason": f"plot {plot_id} (region {home}) is not in route endpoints",
        }
    # Coastal vs inland: if the plot itself is coastal the operator must run a dock; if
    # the plot is inland a waystation suffices (but a dock at an inland endpoint is also
    # fine — docks are strictly more capable). A pure inland-only operator never needs a
    # vessel.
    from realm.production.recipe_sites import plot_is_coastal

    plot_coastal = plot_is_coastal(world, plot)
    if plot_coastal:
        ok, bid = _party_has_operating_building(world, party, plot_id, require_dock=True)
        if not ok:
            return {"ok": False, "reason": "coastal route requires completed dock on plot"}
        if not _party_owns_vessel(world, party):
            return {"ok": False, "reason": "coastal route requires at least one vessel"}
    else:
        ok, bid = _party_has_operating_building(world, party, plot_id, require_dock=False)
        if not ok:
            return {
                "ok": False,
                "reason": "route registration requires completed dock or waystation on plot",
            }
    ensure_route_state_initialised(world)
    key = route_key(from_region, to_region)
    operators = world.scenario_state.setdefault("route_operators", {})
    entries: list[dict] = operators.setdefault(key, [])
    # Overwrite a previous entry from the same party (price revision via re-register).
    entries[:] = [e for e in entries if str(e.get("operator_party")) != str(party)]
    record = {
        "operator_party": str(party),
        "operator_plot": str(plot_id),
        "building": str(bid),
        "fee_per_tile_cents": int(fee_per_tile_cents),
        "registered_at_tick": int(world.tick),
    }
    entries.append(record)
    log_event(
        world,
        "route_registered",
        f"{party} registered route {key} at {fee_per_tile_cents}¢/tile from {plot_id}",
        party=str(party),
        route_key=key,
        plot_id=str(plot_id),
        building=str(bid),
        fee_per_tile_cents=int(fee_per_tile_cents),
    )
    return {
        "ok": True,
        "route_key": key,
        "building": bid,
        "fee_per_tile_cents": int(fee_per_tile_cents),
    }


def set_operator_fee(
    world: World,
    party: PartyId,
    route_key_str: str,
    new_fee_per_tile_cents: int,
) -> dict:
    """Revise a registered operator's ``fee_per_tile_cents`` in place."""
    if int(new_fee_per_tile_cents) < 1:
        return {"ok": False, "reason": "fee_per_tile_cents must be >= 1"}
    operators = world.scenario_state.get("route_operators") or {}
    entries = operators.get(str(route_key_str)) or []
    for e in entries:
        if str(e.get("operator_party")) == str(party):
            e["fee_per_tile_cents"] = int(new_fee_per_tile_cents)
            log_event(
                world,
                "route_fee_revised",
                f"{party} revised {route_key_str} fee → {new_fee_per_tile_cents}¢/tile",
                party=str(party),
                route_key=str(route_key_str),
                fee_per_tile_cents=int(new_fee_per_tile_cents),
            )
            return {"ok": True}
    return {"ok": False, "reason": "no existing registration for this party on this route"}


def list_route_operators(world: World, key: str) -> list[dict]:
    """Snapshot of registered operators for ``key``, sorted by fee ascending."""
    operators = world.scenario_state.get("route_operators") or {}
    entries = list(operators.get(str(key)) or [])
    entries.sort(key=lambda e: (int(e.get("fee_per_tile_cents", 0)), int(e.get("registered_at_tick", 0))))
    return entries


def find_cheapest_operator(world: World, key: str) -> dict | None:
    """The current winning operator for ``key`` (lowest fee, oldest tie-break)."""
    entries = list_route_operators(world, key)
    return entries[0] if entries else None


def remove_party_operators(world: World, party: PartyId) -> int:
    """Drop every registration belonging to ``party`` (e.g. bankruptcy cleanup)."""
    operators = world.scenario_state.get("route_operators") or {}
    n = 0
    for key, entries in list(operators.items()):
        keep = [e for e in entries if str(e.get("operator_party")) != str(party)]
        if len(keep) != len(entries):
            n += len(entries) - len(keep)
            if keep:
                operators[key] = keep
            else:
                operators.pop(key, None)
    return n


# ────────────────────────── revenue tracking ──────────────────────────


_REVENUE_DAY_TICKS: int = 1440


def _current_game_day(world: World) -> int:
    return int(world.tick) // _REVENUE_DAY_TICKS


def record_route_fee_collected(
    world: World,
    operator: PartyId,
    route_key_str: str,
    fee_cents: int,
) -> None:
    """Bookkeeping: tally per-day revenue per operator for the UI / NPC AI."""
    ensure_route_state_initialised(world)
    revenue = world.scenario_state.setdefault("route_revenue", {})
    party_key = str(operator)
    day = _current_game_day(world)
    rec = revenue.setdefault(party_key, {"earned": 0, "day": day, "routes": {}})
    if int(rec.get("day", day)) != day:
        # Roll the day: keep the previous total in ``previous_earned`` for one
        # day so the UI / NPC AI can read "yesterday's revenue" deterministically.
        rec["previous_earned"] = int(rec.get("earned", 0))
        rec["previous_routes"] = dict(rec.get("routes") or {})
        rec["earned"] = 0
        rec["routes"] = {}
        rec["day"] = day
    rec["earned"] = int(rec.get("earned", 0)) + int(fee_cents)
    routes = rec.setdefault("routes", {})
    routes[str(route_key_str)] = int(routes.get(str(route_key_str), 0)) + int(fee_cents)


def route_revenue_by_party_today(world: World, party: PartyId) -> int:
    revenue = world.scenario_state.get("route_revenue") or {}
    rec = revenue.get(str(party)) or {}
    if int(rec.get("day", -1)) != _current_game_day(world):
        return 0
    return int(rec.get("earned", 0))


def route_revenue_by_party_previous_day(world: World, party: PartyId) -> int:
    """Revenue from the most recent fully-completed game-day (yesterday)."""
    revenue = world.scenario_state.get("route_revenue") or {}
    rec = revenue.get(str(party)) or {}
    today = _current_game_day(world)
    if int(rec.get("day", -1)) == today:
        return int(rec.get("previous_earned", 0))
    return int(rec.get("earned", 0))
