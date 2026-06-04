"""Grid utility operators — franchise registration for regional power sellers.

Mirrors :mod:`realm.infrastructure.route_operators`: physical asset + registry
record + published tariff before a party appears as a grid provider.
"""

from __future__ import annotations

from typing import Any

from realm.actions._shared import ActionResult
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.events.event_log import log_event
from realm.infrastructure.power_grid import (
    POWER_GENERATOR_BLUEPRINTS,
    POWER_PRICE_CEILING_CENTS,
    POWER_PRICE_FLOOR_CENTS,
    _build_plot_region_map,
    compute_grid_regions,
)
from realm.infrastructure.road_connectivity import is_road_accessible
from realm.world import World

GRID_UTILITY_FRANCHISE_FEE_CENTS: int = 2_500  # $25.00

__all__ = [
    "GRID_UTILITY_FRANCHISE_FEE_CENTS",
    "ensure_grid_operators_initialised",
    "list_grid_operators",
    "list_party_grid_operators",
    "register_grid_operator",
    "update_grid_operator_tariff",
    "unregister_grid_operator",
    "tick_grid_operators",
    "seed_grid_operator",
    "operator_record_public",
    "is_registered_grid_operator",
]


def ensure_grid_operators_initialised(world: World) -> dict[str, list[dict[str, Any]]]:
    raw = world.scenario_state.setdefault("grid_operators", {})
    if not isinstance(raw, dict):
        world.scenario_state["grid_operators"] = {}
        return world.scenario_state["grid_operators"]
    return raw


def region_id_for_plot(world: World, plot_id: PlotId) -> str | None:
    return _build_plot_region_map(compute_grid_regions(world)).get(str(plot_id))


def _active_power_shed_on_plot(
    world: World, party: PartyId, plot_id: PlotId
) -> tuple[str | None, int]:
    """Return (instance_id, capacity_wh) for party's active power_shed on plot."""
    best_iid: str | None = None
    best_cap = 0
    for pb in world.placed_buildings.values():
        if str(pb.plot_id) != str(plot_id):
            continue
        if str(pb.built_by) != str(party):
            continue
        if pb.blueprint_id not in POWER_GENERATOR_BLUEPRINTS:
            continue
        if str(pb.status) != "active":
            continue
        eff = int(world.building_maintenance.get(pb.instance_id, {}).get("efficiency_pct", 100))
        if eff <= 0:
            continue
        cap = int(POWER_GENERATOR_BLUEPRINTS[pb.blueprint_id] * eff / 100)
        if cap > best_cap:
            best_cap = cap
            best_iid = pb.instance_id
    for row in world.plot_buildings:
        if str(row.get("plot_id", "")) != str(plot_id):
            continue
        if str(row.get("party", "")) != str(party):
            continue
        bid = str(row.get("building_id", ""))
        if bid not in POWER_GENERATOR_BLUEPRINTS:
            continue
        if int(row.get("completes_at_tick", 0)) > int(world.tick):
            continue
        iid = str(row.get("instance_id", ""))
        if not iid:
            continue
        eff = int(world.building_maintenance.get(iid, {}).get("efficiency_pct", 100))
        if eff <= 0:
            continue
        cap = int(POWER_GENERATOR_BLUEPRINTS[bid] * eff / 100)
        if cap > best_cap:
            best_cap = cap
            best_iid = iid
    return best_iid, best_cap


def operator_record_public(world: World, row: dict[str, Any]) -> dict[str, Any]:
    party_s = str(row.get("operator_party", ""))
    return {
        "operator_party": party_s,
        "operator_name": world.party_display_names.get(
            party_s, party_s.replace("_", " ").title()
        ),
        "operator_plot": str(row.get("operator_plot", "")),
        "region_id": str(row.get("region_id", "")),
        "shed_instance_id": str(row.get("shed_instance_id", "")),
        "business_name": str(row.get("business_name", "")),
        "rate_cents_per_kwh": int(row.get("rate_cents_per_kwh", 0)),
        "min_wh_per_day": int(row.get("min_wh_per_day", 0)),
        "max_wh_per_day": int(row.get("max_wh_per_day", 0)),
        "registered_at_tick": int(row.get("registered_at_tick", 0)),
        "status": str(row.get("status", "active")),
        "suspend_reason": str(row.get("suspend_reason") or ""),
    }


