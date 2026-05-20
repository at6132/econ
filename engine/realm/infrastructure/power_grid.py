"""
Regional power grid — replaces the old binary powered/not-powered system.

A GridRegion is a set of plots connected by the road network.
Generators in a region sell electricity into the region's pool.
Consumers in the region buy from that pool at the clearing price.
If load > capacity → brownout: all consumer buildings take an efficiency hit.

Clearing runs once per game-day (1440 ticks).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.events.event_log import log_event
from realm.world import World

ELECTRICITY = MaterialId("electricity")

POWER_PRICE_FLOOR_CENTS: int = 1
POWER_PRICE_CEILING_CENTS: int = 500
POWER_BASE_PRICE_CENTS: int = 40

BROWNOUT_THRESHOLD: float = 0.95

POWER_GENERATOR_BLUEPRINTS: dict[str, int] = {
    "power_shed": 24,
    "tidal_mill": 2,
}

_TICKS_PER_GAME_DAY: int = 1440


@dataclass
class GridRegion:
    region_id: str
    plot_ids: set[str] = field(default_factory=set)
    generator_instance_ids: list[str] = field(default_factory=list)
    capacity_per_day: int = 0
    load_per_day: int = 0
    clearing_price_cents: int = POWER_BASE_PRICE_CENTS
    load_factor: float = 0.0
    revenue_settled_cents: int = 0


def _build_road_graph(world: World) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for seg in world.road_segments:
        a, b = str(seg.from_plot), str(seg.to_plot)
        graph[a].add(b)
        graph[b].add(a)
    return graph


def _legacy_generator_active(world: World, row: dict[str, Any]) -> bool:
    iid = str(row.get("instance_id") or "")
    if iid:
        maint = world.building_maintenance.get(iid) or {}
        if int(maint.get("efficiency_pct", 100)) <= 0:
            return False
    completes = int(row.get("completes_at_tick", 0))
    return completes <= int(world.tick)


def _attach_generators(world: World, regions: dict[str, GridRegion]) -> None:
    plot_to_region: dict[str, str] = {}
    for rid, reg in regions.items():
        for pid in reg.plot_ids:
            plot_to_region[pid] = rid

    for pb in world.placed_buildings.values():
        if pb.blueprint_id not in POWER_GENERATOR_BLUEPRINTS:
            continue
        if str(pb.status) != "active":
            continue
        rid = plot_to_region.get(str(pb.plot_id))
        if rid is None:
            continue
        eff = int(world.building_maintenance.get(pb.instance_id, {}).get("efficiency_pct", 100))
        base_capacity = POWER_GENERATOR_BLUEPRINTS[pb.blueprint_id]
        effective_capacity = int(base_capacity * eff / 100)
        regions[rid].generator_instance_ids.append(pb.instance_id)
        regions[rid].capacity_per_day += effective_capacity

    for row in world.plot_buildings:
        bid = str(row.get("building_id", ""))
        if bid not in POWER_GENERATOR_BLUEPRINTS:
            continue
        if not _legacy_generator_active(world, row):
            continue
        iid = str(row.get("instance_id", ""))
        pid = str(row.get("plot_id", ""))
        rid = plot_to_region.get(pid)
        if rid is None:
            continue
        eff = int(world.building_maintenance.get(iid, {}).get("efficiency_pct", 100))
        base_capacity = POWER_GENERATOR_BLUEPRINTS[bid]
        effective_capacity = int(base_capacity * eff / 100)
        if iid and iid not in regions[rid].generator_instance_ids:
            regions[rid].generator_instance_ids.append(iid)
            regions[rid].capacity_per_day += effective_capacity


def compute_grid_regions(world: World) -> dict[str, GridRegion]:
    graph = _build_road_graph(world)
    visited: set[str] = set()
    regions: dict[str, GridRegion] = {}
    region_seq = 0

    road_plots = set(graph.keys())
    for start in sorted(road_plots):
        if start in visited:
            continue
        component: set[str] = set()
        queue = deque([start])
        while queue:
            pid = queue.popleft()
            if pid in visited:
                continue
            visited.add(pid)
            component.add(pid)
            for nbr in graph.get(pid, []):
                if nbr not in visited:
                    queue.append(nbr)
        rid = f"grid_{region_seq:04d}"
        region_seq += 1
        regions[rid] = GridRegion(region_id=rid, plot_ids=component)

    for pid in world.plots:
        if str(pid) not in visited:
            rid = f"grid_iso_{pid}"
            regions[rid] = GridRegion(region_id=rid, plot_ids={str(pid)})

    _attach_generators(world, regions)
    return regions


def _compute_clearing_price(load_factor: float) -> int:
    if load_factor <= 0:
        return POWER_PRICE_FLOOR_CENTS
    if load_factor >= 2.0:
        return POWER_PRICE_CEILING_CENTS
    if load_factor <= 1.0:
        price = POWER_BASE_PRICE_CENTS * (0.5 + 0.7 * load_factor)
    else:
        price = POWER_BASE_PRICE_CENTS * (1.2 + 2.6 * (load_factor - 1.0))
    return int(max(POWER_PRICE_FLOOR_CENTS, min(POWER_PRICE_CEILING_CENTS, price)))


def _build_plot_region_map(regions: dict[str, GridRegion]) -> dict[str, str]:
    return {pid: rid for rid, reg in regions.items() for pid in reg.plot_ids}


def _generator_owner_and_capacity(
    world: World, iid: str
) -> tuple[PartyId | None, int]:
    pb = world.placed_buildings.get(iid)
    if pb is not None:
        eff = int(world.building_maintenance.get(iid, {}).get("efficiency_pct", 100))
        cap = int(POWER_GENERATOR_BLUEPRINTS.get(pb.blueprint_id, 0) * eff / 100)
        return PartyId(pb.built_by), cap
    for row in world.plot_buildings:
        if str(row.get("instance_id", "")) != iid:
            continue
        bid = str(row.get("building_id", ""))
        eff = int(world.building_maintenance.get(iid, {}).get("efficiency_pct", 100))
        cap = int(POWER_GENERATOR_BLUEPRINTS.get(bid, 0) * eff / 100)
        return PartyId(str(row.get("party", ""))), cap
    return None, 0


def _settle_power_payments(
    world: World,
    reg: GridRegion,
    total_load: int,
    plot_to_region: dict[str, str],
    load_tracker: dict[str, int],
) -> None:
    price = reg.clearing_price_cents
    if price <= 0:
        return

    total_collected = 0
    for pid, load in load_tracker.items():
        if plot_to_region.get(pid) != reg.region_id:
            continue
        if load <= 0:
            continue
        plot = world.plots.get(PlotId(pid))
        if plot is None or plot.owner is None:
            continue
        cost = load * price
        src = party_cash_account(plot.owner)
        bal = world.ledger.balance(src)
        actual = min(cost, bal)
        if actual > 0:
            world.ledger.transfer(
                debit=src,
                credit=system_reserve_account(),
                amount_cents=actual,
            )
            total_collected += actual

    if total_collected <= 0 or not reg.generator_instance_ids:
        return

    total_cap = reg.capacity_per_day or 1
    for iid in reg.generator_instance_ids:
        owner, cap = _generator_owner_and_capacity(world, iid)
        if owner is None or cap <= 0:
            continue
        share = int(total_collected * cap / total_cap)
        if share > 0:
            world.ledger.transfer(
                debit=system_reserve_account(),
                credit=party_cash_account(owner),
                amount_cents=share,
            )
    reg.revenue_settled_cents = total_collected


def _iter_consumer_maintenance(
    world: World, reg: GridRegion
) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    region_plots = reg.plot_ids
    for pb in world.placed_buildings.values():
        if str(pb.plot_id) not in region_plots:
            continue
        if pb.blueprint_id in POWER_GENERATOR_BLUEPRINTS:
            continue
        maint = world.building_maintenance.setdefault(
            pb.instance_id,
            {"efficiency_pct": 100, "missed_cycles": 0, "due_at_tick": 0},
        )
        out.append((pb.instance_id, maint))
    for row in world.plot_buildings:
        pid = str(row.get("plot_id", ""))
        if pid not in region_plots:
            continue
        bid = str(row.get("building_id", ""))
        if bid in POWER_GENERATOR_BLUEPRINTS:
            continue
        iid = str(row.get("instance_id", ""))
        if not iid:
            continue
        maint = world.building_maintenance.setdefault(
            iid,
            {"efficiency_pct": 100, "missed_cycles": 0, "due_at_tick": 0},
        )
        out.append((iid, maint))
    return out


def _apply_brownout(world: World, reg: GridRegion) -> None:
    if reg.load_factor <= BROWNOUT_THRESHOLD:
        _clear_brownout_penalty(world, reg)
        return

    multiplier = min(1.0, reg.capacity_per_day / max(1, reg.load_per_day))
    penalty_pct = int(multiplier * 100)

    for _iid, maint in _iter_consumer_maintenance(world, reg):
        base_eff = min(100, int(maint.get("base_efficiency_pct", maint.get("efficiency_pct", 100))))
        if "base_efficiency_pct" not in maint:
            maint["base_efficiency_pct"] = base_eff
        brownout_eff = int(base_eff * penalty_pct / 100)
        maint["efficiency_pct"] = brownout_eff
        maint["brownout_penalty"] = True


def _clear_brownout_penalty(world: World, reg: GridRegion) -> None:
    for _iid, maint in _iter_consumer_maintenance(world, reg):
        if maint.get("brownout_penalty"):
            maint["efficiency_pct"] = int(maint.get("base_efficiency_pct", 100))
            maint.pop("brownout_penalty", None)


def _emit_power_events(world: World, reg: GridRegion) -> None:
    if reg.capacity_per_day == 0:
        return
    lf = reg.load_factor
    if lf > 1.5:
        eff_pct = int(100 / lf) if lf > 0 else 0
        log_event(
            world,
            "world_feed",
            f"⚡ POWER CRISIS: Grid region {reg.region_id} at {lf:.0%} load. "
            f"Brownout active — all connected buildings at {eff_pct}% efficiency. "
            f"Clearing price: {reg.clearing_price_cents}c/unit.",
            feed_source="power_grid",
            load_factor=lf,
        )
    elif lf > BROWNOUT_THRESHOLD:
        log_event(
            world,
            "world_feed",
            f"⚡ Power warning: Grid {reg.region_id} near capacity ({lf:.0%}). "
            f"Price: {reg.clearing_price_cents}c/unit.",
            feed_source="power_grid",
            load_factor=lf,
        )
    elif lf < 0.3 and reg.load_per_day > 0:
        log_event(
            world,
            "world_feed",
            f"⚡ Power surplus: Grid {reg.region_id} has excess generation "
            f"({lf:.0%} utilized). Price dropped to {reg.clearing_price_cents}c/unit.",
            feed_source="power_grid",
            load_factor=lf,
        )


def serialize_regions(regions: dict[str, GridRegion]) -> list[dict[str, Any]]:
    return [
        {
            "region_id": r.region_id,
            "plot_count": len(r.plot_ids),
            "capacity_per_day": r.capacity_per_day,
            "load_per_day": r.load_per_day,
            "clearing_price_cents": r.clearing_price_cents,
            "load_factor": round(r.load_factor, 3),
            "revenue_settled_cents": r.revenue_settled_cents,
        }
        for r in regions.values()
        if r.capacity_per_day > 0 or r.load_per_day > 0
    ]


def tick_power_grid(world: World) -> None:
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return

    regions = compute_grid_regions(world)
    load_tracker: dict[str, int] = dict(world.scenario_state.pop("power_load_today", {}) or {})
    plot_to_region = _build_plot_region_map(regions)

    for reg in regions.values():
        region_load = sum(
            v for pid, v in load_tracker.items() if plot_to_region.get(pid) == reg.region_id
        )
        reg.load_per_day = region_load

        if reg.capacity_per_day == 0:
            reg.load_factor = float("inf") if region_load > 0 else 0.0
            reg.clearing_price_cents = POWER_PRICE_CEILING_CENTS if region_load > 0 else 0
        else:
            reg.load_factor = region_load / reg.capacity_per_day
            reg.clearing_price_cents = _compute_clearing_price(reg.load_factor)

        if region_load > 0 and reg.capacity_per_day > 0:
            _settle_power_payments(world, reg, region_load, plot_to_region, load_tracker)

        _apply_brownout(world, reg)
        _emit_power_events(world, reg)

    world.scenario_state["power_regions"] = serialize_regions(regions)
    world.scenario_state["power_load_today"] = {}


def record_electricity_consumed(world: World, plot_id: PlotId, units: int) -> None:
    tracker = world.scenario_state.setdefault("power_load_today", {})
    tracker[str(plot_id)] = tracker.get(str(plot_id), 0) + units


def plot_has_grid_capacity(world: World, plot_id: PlotId) -> bool:
    """True if the plot's road-connected region has at least one active generator."""
    plot_to_region = _build_plot_region_map(compute_grid_regions(world))
    rid = plot_to_region.get(str(plot_id))
    if rid is None:
        return False
    regions = compute_grid_regions(world)
    reg = regions.get(rid)
    return reg is not None and reg.capacity_per_day > 0


