"""Grid utility — per-plot contracts, provider tariffs, and supply routing."""

from __future__ import annotations

from typing import Any, Literal

from realm.actions._shared import ActionResult
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.events.event_log import log_event
from realm.infrastructure.energy_service import BATTERY_BLUEPRINT_IDS, BATTERY_CAPACITY_WH
from realm.infrastructure.grid_operators import (
    get_operator_tariff,
    is_registered_grid_operator,
    list_grid_operators,
)
from realm.infrastructure.power_grid import (
    POWER_GENERATOR_BLUEPRINTS,
    POWER_PRICE_CEILING_CENTS,
    POWER_PRICE_FLOOR_CENTS,
    GridRegion,
    _build_plot_region_map,
    _generator_owner_and_capacity,
    compute_grid_regions,
    plot_has_grid_capacity,
)
from realm.world import World

PAYMENT_METHOD_PARTY_CASH: str = "party_cash"
_VALID_PAYMENT_METHODS: frozenset[str] = frozenset({PAYMENT_METHOD_PARTY_CASH})
ConnectionRole = Literal["primary", "backup", "standby"]

_UTILITY_EXEMPT_PARTY_PREFIXES: tuple[str, ...] = ("settler_", "laborer_", "npc_")
_UTILITY_EXEMPT_PARTY_IDS: frozenset[str] = frozenset(
    {
        "genesis_settlement",
        "genesis_exchange",
        "frontier_grid_co",
        "energy_central_north",
        "energy_central_south",
        "frontier_roads",
        "frontier_insurance_co",
    }
)


def _connections_bucket(world: World) -> list[dict[str, Any]]:
    raw = world.scenario_state.setdefault("grid_utility_connections", [])
    if not isinstance(raw, list):
        world.scenario_state["grid_utility_connections"] = []
        return world.scenario_state["grid_utility_connections"]
    return raw


