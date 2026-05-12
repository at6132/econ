"""Party-wide storage capacity (Primitive 2 / Law 1) — additions blocked when over cap."""

from __future__ import annotations

from realm.decay import building_effective_for_bonuses
from realm.ids import MaterialId, PartyId
from realm.time_scale import building_operational
from realm.inventory import MatterErr, MatterOk, MatterResult
from realm.world import World

# Default high enough for Frontier bootstrap; field_stockade adds meaningful headroom.
BASE_PARTY_STORAGE_UNITS = 50_000
FIELD_STOCKADE_BONUS_UNITS = 5_000


def party_storage_cap_units(world: World, party: PartyId) -> int:
    cap = BASE_PARTY_STORAGE_UNITS
    if world.scenario_id == "genesis" and str(party).startswith("pop_hub_"):
        cap += 250_000
    for b in world.plot_buildings:
        if b.get("party") != str(party):
            continue
        if not building_operational(b, at_tick=world.tick):
            continue
        if b.get("building_id") == "field_stockade" and building_effective_for_bonuses(b):
            cap += FIELD_STOCKADE_BONUS_UNITS
    return cap


def party_inventory_unit_total(world: World, party: PartyId) -> int:
    return sum(world.inventory.stock.get(party, {}).values())


def try_add_inventory(world: World, party: PartyId, material: MaterialId, qty: int) -> MatterResult:
    """Add units if party total after add would not exceed storage cap."""
    if qty < 0:
        return MatterErr(reason="quantity must be non-negative")
    if qty == 0:
        return MatterOk()
    cap = party_storage_cap_units(world, party)
    if party_inventory_unit_total(world, party) + qty > cap:
        return MatterErr(reason="storage capacity exceeded")
    return world.inventory.add(party, material, qty)
