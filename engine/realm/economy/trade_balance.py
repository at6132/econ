"""Regional trade balance — net material flows between grid regions."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from realm.core.ids import MaterialId, PlotId
from realm.events.event_log import log_event
from realm.world import World
from realm.world.regions import region_for_plot


def record_shipment_flow(
    world: World,
    from_plot_id: PlotId,
    to_plot_id: PlotId,
    material: MaterialId,
    qty: int,
    value_cents: int,
) -> None:
    """Record inter-region shipment value after a successful dispatch."""
    from_region = _plot_to_region_id(world, from_plot_id)
    to_region = _plot_to_region_id(world, to_plot_id)
    if from_region == to_region:
        return
    flows: dict[str, Any] = world.scenario_state.setdefault("trade_flows_today", {})
    flows.setdefault(
        from_region, {"exports_cents": 0, "imports_cents": 0, "top_exports": {}}
    )
    flows[from_region]["exports_cents"] = int(flows[from_region]["exports_cents"]) + int(
        value_cents
    )
    mat_str = str(material)
    top: dict[str, int] = flows[from_region]["top_exports"]
    top[mat_str] = int(top.get(mat_str, 0)) + int(qty)
    flows.setdefault(to_region, {"exports_cents": 0, "imports_cents": 0, "top_exports": {}})
    flows[to_region]["imports_cents"] = int(flows[to_region]["imports_cents"]) + int(
        value_cents
    )


def _plot_to_region_id(world: World, plot_id: PlotId) -> str:
    rid = region_for_plot(world, plot_id)
    if rid is not None:
        return rid
    lm = world.landmass_id.get(str(plot_id), -1)
    return f"landmass_{lm}"


def tick_trade_balance(world: World) -> None:
    """Daily: roll today's flows into 30-day history."""
    if int(world.tick) % 1440 != 0:
        return
    today = world.scenario_state.pop("trade_flows_today", {})
    history: list[dict[str, Any]] = world.scenario_state.setdefault("trade_balance_history", [])
    game_day = int(world.tick) // 1440
    daily_entry: dict[str, Any] = {"game_day": game_day, "regions": {}}
    for region_id, flows in today.items():
        if not isinstance(flows, dict):
            continue
        exp = int(flows.get("exports_cents", 0))
        imp = int(flows.get("imports_cents", 0))
        top_exports = sorted(
            (flows.get("top_exports") or {}).items(),
            key=lambda x: -int(x[1]),
        )[:3]
        daily_entry["regions"][region_id] = {
            "exports_cents": exp,
            "imports_cents": imp,
            "net_cents": exp - imp,
            "top_exports": [{"material": m, "qty": q} for m, q in top_exports],
        }
        if abs(exp - imp) > 100_000:
            direction = "surplus" if exp > imp else "deficit"
            log_event(
                world,
                "world_feed",
                (
                    f"📦 Region {region_id} has a trade {direction} today: "
                    f"exports ${exp / 100:.0f}, imports ${imp / 100:.0f}"
                ),
                region_id=region_id,
                surplus_cents=exp - imp,
            )
    history.append(daily_entry)
    del history[:-30]


def get_trade_balance_summary(world: World) -> dict[str, dict[str, int]]:
    """Cumulative trade balance per region over the last 30 game-days."""
    history = world.scenario_state.get("trade_balance_history") or []
    summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {"exports_cents": 0, "imports_cents": 0, "net_cents": 0}
    )
    for day_entry in history:
        if not isinstance(day_entry, dict):
            continue
        for region_id, flows in (day_entry.get("regions") or {}).items():
            if not isinstance(flows, dict):
                continue
            summary[region_id]["exports_cents"] += int(flows.get("exports_cents", 0))
            summary[region_id]["imports_cents"] += int(flows.get("imports_cents", 0))
            summary[region_id]["net_cents"] += int(flows.get("net_cents", 0))
    return dict(summary)
