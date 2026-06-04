"""Custom factory design — new products, machine installs, realistic process physics."""

from __future__ import annotations

from typing import Any, Final

from realm.actions._shared import ActionResult
from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event
from realm.materials import MATERIALS, MaterialDef
from realm.production.custom_content import (
    create_custom_recipe,
    custom_recipes_store,
    material_exists,
    register_custom_material,
)
from realm.research.capabilities import party_has_capability
from realm.world import World, ensure_party_recipe_book

_FACTORY_DESIGNS_KEY: Final[str] = "factory_designs"

# Installable equipment: must be discovered (recipe book) and supplied at build time.
INSTALLABLE_MACHINES: Final[dict[str, dict[str, Any]]] = {
    "pump_unit": {
        "label": "Pump line",
        "discovery_recipes": ("make_pump_unit", "electric_pump"),
        "mass_kg": 22.0,
    },
    "gear_set": {
        "label": "Gear train",
        "discovery_recipes": ("make_gear_set",),
        "mass_kg": 8.5,
    },
    "drill_bit": {
        "label": "Drill head",
        "discovery_recipes": ("forge_drill_bit",),
        "mass_kg": 1.2,
    },
    "control_module": {
        "label": "Control module",
        "discovery_recipes": ("automated_factory",),
        "mass_kg": 2.2,
    },
    "vacuum_tube": {
        "label": "Vacuum tube rack",
        "discovery_recipes": ("radio_broadcast",),
        "mass_kg": 0.4,
    },
    "transistor": {
        "label": "Transistor bench",
        "discovery_recipes": ("semiconductor_fab",),
        "mass_kg": 0.05,
    },
}

DEFAULT_CUSTOM_MASS_KG: Final[float] = 400.0
MAX_OUTPUT_TYPES: Final[int] = 4
MASS_BALANCE_MIN_RATIO: Final[float] = 0.35
MASS_BALANCE_MAX_YIELD: Final[float] = 1.15