def get_plot_power_info(world: World, plot_id: PlotId) -> dict[str, Any]:
    regions = compute_grid_regions(world)
    serialized = serialize_regions(regions)
    if not world.scenario_state.get("power_regions"):
        world.scenario_state["power_regions"] = serialized
    else:
        serialized = list(world.scenario_state.get("power_regions") or serialized)

    plot_to_region = _build_plot_region_map(regions)
    pid = str(plot_id)
    rid = plot_to_region.get(pid)
    if rid is None:
        return {
            "ok": True,
            "plot_id": pid,
            "powered": False,
            "reason": "plot not on road network",
            "clearing_price_cents": POWER_PRICE_CEILING_CENTS,
        }

    reg = regions[rid]
    if rid.startswith("grid_iso_"):
        return {
            "ok": True,
            "plot_id": pid,
            "powered": False,
            "reason": "isolated plot — no road access",
            "region_id": rid,
            "clearing_price_cents": POWER_PRICE_CEILING_CENTS,
            "load_factor": reg.load_factor,
            "brownout": False,
            "capacity_per_day": 0,
            "load_per_day": reg.load_per_day,
        }

    r_data = next((r for r in serialized if r["region_id"] == rid), None)
    if r_data is None:
        r_data = {
            "region_id": rid,
            "clearing_price_cents": reg.clearing_price_cents,
            "load_factor": round(reg.load_factor, 3),
            "capacity_per_day": reg.capacity_per_day,
            "load_per_day": reg.load_per_day,
        }

    lf = float(r_data.get("load_factor", reg.load_factor))
    return {
        "ok": True,
        "plot_id": pid,
        "powered": reg.capacity_per_day > 0,
        "region_id": rid,
        "clearing_price_cents": int(r_data.get("clearing_price_cents", reg.clearing_price_cents)),
        "load_factor": lf,
        "brownout": lf > BROWNOUT_THRESHOLD,
        "capacity_per_day": int(r_data.get("capacity_per_day", reg.capacity_per_day)),
        "load_per_day": int(r_data.get("load_per_day", reg.load_per_day)),
    }
