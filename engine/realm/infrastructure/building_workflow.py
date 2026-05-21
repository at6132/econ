"""Player production routing + warehouse replenish rules (solo scenario_state)."""

from __future__ import annotations

from typing import Any

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.world import World

WORKFLOW_KEY = "player_workflows"


def _party_store(world: World, party: PartyId) -> dict[str, Any]:
    root = world.scenario_state.setdefault(WORKFLOW_KEY, {})
    if not isinstance(root, dict):
        root = {}
        world.scenario_state[WORKFLOW_KEY] = root
    party_s = str(party)
    store = root.get(party_s)
    if not isinstance(store, dict):
        store = {"building_routing": {}, "warehouse_replenish": {}}
        root[party_s] = store
    store.setdefault("building_routing", {})
    store.setdefault("warehouse_replenish", {})
    return store


def _owns_building(world: World, party: PartyId, instance_id: str) -> bool:
    pb = world.placed_buildings.get(instance_id)
    if pb is None:
        return False
    return str(pb.built_by) == str(party)


def _owns_plot(world: World, party: PartyId, plot_id: PlotId) -> bool:
    plot = world.plots.get(plot_id)
    if plot is None:
        return False
    return str(plot.owner) == str(party)


def workflow_public_dict(world: World, party: PartyId) -> dict[str, Any]:
    """Snapshot for ``/world/player`` and GET /workflow."""
    store = _party_store(world, party)
    return {
        "building_routing": dict(store.get("building_routing") or {}),
        "warehouse_replenish": dict(store.get("warehouse_replenish") or {}),
    }


def get_building_routing(
    world: World, party: PartyId, instance_id: str
) -> dict[str, Any]:
    if not _owns_building(world, party, instance_id):
        return {"ok": False, "reason": "not your building"}
    store = _party_store(world, party)
    routing = (store.get("building_routing") or {}).get(instance_id) or {}
    return {
        "ok": True,
        "instance_id": instance_id,
        "input": dict(routing.get("input") or {}),
        "output": dict(routing.get("output") or {}),
    }


def set_building_routing(
    world: World,
    party: PartyId,
    instance_id: str,
    input_routes: dict[str, str],
    output_routes: dict[str, str],
) -> dict[str, Any]:
    if not _owns_building(world, party, instance_id):
        return {"ok": False, "reason": "not your building"}
    store = _party_store(world, party)
    br = store.setdefault("building_routing", {})
    br[instance_id] = {
        "input": {str(k): str(v) for k, v in input_routes.items()},
        "output": {str(k): str(v) for k, v in output_routes.items()},
    }
    return {"ok": True, "instance_id": instance_id}


def get_warehouse_rule(
    world: World, party: PartyId, plot_id: PlotId, material: str
) -> dict[str, Any]:
    if not _owns_plot(world, party, plot_id):
        return {"ok": False, "reason": "not your plot"}
    store = _party_store(world, party)
    wr = store.get("warehouse_replenish") or {}
    key = f"{plot_id}/{material}"
    rule = wr.get(key) or {}
    return {
        "ok": True,
        "plot_id": str(plot_id),
        "material": material,
        "enabled": bool(rule.get("enabled", False)),
        "target_qty": int(rule.get("target_qty", 0)),
        "max_price_cents": int(rule.get("max_price_cents", 0)),
    }


def set_warehouse_rule(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    material: str,
    *,
    enabled: bool,
    target_qty: int,
    max_price_cents: int,
) -> dict[str, Any]:
    if not _owns_plot(world, party, plot_id):
        return {"ok": False, "reason": "not your plot"}
    if target_qty < 0 or max_price_cents < 0:
        return {"ok": False, "reason": "qty and price must be non-negative"}
    store = _party_store(world, party)
    wr = store.setdefault("warehouse_replenish", {})
    key = f"{plot_id}/{material}"
    wr[key] = {
        "enabled": enabled,
        "target_qty": int(target_qty),
        "max_price_cents": int(max_price_cents),
    }
    return {"ok": True, "plot_id": str(plot_id), "material": material}
