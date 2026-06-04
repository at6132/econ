"""Register custom factories (new products + machines + blueprint)."""

from __future__ import annotations

from typing import Any

from realm.actions._shared import ActionResult
from realm.core.ids import PartyId
from realm.production.factory_design import (
    design_custom_factory,
    factory_design_public,
    machines_catalog_for_party,
)
from realm.world import World


def machines_catalog_action(world: World, party: PartyId) -> dict[str, Any]:
    return {"machines": machines_catalog_for_party(world, party)}


def design_factory_action(world: World, party: PartyId, body: dict[str, Any]) -> ActionResult:
    products_raw = body.get("new_products") or []
    products: list[dict[str, Any]] = [
        dict(x) for x in products_raw if isinstance(x, dict)
    ]
    inputs_raw = body.get("process_inputs") or body.get("inputs") or {}
    outputs_raw = body.get("process_outputs") or body.get("outputs") or {}
    inputs = (
        {str(k): int(v) for k, v in inputs_raw.items()}
        if isinstance(inputs_raw, dict)
        else {}
    )
    outputs = (
        {str(k): int(v) for k, v in outputs_raw.items()}
        if isinstance(outputs_raw, dict)
        else {}
    )
    machines_raw = body.get("installed_machines") or {}
    machines = (
        {str(k): int(v) for k, v in machines_raw.items()}
        if isinstance(machines_raw, dict)
        else {}
    )
    constr_raw = body.get("construction_materials") or {}
    constr = (
        {str(k): int(v) for k, v in constr_raw.items()}
        if isinstance(constr_raw, dict)
        else {}
    )
    maint_raw = body.get("maintenance_materials") or {}
    maint = (
        {str(k): int(v) for k, v in maint_raw.items()}
        if isinstance(maint_raw, dict)
        else {}
    )
    return design_custom_factory(
        world,
        party,
        name=str(body.get("name", "")),
        description=str(body.get("description", "")),
        footprint_w=int(body.get("footprint_w", 3)),
        footprint_h=int(body.get("footprint_h", 2)),
        category=str(body.get("category", "processing")),
        construction_materials=constr,
        construction_labor_cents=int(body.get("construction_labor_cents", 0)),
        construction_ticks=int(body.get("construction_ticks", 1440)),
        maintenance_interval_ticks=int(body.get("maintenance_interval_ticks", 14_400)),
        maintenance_materials=maint,
        maintenance_grace_ticks=int(body.get("maintenance_grace_ticks", 1440)),
        is_public=bool(body.get("is_public", False)),
        license_fee_cents=int(body.get("license_fee_cents", 0)),
        terrain_requirements=list(body.get("terrain_requirements") or []),
        requires_coastal=bool(body.get("requires_coastal", False)),
        requires_power=bool(body.get("requires_power", False)),
        installed_machines=machines,
        process_name=str(body.get("process_name", "")),
        process_inputs=inputs,
        process_outputs=outputs,
        process_duration_ticks=int(body.get("process_duration_ticks", 1440)),
        process_labor_cents=int(body.get("process_labor_cents", 500)),
        new_products=products,
    )


def factory_design_for_blueprint(
    world: World, blueprint_id: str
) -> dict[str, Any] | None:
    return factory_design_public(world, blueprint_id)
