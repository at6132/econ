"""Supply chain visibility signals (Sprint 6 — Phase C).

Three observable signals that surface market structure to the player without
revealing identities:

  * **Large buy detection** — when a party places a single buy order for
    ``LARGE_BUY_THRESHOLD_UNITS`` units or more, a ``large_buy_detected`` event
    is logged. The actor is never named.

  * **Supply concentration warning** — when a single party owns more than
    ``SUPPLY_CONCENTRATION_THRESHOLD_BPS`` of listed sell-side supply for a
    material, a ``world_feed`` entry is emitted. The actor is never named.

  * **Region activity per material** — aggregated public statistic showing
    which regions are selling a given material, derived from the public
    locations of the sellers' plots.

Identity remains hidden — analytics purchases (Sprint 4) are the only way to
discover *who* is behind a signal.
"""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.core.ids import MaterialId, PartyId
from realm.regions import region_for_plot
from realm.world import World

# Thresholds (game-design knobs).
LARGE_BUY_THRESHOLD_UNITS: int = 30
SUPPLY_CONCENTRATION_THRESHOLD_BPS: int = 3_500  # 35%


# ────────────────────────────────────────────────────────────────────────
# Supply concentration (sell-side)
# ────────────────────────────────────────────────────────────────────────


def _seller_units(world: World, material: MaterialId) -> dict[str, int]:
    """``seller_party_id_str -> total visible+iceberg units listed on this material``."""
    asks = world.market_asks_by_material.get(str(material), [])
    totals: dict[str, int] = {}
    for o in asks:
        units = int(getattr(o, "qty", 0)) + int(getattr(o, "iceberg_hidden_qty", 0))
        if units <= 0:
            continue
        totals[str(o.party)] = totals.get(str(o.party), 0) + units
    return totals


def _concentration_state(world: World) -> dict[str, int]:
    """Per-material last-warned tick, so we don't spam the feed repeatedly."""
    return world.scenario_state.setdefault("supply_concentration_last_warned", {})


def maybe_emit_supply_concentration(world: World, material: MaterialId) -> None:
    """Emit a ``world_feed`` line when one seller exceeds the concentration threshold.

    Suppresses re-emission for the same material within a 1440-tick window so a
    single dominant seller doesn't spam the feed every time they list another
    batch.
    """
    totals = _seller_units(world, material)
    total = sum(totals.values())
    if total <= 0:
        return
    # Concentration is only meaningful when at least 2 distinct sellers are listed.
    if len(totals) < 2:
        return
    top_seller, top_units = max(totals.items(), key=lambda kv: kv[1])
    share_bps = top_units * 10_000 // total
    if share_bps <= SUPPLY_CONCENTRATION_THRESHOLD_BPS:
        return
    state = _concentration_state(world)
    last = int(state.get(str(material), -10**9))
    if int(world.tick) - last < 1440:
        return
    state[str(material)] = int(world.tick)
    pct = share_bps // 100
    log_event(
        world,
        "world_feed",
        f"Supply concentration detected in {material} — one seller holds {pct}%+ of listed supply.",
        kind_tag="supply_concentration",
        material=str(material),
        share_pct=int(pct),
    )


# ────────────────────────────────────────────────────────────────────────
# Region activity per material
# ────────────────────────────────────────────────────────────────────────


def _party_primary_region(world: World, party: PartyId) -> str | None:
    """A representative region for ``party``'s plots, or ``None`` if it owns none.

    Picks the region with the most owned plots (ties broken by region id).
    """
    counts: dict[str, int] = {}
    for plot_id, plot in world.plots.items():
        if plot.owner != party:
            continue
        r = region_for_plot(world, plot_id)
        if r is None:
            continue
        counts[r] = counts.get(r, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def region_activity_for_material(
    world: World, material: MaterialId
) -> dict[str, Any]:
    """Aggregate sellers of ``material`` by their primary region.

    Returns ``{"material": str, "by_region": {region: units}, "primary_region": str|None}``.
    """
    asks = world.market_asks_by_material.get(str(material), [])
    by_region: dict[str, int] = {}
    for o in asks:
        units = int(getattr(o, "qty", 0)) + int(getattr(o, "iceberg_hidden_qty", 0))
        if units <= 0:
            continue
        seller = PartyId(str(o.party))
        r = _party_primary_region(world, seller)
        if r is None:
            continue
        by_region[r] = by_region.get(r, 0) + units
    primary: str | None = None
    if by_region:
        primary = sorted(by_region.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return {
        "material": str(material),
        "by_region": by_region,
        "primary_region": primary,
    }


def all_region_activity(world: World) -> list[dict[str, Any]]:
    """Region-activity per material (only materials with any listed supply)."""
    out: list[dict[str, Any]] = []
    for mat in sorted(world.market_asks_by_material.keys()):
        info = region_activity_for_material(world, MaterialId(mat))
        if info["by_region"]:
            out.append(info)
    return out


# ────────────────────────────────────────────────────────────────────────
# Trade flow aggregation (consumed by the UI overlay)
# ────────────────────────────────────────────────────────────────────────


def trade_flows_overlay(world: World) -> list[dict[str, Any]]:
    """Aggregate shipment counts per region-pair (from ``route_shipment_counts``)
    into flow lines the UI can draw as arrows."""
    raw = world.scenario_state.get("route_shipment_counts") or {}
    if not isinstance(raw, dict):
        return []
    out: list[dict[str, Any]] = []
    for key, count in raw.items():
        try:
            a, b = str(key).split(":", 1)
        except ValueError:
            continue
        try:
            c = int(count)
        except (TypeError, ValueError):
            continue
        if c <= 0:
            continue
        out.append({"from_region": a, "to_region": b, "shipments": c})
    out.sort(key=lambda d: -int(d["shipments"]))
    return out