def _config_bucket(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault("plot_utility_config", {})
    if not isinstance(raw, dict):
        world.scenario_state["plot_utility_config"] = {}
        return world.scenario_state["plot_utility_config"]
    return raw


def _config_key(party: PartyId, plot_id: PlotId) -> str:
    return f"{plot_id}|{party}"


def _next_connection_id(world: World) -> str:
    seq = int(world.scenario_state.setdefault("grid_utility_connection_seq", 0)) + 1
    world.scenario_state["grid_utility_connection_seq"] = seq
    return f"guc-{seq:05d}"


def region_id_for_plot(world: World, plot_id: PlotId) -> str | None:
    return _build_plot_region_map(compute_grid_regions(world)).get(str(plot_id))


def _party_exempt_from_utility_contract(party: PartyId) -> bool:
    s = str(party)
    if s in _UTILITY_EXEMPT_PARTY_IDS:
        return True
    return any(s.startswith(p) for p in _UTILITY_EXEMPT_PARTY_PREFIXES)


def _generator_owners_in_region(world: World, reg: GridRegion) -> dict[str, int]:
    owners: dict[str, int] = {}
    for iid in reg.generator_instance_ids:
        owner, cap = _generator_owner_and_capacity(world, iid)
        if owner is None or cap <= 0:
            continue
        key = str(owner)
        owners[key] = owners.get(key, 0) + cap
    return owners


def party_has_own_generation_in_region(
    world: World, party: PartyId, region_id: str
) -> bool:
    regions = compute_grid_regions(world)
    reg = regions.get(region_id)
    if reg is None or reg.capacity_per_day <= 0:
        return False
    owners = _generator_owners_in_region(world, reg)
    return int(owners.get(str(party), 0)) > 0


def _connection_matches_plot(row: dict[str, Any], plot_id: PlotId, region_id: str) -> bool:
    pid = str(row.get("plot_id") or "")
    if pid:
        return pid == str(plot_id)
    return str(row.get("region_id", "")) == region_id


def connections_for_plot(
    world: World, party: PartyId, plot_id: PlotId, *, active_only: bool = True
) -> list[dict[str, Any]]:
    rid = region_id_for_plot(world, plot_id)
    if rid is None:
        return []
    out: list[dict[str, Any]] = []
    for row in _connections_bucket(world):
        if str(row.get("subscriber")) != str(party):
            continue
        if active_only and row.get("status") != "active":
            continue
        if _connection_matches_plot(row, plot_id, rid):
            out.append(row)
    return out


def get_plot_utility_config(world: World, party: PartyId, plot_id: PlotId) -> dict[str, Any]:
    cfg = _config_bucket(world).get(_config_key(party, plot_id), {})
    return {
        "primary_connection_id": str(cfg.get("primary_connection_id") or ""),
        "backup_connection_ids": [
            str(x) for x in (cfg.get("backup_connection_ids") or []) if str(x)
        ],
        "battery_instance_ids": [
            str(x) for x in (cfg.get("battery_instance_ids") or []) if str(x)
        ],
    }


def utility_provider_offers_for_plot(
    world: World, party: PartyId, plot_id: PlotId
) -> list[dict[str, Any]]:
    rid = region_id_for_plot(world, plot_id)
    if rid is None:
        return []
    regions = compute_grid_regions(world)
    reg = regions.get(rid)
    if reg is None:
        return []
    owners = _generator_owners_in_region(world, reg)
    signed = {
        str(c.get("provider"))
        for c in connections_for_plot(world, party, plot_id, active_only=False)
        if c.get("status") == "active"
    }
    out: list[dict[str, Any]] = []
    for op in list_grid_operators(world, rid, active_only=True):
        owner_s = str(op.get("operator_party", ""))
        if owner_s == str(party):
            continue
        cap = int(owners.get(owner_s, 0))
        if cap <= 0:
            continue
        rate = int(op.get("rate_cents_per_kwh", 0))
        min_wh = int(op.get("min_wh_per_day", 0))
        max_wh = int(op.get("max_wh_per_day", 0))
        display = str(op.get("operator_name") or world.party_display_names.get(
            owner_s, owner_s.replace("_", " ").title()
        ))
        out.append(
            {
                "provider_party": owner_s,
                "display_name": display,
                "business_name": str(op.get("business_name") or ""),
                "operator_plot": str(op.get("operator_plot") or ""),
                "capacity_wh_per_day": cap,
                "capacity_kwh_per_day": round(cap / 1000, 1),
                "rate_cents_per_kwh": rate,
                "min_wh_per_day": min_wh,
                "max_wh_per_day": max_wh,
                "min_kwh_per_day": round(min_wh / 1000, 1),
                "max_kwh_per_day": round(max_wh / 1000, 1),
                "payment_methods": [PAYMENT_METHOD_PARTY_CASH],
                "already_connected": owner_s in signed,
            }
        )
    out.sort(key=lambda x: (x["rate_cents_per_kwh"], x["provider_party"]))
    return out


def build_utility_contract_text(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    provider_party: PartyId,
    *,
    rate_cents_per_kwh: int,
    min_wh_per_day: int,
    max_wh_per_day: int,
    payment_method: str,
) -> str:
    provider_name = world.party_display_names.get(
        str(provider_party), str(provider_party)
    )
    subscriber_name = world.party_display_names.get(str(party), str(party))
    rid = region_id_for_plot(world, plot_id) or "unknown"
    tick = int(world.tick)
    return (
        f"GRID POWER SUPPLY AGREEMENT\n"
        f"Contract reference: pending signature at tick {tick}\n\n"
        f"Provider: {provider_name} ({provider_party})\n"
        f"Subscriber: {subscriber_name} ({party})\n"
        f"Service location (plot): {plot_id}\n"
        f"Grid region: {rid}\n\n"
        f"1. Service. Provider agrees to make wholesale grid energy available to "
        f"Subscriber at the service location, subject to regional generation capacity "
        f"and maintenance status.\n"
        f"2. Rate. Subscriber pays {rate_cents_per_kwh} cents (USD) per kWh drawn "
        f"under this agreement, settled on each game-day grid clearing.\n"
        f"3. Usage band. Minimum daily draw (if any): {min_wh_per_day / 1000:.1f} kWh. "
        f"Maximum contracted draw: {max_wh_per_day / 1000:.1f} kWh per game-day.\n"
        f"4. Payment. Charges debit Subscriber's {payment_method} account automatically. "
        f"Insufficient funds may curtail service without breaching conservation rules.\n"
        f"5. Term. Agreement remains active until cancelled by Subscriber or suspended "
        f"if Provider loses generation in the region.\n"
        f"6. Priority. Subscriber may designate this agreement as primary, backup, or "
        f"standby supply in the plot electricity control panel.\n\n"
        f"By accepting, Subscriber authorizes automatic billing and confirms the plot "
        f"above is authorized to draw from Provider's regional contribution."
    )


def preview_utility_contract(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    provider_party: PartyId,
) -> ActionResult:
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    rid = region_id_for_plot(world, plot_id)
    if rid is None:
        return {"ok": False, "reason": "plot is not on a grid region"}
    owners = _generator_owners_in_region(world, compute_grid_regions(world)[rid])
    if str(provider_party) not in owners:
        return {"ok": False, "reason": "provider has no active generator in this region"}
    op = get_operator_tariff(world, provider_party, rid)
    if op is None:
        return {
            "ok": False,
            "reason": "provider is not a registered grid utility operator in this region",
        }
    cap = int(owners[str(provider_party)])
    tariff = {
        "rate_cents_per_kwh": int(op.get("rate_cents_per_kwh", 0)),
        "min_wh_per_day": int(op.get("min_wh_per_day", 0)),
        "max_wh_per_day": int(op.get("max_wh_per_day", 0)),
    }
    rate = int(tariff["rate_cents_per_kwh"])
    text = build_utility_contract_text(
        world,
        party,
        plot_id,
        provider_party,
        rate_cents_per_kwh=rate,
        min_wh_per_day=int(tariff["min_wh_per_day"]),
        max_wh_per_day=int(tariff["max_wh_per_day"]),
        payment_method=PAYMENT_METHOD_PARTY_CASH,
    )
    return {
        "ok": True,
        "contract_text": text,
        "rate_cents_per_kwh": rate,
        "min_wh_per_day": int(tariff["min_wh_per_day"]),
        "max_wh_per_day": int(tariff["max_wh_per_day"]),
        "payment_method": PAYMENT_METHOD_PARTY_CASH,
        "provider": str(provider_party),
        "plot_id": str(plot_id),
    }


def _connection_public(world: World, row: dict[str, Any]) -> dict[str, Any]:
    provider = str(row.get("provider", ""))
    return {
        "connection_id": str(row.get("id", "")),
        "plot_id": str(row.get("plot_id") or ""),
        "provider": provider,
        "provider_name": world.party_display_names.get(provider, provider),
        "role": str(row.get("role") or "standby"),
        "rate_cents_per_kwh": int(row.get("rate_cents_per_kwh", 0)),
        "min_wh_per_day": int(row.get("min_wh_per_day", 0)),
        "max_wh_per_day": int(row.get("max_wh_per_day", 0)),
        "payment_method": str(row.get("payment_method", "")),
        "status": str(row.get("status", "")),
        "signed_tick": int(row.get("signed_tick", 0)),
        "contract_text": str(row.get("contract_text") or ""),
    }


def resolve_billing_connection_for_plot(
    world: World, party: PartyId, plot_id: PlotId
) -> dict[str, Any] | None:
    if party_has_own_generation_in_region(
        world, party, region_id_for_plot(world, plot_id) or ""
    ):
        return None
    cfg = get_plot_utility_config(world, party, plot_id)
    active = {str(c["id"]): c for c in connections_for_plot(world, party, plot_id)}
    for cid in [cfg["primary_connection_id"], *cfg["backup_connection_ids"]]:
        if cid and cid in active:
            return active[cid]
    conns = connections_for_plot(world, party, plot_id)
    return conns[0] if conns else None


def party_may_draw_grid_energy(
    world: World, party: PartyId, plot_id: PlotId
) -> tuple[bool, str | None]:
    if not plot_has_grid_capacity(world, plot_id):
        return False, "no grid capacity at this plot"
    rid = region_id_for_plot(world, plot_id)
    if rid is None:
        return False, "plot not on a powered grid region"
    if _party_exempt_from_utility_contract(party):
        return True, None
    if party_has_own_generation_in_region(world, party, rid):
        return True, None
    conn = resolve_billing_connection_for_plot(world, party, plot_id)
    if conn is None:
        return (
            False,
            "no utility contract for this plot — open Electricity and sign a provider",
        )
    if conn.get("status") != "active":
        return False, str(conn.get("suspend_reason") or "utility contract suspended")
    provider = str(conn.get("provider", ""))
    owners = _generator_owners_in_region(world, compute_grid_regions(world)[rid])
    if provider not in owners:
        return False, "utility provider no longer serves this region"
    if not is_registered_grid_operator(world, PartyId(provider), rid):
        return False, "utility provider franchise is not active"
    return True, None


def settlement_rate_for_plot_load(
    world: World, party: PartyId, plot_id: PlotId
) -> tuple[int, PartyId | None]:
    conn = resolve_billing_connection_for_plot(world, party, plot_id)
    if conn is None:
        return 0, None
    return int(conn.get("rate_cents_per_kwh", 0)), PartyId(str(conn["provider"]))


def _buildings_on_plot(world: World, plot_id: PlotId) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pb in world.placed_buildings.values():
        if str(pb.plot_id) != str(plot_id):
            continue
        rows.append(
            {
                "instance_id": pb.instance_id,
                "blueprint_id": pb.blueprint_id,
                "label": pb.blueprint_id,
                "status": str(pb.status),
                "built_by": str(pb.built_by),
            }
        )
    for row in world.plot_buildings:
        if str(row.get("plot_id", "")) != str(plot_id):
            continue
        rows.append(
            {
                "instance_id": str(row.get("instance_id", "")),
                "blueprint_id": str(row.get("building_id", "")),
                "label": str(row.get("label") or row.get("building_id", "")),
                "status": "active",
                "built_by": str(row.get("party", "")),
            }
        )
    return rows


def plot_energy_flow(world: World, party: PartyId, plot_id: PlotId) -> dict[str, Any]:
    from realm.infrastructure.energy_service import recipe_energy_wh
    from realm.production.recipes import RECIPES

    buildings = _buildings_on_plot(world, plot_id)
    sources: list[dict[str, Any]] = []
    storage: list[dict[str, Any]] = []
    consumers: list[dict[str, Any]] = []

    for b in buildings:
        bid = str(b["blueprint_id"])
        iid = str(b["instance_id"])
        if bid in POWER_GENERATOR_BLUEPRINTS:
            maint = world.building_maintenance.get(iid, {})
            eff = int(maint.get("efficiency_pct", 100))
            cap = int(POWER_GENERATOR_BLUEPRINTS.get(bid, 0) * eff / 100)
            sources.append(
                {
                    "instance_id": iid,
                    "kind": "generator",
                    "label": bid,
                    "capacity_wh_per_day": cap,
                    "owner": b["built_by"],
                    "own": str(b["built_by"]) == str(party),
                }
            )
        elif bid in BATTERY_BLUEPRINT_IDS:
            maint = world.building_maintenance.get(iid, {})
            stored = int(maint.get("stored_wh", 0))
            cap = int(BATTERY_CAPACITY_WH.get(bid, 0))
            storage.append(
                {
                    "instance_id": iid,
                    "kind": "battery",
                    "label": bid,
                    "stored_wh": stored,
                    "capacity_wh": cap,
                }
            )
        else:
            consumers.append(
                {
                    "instance_id": iid,
                    "kind": "building",
                    "label": b["label"],
                    "blueprint_id": bid,
                }
            )

    for run in world.active_production:
        if str(run.plot_id) != str(plot_id) or str(run.party) != str(party):
            continue
        recipe = RECIPES.get(str(run.recipe_id))
        if recipe is None:
            continue
        wh = recipe_energy_wh(recipe)
        if wh <= 0:
            continue
        consumers.append(
            {
                "instance_id": str(run.run_id),
                "kind": "production_run",
                "label": str(run.recipe_id),
                "draw_wh_per_batch": wh,
            }
        )

    load_today = int(
        (world.scenario_state.get("power_load_today") or {}).get(str(plot_id), 0)
    )
    cfg = get_plot_utility_config(world, party, plot_id)
    return {
        "sources": sources,
        "storage": storage,
        "consumers": consumers,
        "load_wh_today": load_today,
        "config": cfg,
    }


def grid_utility_status_for_plot(
    world: World, party: PartyId, plot_id: PlotId
) -> dict[str, Any]:
    from realm.infrastructure.power_grid import get_plot_power_info

    power = get_plot_power_info(world, plot_id)
    rid = region_id_for_plot(world, plot_id)
    own_gen = (
        party_has_own_generation_in_region(world, party, rid) if rid else False
    )
    may_draw, block_reason = party_may_draw_grid_energy(world, party, plot_id)
    offers = utility_provider_offers_for_plot(world, party, plot_id)
    connections = [
        _connection_public(world, c)
        for c in connections_for_plot(world, party, plot_id, active_only=False)
        if c.get("status") in ("active", "suspended")
    ]
    flow = plot_energy_flow(world, party, plot_id)
    cfg = get_plot_utility_config(world, party, plot_id)

    access_mode = "none"
    if not power.get("powered"):
        access_mode = "unpowered"
    elif own_gen:
        access_mode = "own_generation"
    elif any(c["status"] == "active" for c in connections):
        access_mode = "utility_contract"
    elif offers:
        access_mode = "requires_contract"
    elif may_draw:
        access_mode = "exempt"

    return {
        "ok": True,
        "plot_id": str(plot_id),
        "party": str(party),
        "region_id": rid,
        "access_mode": access_mode,
        "may_draw_grid_energy": may_draw,
        "block_reason": block_reason,
        "own_generation_in_region": own_gen,
        "provider_offers": offers,
        "connections": connections,
        "energy_flow": flow,
        "utility_config": cfg,
        "power": power,
    }


def connect_grid_utility(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    provider_party: PartyId,
    *,
    rate_cents_per_kwh: int | None = None,
    payment_method: str = PAYMENT_METHOD_PARTY_CASH,
    agreed_to_terms: bool = False,
    contract_text: str | None = None,
) -> ActionResult:
    if not agreed_to_terms:
        return {"ok": False, "reason": "must agree to contract terms before signing"}
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner is not None and plot.owner != party:
        return {"ok": False, "reason": "you do not own this plot"}
    if party not in world.parties or provider_party not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if payment_method not in _VALID_PAYMENT_METHODS:
        return {"ok": False, "reason": f"unsupported payment_method {payment_method!r}"}
    if not plot_has_grid_capacity(world, plot_id):
        return {"ok": False, "reason": "plot has no regional grid capacity"}
    rid = region_id_for_plot(world, plot_id)
    if rid is None:
        return {"ok": False, "reason": "plot is not on a grid region"}

    owners = _generator_owners_in_region(world, compute_grid_regions(world)[rid])
    if str(provider_party) not in owners:
        return {"ok": False, "reason": "provider has no active generator in this region"}
    op = get_operator_tariff(world, provider_party, rid)
    if op is None:
        return {
            "ok": False,
            "reason": "provider is not a registered grid utility operator in this region",
        }

    for row in connections_for_plot(world, party, plot_id, active_only=True):
        if str(row.get("provider")) == str(provider_party):
            return {"ok": False, "reason": "already connected to this provider on this plot"}

    tariff = {
        "rate_cents_per_kwh": int(op.get("rate_cents_per_kwh", 0)),
        "min_wh_per_day": int(op.get("min_wh_per_day", 0)),
        "max_wh_per_day": int(op.get("max_wh_per_day", 0)),
    }
    rate = int(rate_cents_per_kwh if rate_cents_per_kwh is not None else tariff["rate_cents_per_kwh"])
    if rate < POWER_PRICE_FLOOR_CENTS or rate > POWER_PRICE_CEILING_CENTS:
        return {
            "ok": False,
            "reason": (
                f"rate must be between {POWER_PRICE_FLOOR_CENTS} and "
                f"{POWER_PRICE_CEILING_CENTS} ¢/kWh"
            ),
        }

    terms = contract_text or build_utility_contract_text(
        world,
        party,
        plot_id,
        provider_party,
        rate_cents_per_kwh=rate,
        min_wh_per_day=int(tariff["min_wh_per_day"]),
        max_wh_per_day=int(tariff["max_wh_per_day"]),
        payment_method=payment_method,
    )

    world.ledger.ensure_account(party_cash_account(party))
    cid = _next_connection_id(world)
    row = {
        "id": cid,
        "plot_id": str(plot_id),
        "subscriber": str(party),
        "provider": str(provider_party),
        "region_id": rid,
        "role": "standby",
        "rate_cents_per_kwh": rate,
        "min_wh_per_day": int(tariff["min_wh_per_day"]),
        "max_wh_per_day": int(tariff["max_wh_per_day"]),
        "payment_method": payment_method,
        "status": "active",
        "signed_tick": int(world.tick),
        "contract_text": terms,
    }
    _connections_bucket(world).append(row)

    cfg_key = _config_key(party, plot_id)
    cfg = _config_bucket(world).setdefault(cfg_key, {})
    if not cfg.get("primary_connection_id"):
        cfg["primary_connection_id"] = cid
        row["role"] = "primary"

    provider_name = world.party_display_names.get(
        str(provider_party), str(provider_party)
    )
    log_event(
        world,
        "grid_utility_connect",
        f"{party} signed plot utility {cid} with {provider_name} on {plot_id}",
        party=str(party),
        plot_id=str(plot_id),
        connection_id=cid,
        provider=str(provider_party),
    )
    return {
        "ok": True,
        "connection_id": cid,
        "plot_id": str(plot_id),
        "rate_cents_per_kwh": rate,
        "contract_text": terms,
        "provider": str(provider_party),
    }


def disconnect_grid_utility(
    world: World, party: PartyId, connection_id: str
) -> ActionResult:
    for row in _connections_bucket(world):
        if str(row.get("id")) != connection_id:
            continue
        if str(row.get("subscriber")) != str(party):
            return {"ok": False, "reason": "not your utility contract"}
        if row.get("status") != "active":
            return {"ok": False, "reason": "connection is not active"}
        row["status"] = "cancelled"
        row["cancelled_tick"] = int(world.tick)
        pid = PlotId(str(row.get("plot_id") or ""))
        if pid in world.plots:
            cfg_key = _config_key(party, pid)
            cfg = _config_bucket(world).get(cfg_key, {})
            if cfg.get("primary_connection_id") == connection_id:
                cfg["primary_connection_id"] = ""
            cfg["backup_connection_ids"] = [
                x
                for x in (cfg.get("backup_connection_ids") or [])
                if str(x) != connection_id
            ]
        log_event(
            world,
            "grid_utility_disconnect",
            f"{party} cancelled grid utility {connection_id}",
            party=str(party),
            connection_id=connection_id,
        )
        return {"ok": True, "connection_id": connection_id}
    return {"ok": False, "reason": "connection not found"}


def update_plot_utility_config(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    *,
    primary_connection_id: str | None = None,
    backup_connection_ids: list[str] | None = None,
    battery_instance_ids: list[str] | None = None,
) -> ActionResult:
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner is not None and plot.owner != party:
        return {"ok": False, "reason": "you do not own this plot"}
    active_ids = {
        str(c["id"]) for c in connections_for_plot(world, party, plot_id)
    }
    cfg_key = _config_key(party, plot_id)
    cfg = _config_bucket(world).setdefault(cfg_key, {})

    if primary_connection_id is not None:
        if primary_connection_id and primary_connection_id not in active_ids:
            return {"ok": False, "reason": "primary connection not active on this plot"}
        cfg["primary_connection_id"] = primary_connection_id
        for row in _connections_bucket(world):
            if str(row.get("id")) in active_ids:
                row["role"] = (
                    "primary"
                    if str(row.get("id")) == primary_connection_id
                    else (
                        "backup"
                        if str(row.get("id"))
                        in (backup_connection_ids or cfg.get("backup_connection_ids") or [])
                        else "standby"
                    )
                )

    if backup_connection_ids is not None:
        for cid in backup_connection_ids:
            if cid not in active_ids:
                return {"ok": False, "reason": f"backup connection {cid} not on this plot"}
        cfg["backup_connection_ids"] = list(backup_connection_ids)
        primary = str(cfg.get("primary_connection_id") or "")
        for row in _connections_bucket(world):
            rid = str(row.get("id"))
            if rid not in active_ids:
                continue
            row["role"] = (
                "primary"
                if rid == primary
                else ("backup" if rid in backup_connection_ids else "standby")
            )

    if battery_instance_ids is not None:
        valid: list[str] = []
        for iid in battery_instance_ids:
            found = any(
                str(b.get("instance_id")) == iid
                and str(b.get("blueprint_id")) in BATTERY_BLUEPRINT_IDS
                for b in _buildings_on_plot(world, plot_id)
            )
            if not found:
                return {"ok": False, "reason": f"battery {iid} not on this plot"}
            valid.append(iid)
        cfg["battery_instance_ids"] = valid

    return {"ok": True, "utility_config": get_plot_utility_config(world, party, plot_id)}


def tick_grid_utility_connections(world: World) -> None:
    regions = compute_grid_regions(world)
    for row in _connections_bucket(world):
        if row.get("status") != "active":
            continue
        rid = str(row.get("region_id", ""))
        provider = str(row.get("provider", ""))
        reg = regions.get(rid)
        if reg is None or reg.capacity_per_day <= 0:
            row["status"] = "suspended"
            row["suspend_reason"] = "region has no grid capacity"
            continue
        owners = _generator_owners_in_region(world, reg)
        if provider not in owners:
            row["status"] = "suspended"
            row["suspend_reason"] = "provider offline in region"
            continue
        if not is_registered_grid_operator(world, PartyId(provider), rid):
            row["status"] = "suspended"
            row["suspend_reason"] = "provider franchise not active"