def list_grid_operators(
    world: World, region_id: str | None = None, *, active_only: bool = True
) -> list[dict[str, Any]]:
    ops = ensure_grid_operators_initialised(world)
    out: list[dict[str, Any]] = []
    regions = ops.items() if region_id is None else [(region_id, ops.get(region_id, []))]
    for rid, entries in regions:
        if not isinstance(entries, list):
            continue
        for row in entries:
            if active_only and row.get("status") != "active":
                continue
            pub = operator_record_public(world, row)
            pub["region_id"] = str(rid)
            out.append(pub)
    return out


def list_party_grid_operators(world: World, party: PartyId) -> list[dict[str, Any]]:
    ops = ensure_grid_operators_initialised(world)
    out: list[dict[str, Any]] = []
    for rid, entries in ops.items():
        if not isinstance(entries, list):
            continue
        for row in entries:
            if str(row.get("operator_party")) != str(party):
                continue
            pub = operator_record_public(world, row)
            pub["region_id"] = str(rid)
            out.append(pub)
    return out


def is_registered_grid_operator(
    world: World, provider: PartyId, region_id: str, *, active_only: bool = True
) -> bool:
    ops = ensure_grid_operators_initialised(world)
    for row in ops.get(region_id, []) or []:
        if str(row.get("operator_party")) != str(provider):
            continue
        if active_only and row.get("status") != "active":
            continue
        return True
    return False


