"""Consumer Price Index — weekly basket cost vs a seeded base period."""

from __future__ import annotations

from typing import Any, Final

from realm.events.event_log import log_event
from realm.world import World

CPI_BASKET: Final[dict[str, float]] = {
    "grain": 0.30,
    "coal": 0.20,
    "lumber": 0.15,
    "medicine": 0.10,
    "iron_ingot": 0.10,
    "timber": 0.08,
    "electricity": 0.07,
}

BASE_CPI: Final[float] = 100.0
TICKS_PER_GAME_WEEK: Final[int] = 10_080


def _best_ask_price_cents(world: World, mat_id: str) -> int | None:
    asks = world.market_asks_by_material.get(mat_id, [])
    if not asks:
        return None
    return min(int(a.price_per_unit_cents) for a in asks)


def compute_cpi(world: World) -> float:
    """CPI = 100 × (current basket cost / base basket cost)."""
    current_cost = 0.0
    base_cost = world.scenario_state.get("cpi_base_basket_cost")
    for mat_id, weight in CPI_BASKET.items():
        price_f: float
        bp = _best_ask_price_cents(world, mat_id)
        if bp is not None:
            price_f = float(bp)
        else:
            history: list[dict[str, Any]] = list(world.scenario_state.get("cpi_history") or [])
            last: int | None = None
            for h in reversed(history):
                cp = h.get("component_prices") or {}
                if isinstance(cp, dict) and mat_id in cp and cp[mat_id] is not None:
                    last = int(cp[mat_id])
                    break
            price_f = float(last if last is not None else 100)
        current_cost += price_f * float(weight)

    if base_cost is None:
        world.scenario_state["cpi_base_basket_cost"] = max(float(current_cost), 1.0)
        return BASE_CPI
    bc = float(base_cost)
    if bc <= 0.0:
        return BASE_CPI
    return BASE_CPI * (current_cost / bc)


def tick_cpi(world: World) -> None:
    """Record CPI weekly; emit world_feed on large week-over-week moves."""
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_WEEK != 0:
        return
    cpi = float(compute_cpi(world))
    component_prices: dict[str, int] = {}
    for mat_id in CPI_BASKET:
        p = _best_ask_price_cents(world, mat_id)
        if p is not None:
            component_prices[mat_id] = int(p)
    hist = world.scenario_state.setdefault("cpi_history", [])
    if not isinstance(hist, list):
        world.scenario_state["cpi_history"] = []
        hist = world.scenario_state["cpi_history"]
    hist.append({"tick": int(world.tick), "cpi": cpi, "component_prices": component_prices})
    trimmed = hist[-52:]
    world.scenario_state["cpi_history"] = trimmed
    world.scenario_state["cpi_current"] = cpi
    if len(trimmed) >= 2:
        prev = float(trimmed[-2]["cpi"])
        if prev > 0.0:
            change_pct = (cpi - prev) / prev * 100.0
            if abs(change_pct) >= 3.0:
                direction = "rose" if change_pct > 0 else "fell"
                msg = (
                    f"Price levels {direction} {abs(change_pct):.1f}% this week "
                    f"(CPI: {cpi:.1f}). "
                    + (
                        "Inflation is eroding purchasing power."
                        if change_pct > 0
                        else "Deflation is tightening the economy."
                    )
                )
                log_event(
                    world,
                    "world_feed",
                    msg,
                    feed_source="cpi_alert",
                    cpi=cpi,
                    change_pct=change_pct,
                )


def cpi_multiplier(world: World) -> float:
    """Scale factor current_cpi/100 for indexed cash flows."""
    v = world.scenario_state.get("cpi_current")
    if v is None:
        return 1.0
    return max(0.01, float(v) / BASE_CPI)
