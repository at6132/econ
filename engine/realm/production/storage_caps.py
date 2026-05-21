"""Storage capacity — personal carry vs plot-local bulk (warehouse / yard)."""

from __future__ import annotations

from realm.production.decay import building_effective_for_bonuses
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.time_scale import building_operational
from realm.core.inventory import MatterErr, MatterOk, MatterResult
from realm.world import World

# Personal inventory (tools, electricity) — small.
PERSONAL_CARRY_CAP_UNITS: int = 500
FIELD_STOCKADE_BONUS_UNITS: int = 200

# Plot-local bulk without / with warehouse.
PLOT_YARD_CAP_UNITS: int = 800
PLOT_WAREHOUSE_CAP_UNITS: int = 50_000

# Legacy alias used by tests referencing party-wide cap.
BASE_PARTY_STORAGE_UNITS: int = PERSONAL_CARRY_CAP_UNITS

# Materials that may live in party inventory (not plot bulk).
CARRIED_MATERIAL_IDS: frozenset[str] = frozenset({"mining_pick"})


def is_carried_material(material: MaterialId) -> bool:
    return str(material) in CARRIED_MATERIAL_IDS


def party_uses_plot_storage(world: World, party: PartyId) -> bool:
    """Human + settlers stage bulk on plots; NPC/system parties keep legacy inventory."""
    if not bool(world.use_plot_output_logistics):
        return False
    s = str(party)
    return s == "player" or s.startswith("settler_")


def plot_has_active_warehouse(world: World, plot_id: PlotId) -> bool:
    pid = str(plot_id)
    for b in world.plot_buildings:
        if str(b.get("plot_id")) != pid:
            continue
        if str(b.get("building_id")) != "warehouse":
            continue
        if not building_operational(b, at_tick=world.tick):
            continue
        if building_effective_for_bonuses(b):
            return True
    return False


def plot_storage_cap_units(world: World, plot_id: PlotId) -> int:
    if plot_has_active_warehouse(world, plot_id):
        return PLOT_WAREHOUSE_CAP_UNITS
    return PLOT_YARD_CAP_UNITS


def party_storage_cap_units(world: World, party: PartyId) -> int:
    """Personal carry cap (+ field_stockade bonus on carried totals only)."""
    cap = PERSONAL_CARRY_CAP_UNITS
    for b in world.plot_buildings:
        if b.get("party") != str(party):
            continue
        if not building_operational(b, at_tick=world.tick):
            continue
        if b.get("building_id") == "field_stockade" and building_effective_for_bonuses(b):
            cap += FIELD_STOCKADE_BONUS_UNITS
    return cap


def party_inventory_unit_total(world: World, party: PartyId) -> int:
    return sum(world.inventory.stock_for_party(party).values())


def party_matter_value_cents(world: World, party: PartyId) -> int:
    """Fair-value estimate of personal carry plus owned plot bulk."""
    try:
        from realm.economy.pricing import _FAIR_VALUE_CENTS
    except Exception:
        return 0
    total = 0
    for mat, qty in world.inventory.stock_for_party(party).items():
        unit = int(_FAIR_VALUE_CENTS.get(str(mat), 0))
        total += unit * int(qty)
    if not party_uses_plot_storage(world, party):
        return total
    from realm.core.ids import PlotId

    for pid_str, bucket in world.plot_output_stock.items():
        plot = world.plots.get(PlotId(pid_str))
        if plot is None or plot.owner != party:
            continue
        for mat_s, q in bucket.items():
            unit = int(_FAIR_VALUE_CENTS.get(str(mat_s), 0))
            total += unit * int(q)
    return total


def try_add_inventory(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    *,
    quality: str = "standard",
) -> MatterResult:
    """Add to personal carry if material is portable and cap allows."""
    if qty < 0:
        return MatterErr(reason="quantity must be non-negative")
    if qty == 0:
        return MatterOk()
    if party_uses_plot_storage(world, party) and not is_carried_material(material):
        return MatterErr(
            reason="bulk goods must be stored on a plot — ship, list from site, or harvest not applicable"
        )
    cap = party_storage_cap_units(world, party)
    if party_inventory_unit_total(world, party) + qty > cap:
        return MatterErr(reason="personal carry capacity exceeded")
    return world.inventory.add(party, material, qty, quality=quality)