def _factory_designs(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault(_FACTORY_DESIGNS_KEY, {})
    if not isinstance(raw, dict):
        world.scenario_state[_FACTORY_DESIGNS_KEY] = {}
        raw = world.scenario_state[_FACTORY_DESIGNS_KEY]
    return raw  # type: ignore[return-value]


def get_factory_design(world: World, blueprint_id: str) -> dict[str, Any] | None:
    row = _factory_designs(world).get(str(blueprint_id))
    return dict(row) if isinstance(row, dict) else None


def _material_mass_kg(world: World, material_id: str) -> float:
    mid = MaterialId(str(material_id))
    if mid in MATERIALS:
        return float(MATERIALS[mid].mass_per_unit_kg)
    row = world.scenario_state.get("custom_materials", {}).get(str(material_id))
    if isinstance(row, dict):
        return float(row.get("mass_per_unit_kg", DEFAULT_CUSTOM_MASS_KG))
    return DEFAULT_CUSTOM_MASS_KG


def _party_discovered_machine(world: World, party: PartyId, machine_id: str) -> bool:
    spec = INSTALLABLE_MACHINES.get(str(machine_id))
    if spec is None:
        return False
    book = world.party_recipe_books.get(str(party), set())
    for rid in spec.get("discovery_recipes", ()):
        if str(rid) in book:
            return True
    return False


def machines_catalog_for_party(world: World, party: PartyId) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for mid, spec in INSTALLABLE_MACHINES.items():
        out.append(
            {
                "machine_id": mid,
                "label": str(spec["label"]),
                "discovered": _party_discovered_machine(world, party, mid),
                "on_hand": int(world.inventory.qty(party, MaterialId(mid))),
                "mass_kg": float(spec["mass_kg"]),
            }
        )
    return out


def _validate_machines(
    world: World, party: PartyId, installed: dict[str, int]
) -> str | None:
    if not installed:
        return "install at least one machine (pump, gears, control module, …)"
    total_units = 0
    for mid, qty in installed.items():
        q = int(qty)
        if q <= 0:
            continue
        if mid not in INSTALLABLE_MACHINES:
            return f"unknown machine type '{mid}'"
        if not _party_discovered_machine(world, party, mid):
            return (
                f"machine '{mid}' not discovered — build or research the "
                f"component line first"
            )
        on_hand = int(world.inventory.qty(party, MaterialId(mid)))
        if on_hand < q:
            return f"need {q}× {mid} in inventory (have {on_hand})"
        total_units += q
    if total_units < 1:
        return "install at least one machine unit"
    return None


def _validate_process_physics(
    world: World,
    inputs: dict[str, int],
    outputs: dict[str, int],
    *,
    require_novel_output: bool,
) -> str | None:
    if not outputs:
        return "process must produce at least one output"
    if len(outputs) > MAX_OUTPUT_TYPES:
        return f"at most {MAX_OUTPUT_TYPES} output materials per process"
    in_mass = sum(_material_mass_kg(world, m) * int(q) for m, q in inputs.items())
    out_mass = sum(_material_mass_kg(world, m) * int(q) for m, q in outputs.items())
    if out_mass <= 0:
        return "output mass must be positive"
    if in_mass <= 0 and MaterialId("electricity") not in {
        MaterialId(str(k)) for k in inputs
    }:
        return "inputs must include matter and/or grid power (electricity)"
    if in_mass > 0 and out_mass > in_mass * MASS_BALANCE_MAX_YIELD:
        return (
            "output mass exceeds realistic yield from inputs — "
            "add more feedstock or reduce batch size"
        )
    if in_mass > 0 and out_mass < in_mass * MASS_BALANCE_MIN_RATIO:
        return "output too small relative to inputs — adjust batch balance"
    if require_novel_output and not any(str(mid) not in MATERIALS for mid in outputs):
        return (
            "factory must introduce a new product — register a new material "
            "on the Process tab (not only catalog goods)"
        )
    return None


def _register_new_products(
    world: World,
    party: PartyId,
    products: list[dict[str, Any]],
) -> ActionResult | dict[str, str]:
    """Returns map output_slot → material_id or error ActionResult."""
    id_map: dict[str, str] = {}
    for row in products:
        if not isinstance(row, dict):
            continue
        slot = str(row.get("slot", row.get("material_id", "")))
        display = str(row.get("display_name", "")).strip()
        mat_id = str(row.get("material_id", "")).strip()
        category = str(row.get("category", "processed"))
        mass = float(row.get("mass_per_unit_kg", DEFAULT_CUSTOM_MASS_KG))
        if display and not mat_id:
            reg = register_custom_material(
                world,
                party,
                display,
                category=category,
                material_id="",
            )
            if not reg.get("ok"):
                return reg  # type: ignore[return-value]
            mat_id = str(reg["material_id"])
            mats = world.scenario_state.setdefault("custom_materials", {})
            if isinstance(mats.get(mat_id), dict):
                mats[mat_id]["mass_per_unit_kg"] = mass
        elif mat_id:
            if not material_exists(world, mat_id):
                reg = register_custom_material(
                    world,
                    party,
                    display or mat_id,
                    category=category,
                    material_id=mat_id,
                )
                if not reg.get("ok"):
                    return reg  # type: ignore[return-value]
            mats = world.scenario_state.setdefault("custom_materials", {})
            if isinstance(mats.get(mat_id), dict):
                mats[mat_id]["mass_per_unit_kg"] = mass
        else:
            continue
        if slot:
            id_map[slot] = mat_id
        id_map[mat_id] = mat_id
    return id_map


def design_custom_factory(
    world: World,
    party: PartyId,
    *,
    name: str,
    description: str,
    footprint_w: int,
    footprint_h: int,
    category: str,
    construction_materials: dict[str, int],
    construction_labor_cents: int,
    construction_ticks: int,
    maintenance_interval_ticks: int,
    maintenance_materials: dict[str, int],
    maintenance_grace_ticks: int,
    is_public: bool,
    license_fee_cents: int,
    terrain_requirements: list[str],
    requires_coastal: bool,
    requires_power: bool,
    installed_machines: dict[str, int],
    process_name: str,
    process_inputs: dict[str, int],
    process_outputs: dict[str, int],
    process_duration_ticks: int,
    process_labor_cents: int,
    new_products: list[dict[str, Any]],
) -> ActionResult:
    """One-shot: new matter (optional) + process + blueprint bound to installed machines."""
    from realm.research.fabrication import (
        validate_blueprint_public_license,
        validate_blueprint_registration,
        validate_custom_recipe_creation,
    )

    if not party_has_capability(world, party, "custom_blueprint"):
        return {
            "ok": False,
            "reason": "custom factories locked — research Workshop engineering",
        }
    cap_err = validate_custom_recipe_creation(world, party)
    if cap_err:
        return {"ok": False, "reason": cap_err}
    lic_err = validate_blueprint_public_license(world, party, is_public)
    if lic_err:
        return {"ok": False, "reason": lic_err}
    mach_err = _validate_machines(world, party, installed_machines)
    if mach_err:
        return {"ok": False, "reason": mach_err}

    reg_products = _register_new_products(world, party, new_products)
    if isinstance(reg_products, dict) and reg_products.get("ok") is False:
        return reg_products  # type: ignore[return-value]

    outputs = {str(k): int(v) for k, v in process_outputs.items()}
    for row in new_products:
        if not isinstance(row, dict):
            continue
        slot = str(row.get("output_slot", ""))
        if slot and slot in outputs and isinstance(reg_products, dict):
            mid = reg_products.get(slot)
            if mid:
                outputs[mid] = outputs.pop(slot, outputs.get(mid, 1))

    inputs = {str(k): int(v) for k, v in process_inputs.items()}
    phys = _validate_process_physics(
        world,
        inputs,
        outputs,
        require_novel_output=True,
    )
    if phys:
        return {"ok": False, "reason": phys}

    if process_duration_ticks < TICKS_PER_GAME_DAY // 4:
        return {"ok": False, "reason": "process duration too short for a factory line"}
    if not process_name.strip():
        return {"ok": False, "reason": "process name required"}

    from realm.actions.blueprint_actions import create_blueprint

    recipe_row = create_custom_recipe(
        world,
        party,
        process_name.strip(),
        inputs,
        outputs,
        int(process_duration_ticks),
        int(process_labor_cents),
        "",
        is_public=False,
    )
    if not recipe_row.get("ok"):
        return recipe_row  # type: ignore[return-value]
    recipe_id = str(recipe_row["recipe_id"])

    reg_err = validate_blueprint_registration(
        world,
        party,
        footprint_w,
        footprint_h,
        [recipe_id],
    )
    if reg_err:
        custom_recipes_store(world).pop(recipe_id, None)
        book = world.party_recipe_books.get(str(party), set())
        book.discard(recipe_id)
        return {"ok": False, "reason": reg_err}

    bp_result = create_blueprint(
        world,
        party,
        name.strip(),
        description.strip(),
        int(footprint_w),
        int(footprint_h),
        {str(k): int(v) for k, v in construction_materials.items()},
        int(construction_labor_cents),
        int(construction_ticks),
        [recipe_id],
        int(maintenance_interval_ticks),
        {str(k): int(v) for k, v in maintenance_materials.items()},
        int(maintenance_grace_ticks),
        bool(is_public),
        int(license_fee_cents),
        str(category or "processing"),
        list(terrain_requirements),
        bool(requires_coastal),
        bool(requires_power),
    )
    if not bp_result.get("ok"):
        custom_recipes_store(world).pop(recipe_id, None)
        return bp_result

    blueprint_id = str(bp_result["blueprint_id"])
    store = custom_recipes_store(world).get(recipe_id)
    if isinstance(store, dict):
        store["requires_building_id"] = blueprint_id

    clean_machines = {
        str(k): int(v)
        for k, v in installed_machines.items()
        if str(k) in INSTALLABLE_MACHINES and int(v) > 0
    }
    _factory_designs(world)[blueprint_id] = {
        "creator_party": str(party),
        "recipe_id": recipe_id,
        "installed_machines": clean_machines,
        "outputs": {str(k): int(v) for k, v in outputs.items()},
        "inputs": inputs,
        "process_name": process_name.strip(),
    }

    log_event(
        world,
        "world_feed",
        f"FACTORY DESIGNED: {party} registered '{name}' producing "
        f"{', '.join(outputs.keys())} — machines installed.",
        feed_source="factory_design",
        party=str(party),
        blueprint_id=blueprint_id,
        recipe_id=recipe_id,
    )
    return {
        "ok": True,
        "blueprint_id": blueprint_id,
        "recipe_id": recipe_id,
        "outputs": outputs,
        "installed_machines": clean_machines,
        "registration_fee_cents": bp_result.get("registration_fee_cents"),
    }


def consume_factory_machines_on_build(
    world: World, party: PartyId, blueprint_id: str
) -> ActionResult:
    """Remove installed machine components from inventory when construction starts."""
    fd = get_factory_design(world, blueprint_id)
    if fd is None:
        return {"ok": True, "skipped": True}
    for mid, qty in (fd.get("installed_machines") or {}).items():
        q = int(qty)
        if q <= 0:
            continue
        rm = world.inventory.remove(party, MaterialId(str(mid)), q)
        if isinstance(rm, MatterErr):
            return {"ok": False, "reason": f"missing installed machine {mid}: {rm.reason}"}
    log_event(
        world,
        "factory_machines_installed",
        f"{party} installed machines into {blueprint_id}",
        party=str(party),
        blueprint_id=str(blueprint_id),
    )
    return {"ok": True}


def factory_design_public(world: World, blueprint_id: str) -> dict[str, Any] | None:
    fd = get_factory_design(world, blueprint_id)
    if fd is None:
        return None
    return {
        "blueprint_id": str(blueprint_id),
        "recipe_id": str(fd.get("recipe_id", "")),
        "process_name": str(fd.get("process_name", "")),
        "inputs": dict(fd.get("inputs") or {}),
        "outputs": dict(fd.get("outputs") or {}),
        "installed_machines": dict(fd.get("installed_machines") or {}),
    }