def _default_max_wh(capacity_wh: int) -> int:
    return max(5_000, min(capacity_wh, capacity_wh // 3 + 10_000))


def register_grid_operator(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    *,
    rate_cents_per_kwh: int,
    min_wh_per_day: int = 0,
    max_wh_per_day: int | None = None,
    skip_fee: bool = False,
    skip_business_check: bool = False,
    skip_road_check: bool = False,
) -> ActionResult:
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    if party not in world.parties:
        return {"ok": False, "reason": "unknown party"}

    if not skip_business_check and str(party) not in world.business_registry:
        return {
            "ok": False,
            "reason": "register a business name in the Registry before applying for a grid franchise",
        }

    if not skip_road_check and not is_road_accessible(world, plot_id):
        return {
            "ok": False,
            "reason": "power shed plot must be road-accessible to register as a grid operator",
        }

    rid = region_id_for_plot(world, plot_id)
    if rid is None:
        return {"ok": False, "reason": "plot is not on a road-linked grid region"}

    shed_iid, cap = _active_power_shed_on_plot(world, party, plot_id)
    if shed_iid is None or cap <= 0:
        return {
            "ok": False,
            "reason": "plot needs an active, maintained power_shed you operate",
        }

    if rate_cents_per_kwh < POWER_PRICE_FLOOR_CENTS or rate_cents_per_kwh > POWER_PRICE_CEILING_CENTS:
        return {
            "ok": False,
            "reason": (
                f"rate must be between {POWER_PRICE_FLOOR_CENTS} and "
                f"{POWER_PRICE_CEILING_CENTS} ¢/kWh"
            ),
        }

    max_wh = int(max_wh_per_day if max_wh_per_day is not None else _default_max_wh(cap))
    if max_wh <= 0:
        return {"ok": False, "reason": "max_wh_per_day must be positive"}
    if min_wh_per_day < 0 or min_wh_per_day > max_wh:
        return {"ok": False, "reason": "min_wh_per_day out of range"}

    ops = ensure_grid_operators_initialised(world)
    entries: list[dict[str, Any]] = ops.setdefault(rid, [])
    for row in entries:
        if str(row.get("operator_party")) == str(party) and str(row.get("operator_plot")) == str(plot_id):
            if row.get("status") == "active":
                return {"ok": False, "reason": "already registered on this plot for this region"}
            row["status"] = "active"
            row.pop("suspend_reason", None)
            row["rate_cents_per_kwh"] = int(rate_cents_per_kwh)
            row["min_wh_per_day"] = int(min_wh_per_day)
            row["max_wh_per_day"] = max_wh
            row["shed_instance_id"] = shed_iid
            return {
                "ok": True,
                "region_id": rid,
                "operator_plot": str(plot_id),
                "reactivated": True,
            }

    if not skip_fee:
        cash = party_cash_account(party)
        world.ledger.ensure_account(cash)
        if world.ledger.balance(cash) < GRID_UTILITY_FRANCHISE_FEE_CENTS:
            return {"ok": False, "reason": "insufficient cash for grid franchise fee"}
        tr = world.ledger.transfer(
            debit=cash,
            credit=system_reserve_account(),
            amount_cents=GRID_UTILITY_FRANCHISE_FEE_CENTS,
        )
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}

    biz = world.business_registry.get(str(party))
    biz_name = biz.business_name if biz is not None else str(party)
    record = {
        "operator_party": str(party),
        "operator_plot": str(plot_id),
        "region_id": rid,
        "shed_instance_id": shed_iid,
        "business_name": biz_name,
        "rate_cents_per_kwh": int(rate_cents_per_kwh),
        "min_wh_per_day": int(min_wh_per_day),
        "max_wh_per_day": max_wh,
        "registered_at_tick": int(world.tick),
        "status": "active",
    }
    entries.append(record)
    log_event(
        world,
        "grid_operator_registered",
        (
            f"{party} registered grid utility franchise on {plot_id} "
            f"({rid}) at {rate_cents_per_kwh}¢/kWh"
        ),
        party=str(party),
        plot_id=str(plot_id),
        region_id=rid,
    )
    return {
        "ok": True,
        "region_id": rid,
        "operator_plot": str(plot_id),
        "rate_cents_per_kwh": int(rate_cents_per_kwh),
        "fee_cents": 0 if skip_fee else GRID_UTILITY_FRANCHISE_FEE_CENTS,
    }


def seed_grid_operator(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    *,
    rate_cents_per_kwh: int | None = None,
) -> ActionResult:
    """Bootstrap NPC / town operators without franchise fee or business check."""
    rid = region_id_for_plot(world, plot_id)
    if rid is None:
        return {"ok": False, "reason": "plot not on grid region"}
    regions = compute_grid_regions(world)
    reg = regions.get(rid)
    clearing = int(reg.clearing_price_cents) if reg else POWER_PRICE_FLOOR_CENTS
    rate = int(rate_cents_per_kwh if rate_cents_per_kwh is not None else clearing)
    return register_grid_operator(
        world,
        party,
        plot_id,
        rate_cents_per_kwh=rate,
        skip_fee=True,
        skip_business_check=True,
        skip_road_check=True,
    )


def update_grid_operator_tariff(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    *,
    rate_cents_per_kwh: int | None = None,
    min_wh_per_day: int | None = None,
    max_wh_per_day: int | None = None,
) -> ActionResult:
    rid = region_id_for_plot(world, plot_id)
    if rid is None:
        return {"ok": False, "reason": "plot not on a grid region"}
    ops = ensure_grid_operators_initialised(world)
    for row in ops.get(rid, []) or []:
        if str(row.get("operator_party")) != str(party):
            continue
        if str(row.get("operator_plot")) != str(plot_id):
            continue
        if row.get("status") != "active":
            return {"ok": False, "reason": "operator registration is not active"}
        if rate_cents_per_kwh is not None:
            if (
                rate_cents_per_kwh < POWER_PRICE_FLOOR_CENTS
                or rate_cents_per_kwh > POWER_PRICE_CEILING_CENTS
            ):
                return {"ok": False, "reason": "rate out of allowed range"}
            row["rate_cents_per_kwh"] = int(rate_cents_per_kwh)
        if min_wh_per_day is not None:
            row["min_wh_per_day"] = int(min_wh_per_day)
        if max_wh_per_day is not None:
            row["max_wh_per_day"] = int(max_wh_per_day)
        if int(row.get("min_wh_per_day", 0)) > int(row.get("max_wh_per_day", 0)):
            return {"ok": False, "reason": "min_wh_per_day exceeds max_wh_per_day"}
        return {"ok": True, "region_id": rid, "operator_plot": str(plot_id)}
    return {"ok": False, "reason": "no grid operator registration on this plot"}


def unregister_grid_operator(
    world: World, party: PartyId, plot_id: PlotId
) -> ActionResult:
    rid = region_id_for_plot(world, plot_id)
    if rid is None:
        return {"ok": False, "reason": "plot not on a grid region"}
    ops = ensure_grid_operators_initialised(world)
    for row in ops.get(rid, []) or []:
        if str(row.get("operator_party")) != str(party):
            continue
        if str(row.get("operator_plot")) != str(plot_id):
            continue
        row["status"] = "cancelled"
        row["cancelled_tick"] = int(world.tick)
        log_event(
            world,
            "grid_operator_unregistered",
            f"{party} cancelled grid franchise on {plot_id}",
            party=str(party),
            plot_id=str(plot_id),
        )
        return {"ok": True, "region_id": rid}
    return {"ok": False, "reason": "no registration found on this plot"}


def get_operator_tariff(
    world: World, provider: PartyId, region_id: str, plot_id: PlotId | None = None
) -> dict[str, Any] | None:
    ops = ensure_grid_operators_initialised(world)
    for row in ops.get(region_id, []) or []:
        if str(row.get("operator_party")) != str(provider):
            continue
        if row.get("status") != "active":
            continue
        if plot_id is not None and str(row.get("operator_plot")) != str(plot_id):
            continue
        return row
    return None


def tick_grid_operators(world: World) -> None:
    """Suspend franchises when the shed is offline or plot loses road access."""
    ops = ensure_grid_operators_initialised(world)
    for _rid, entries in ops.items():
        if not isinstance(entries, list):
            continue
        for row in entries:
            party = PartyId(str(row.get("operator_party", "")))
            plot_id = PlotId(str(row.get("operator_plot", "")))
            shed_iid, cap = _active_power_shed_on_plot(world, party, plot_id)
            road_ok = is_road_accessible(world, plot_id)
            if row.get("status") == "suspended":
                if road_ok and shed_iid is not None and cap > 0:
                    row["status"] = "active"
                    row.pop("suspend_reason", None)
                    row["shed_instance_id"] = shed_iid
                    row["max_wh_per_day"] = min(
                        int(row.get("max_wh_per_day", cap)), _default_max_wh(cap)
                    )
                continue
            if row.get("status") != "active":
                continue
            if not road_ok:
                row["status"] = "suspended"
                row["suspend_reason"] = "operator plot not road-accessible"
                continue
            if shed_iid is None or cap <= 0:
                row["status"] = "suspended"
                row["suspend_reason"] = "power shed offline or unmaintained"
                continue
            row["shed_instance_id"] = shed_iid
            row["max_wh_per_day"] = min(int(row.get("max_wh_per_day", cap)), _default_max_wh(cap))


def grid_operators_public(world: World) -> list[dict[str, Any]]:
    return list_grid_operators(world, active_only=False)


def eligible_franchise_plots(world: World, party: PartyId) -> list[dict[str, Any]]:
    """Plots where party could register as grid operator (for Registry UI)."""
    out: list[dict[str, Any]] = []
    registered = {
        (str(r.get("region_id")), str(r.get("operator_plot")))
        for r in list_party_grid_operators(world, party)
        if r.get("status") == "active"
    }
    for pid, plot in world.plots.items():
        if plot.owner != party:
            continue
        rid = region_id_for_plot(world, PlotId(str(pid)))
        if rid is None:
            continue
        if not is_road_accessible(world, PlotId(str(pid))):
            continue
        shed_iid, cap = _active_power_shed_on_plot(world, party, PlotId(str(pid)))
        if shed_iid is None:
            continue
        out.append(
            {
                "plot_id": str(pid),
                "region_id": rid,
                "shed_instance_id": shed_iid,
                "capacity_kwh_per_day": round(cap / 1000, 1),
                "already_registered": (rid, str(pid)) in registered,
            }
        )
    return out
