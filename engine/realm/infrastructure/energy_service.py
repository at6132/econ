"""Grid energy as a service (Wh) — not a warehouse commodity."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.world import World

# Legacy saves/recipes used ``electricity`` inventory units; 1 unit = 1 kWh.
WH_PER_LEGACY_ELEC_UNIT: int = 1000
LEGACY_ELECTRICITY_MATERIAL: MaterialId = MaterialId("electricity")

BATTERY_BLUEPRINT_IDS: frozenset[str] = frozenset({"battery_bank"})

# Wh capacity by blueprint tier (only ``battery_bank`` in v1).
BATTERY_CAPACITY_WH: dict[str, int] = {
    "battery_bank": 50_000,  # 50 kWh
}


def is_legacy_electricity_material(material: MaterialId | str) -> bool:
    return str(material) == str(LEGACY_ELECTRICITY_MATERIAL)


def recipe_energy_wh(recipe: object) -> int:
    """Wh drawn from grid/battery for one batch of ``recipe``."""
    explicit = int(getattr(recipe, "energy_wh", 0) or 0)
    if explicit > 0:
        return explicit
    inputs = getattr(recipe, "inputs", {}) or {}
    legacy = int(inputs.get(LEGACY_ELECTRICITY_MATERIAL, 0))
    return legacy * WH_PER_LEGACY_ELEC_UNIT


def recipe_grid_export_wh(recipe: object) -> int:
    """Wh fed into the regional grid when a generator recipe completes."""
    explicit = int(getattr(recipe, "grid_export_wh", 0) or 0)
    if explicit > 0:
        return explicit
    outputs = getattr(recipe, "outputs", {}) or {}
    legacy = int(outputs.get(LEGACY_ELECTRICITY_MATERIAL, 0))
    return legacy * WH_PER_LEGACY_ELEC_UNIT


def material_inputs_excluding_energy(recipe: object) -> dict[MaterialId, int]:
    out: dict[MaterialId, int] = {}
    for mat, qty in (getattr(recipe, "inputs", {}) or {}).items():
        if is_legacy_electricity_material(mat):
            continue
        out[MaterialId(str(mat))] = int(qty)
    return out


def material_outputs_excluding_energy(recipe: object) -> dict[MaterialId, int]:
    out: dict[MaterialId, int] = {}
    for mat, qty in (getattr(recipe, "outputs", {}) or {}).items():
        if is_legacy_electricity_material(mat):
            continue
        out[MaterialId(str(mat))] = int(qty)
    return out


def _battery_stored_wh(world: World, plot_id: PlotId) -> int:
    total = 0
    for pb in world.placed_buildings.values():
        if str(pb.plot_id) != str(plot_id):
            continue
        if pb.blueprint_id not in BATTERY_BLUEPRINT_IDS:
            continue
        if str(pb.status) != "active":
            continue
        maint = world.building_maintenance.get(pb.instance_id, {})
        total += int(maint.get("stored_wh", 0))
    for row in world.plot_buildings:
        if str(row.get("plot_id", "")) != str(plot_id):
            continue
        bid = str(row.get("building_id", ""))
        if bid not in BATTERY_BLUEPRINT_IDS:
            continue
        iid = str(row.get("instance_id", ""))
        if not iid:
            continue
        if int(row.get("completes_at_tick", 0)) > int(world.tick):
            continue
        maint = world.building_maintenance.get(iid, {})
        total += int(maint.get("stored_wh", 0))
    return total


def _discharge_battery(world: World, plot_id: PlotId, wh: int) -> int:
    """Remove up to ``wh`` Wh from batteries on plot; returns Wh actually taken."""
    if wh <= 0:
        return 0
    remaining = wh
    for pb in sorted(
        world.placed_buildings.values(),
        key=lambda b: str(b.instance_id),
    ):
        if remaining <= 0:
            break
        if str(pb.plot_id) != str(plot_id) or pb.blueprint_id not in BATTERY_BLUEPRINT_IDS:
            continue
        if str(pb.status) != "active":
            continue
        maint = world.building_maintenance.setdefault(
            pb.instance_id,
            {"efficiency_pct": 100, "missed_cycles": 0, "due_at_tick": 0, "stored_wh": 0},
        )
        have = int(maint.get("stored_wh", 0))
        if have <= 0:
            continue
        take = min(have, remaining)
        maint["stored_wh"] = have - take
        remaining -= take
    for row in sorted(world.plot_buildings, key=lambda r: str(r.get("instance_id", ""))):
        if remaining <= 0:
            break
        if str(row.get("plot_id", "")) != str(plot_id):
            continue
        bid = str(row.get("building_id", ""))
        if bid not in BATTERY_BLUEPRINT_IDS:
            continue
        iid = str(row.get("instance_id", ""))
        if not iid or int(row.get("completes_at_tick", 0)) > int(world.tick):
            continue
        maint = world.building_maintenance.setdefault(
            iid,
            {"efficiency_pct": 100, "missed_cycles": 0, "due_at_tick": 0, "stored_wh": 0},
        )
        have = int(maint.get("stored_wh", 0))
        if have <= 0:
            continue
        take = min(have, remaining)
        maint["stored_wh"] = have - take
        remaining -= take
    return wh - remaining


def check_energy_for_production(
    world: World, party: PartyId, plot_id: PlotId, recipe: object
) -> dict | None:
    """``None`` if ok, else ``{ok: False, reason}``."""
    need = recipe_energy_wh(recipe)
    if need <= 0:
        return None
    from realm.infrastructure.power_grid import plot_has_grid_capacity

    if plot_has_grid_capacity(world, plot_id):
        from realm.infrastructure.grid_utility import party_may_draw_grid_energy

        allowed, reason = party_may_draw_grid_energy(world, party, plot_id)
        if allowed:
            return None
        return {"ok": False, "reason": reason or "grid access not authorized"}
    from_battery = _discharge_battery(world, plot_id, need)
    if from_battery >= need:
        return None
    kwh = need / 1000
    have_kwh = from_battery / 1000
    return {
        "ok": False,
        "reason": (
            f"need {kwh:.1f} kWh for this run — plot not on a powered grid "
            f"(battery has {have_kwh:.1f} kWh). Build road to a generator, add a "
            f"battery_bank, or run a local generator."
        ),
    }


def commit_energy_for_production(
    world: World, party: PartyId, plot_id: PlotId, recipe: object
) -> None:
    """Record Wh consumption (grid first, then battery)."""
    need = recipe_energy_wh(recipe)
    if need <= 0:
        return
    from realm.infrastructure.power_grid import plot_has_grid_capacity, record_energy_wh

    if plot_has_grid_capacity(world, plot_id):
        from realm.infrastructure.grid_utility import party_may_draw_grid_energy

        if party_may_draw_grid_energy(world, party, plot_id)[0]:
            record_energy_wh(world, plot_id, need, party=party)
            return
    taken = _discharge_battery(world, plot_id, need)
    if taken > 0:
        record_energy_wh(world, plot_id, taken, party=party, off_grid=True)


def record_generator_export(world: World, plot_id: PlotId, wh: int) -> None:
    if wh <= 0:
        return
    from realm.infrastructure.power_grid import record_generation_wh

    record_generation_wh(world, plot_id, wh)
