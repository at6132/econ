"""Grant ``self_materials`` for contracted turnkey builds (tests only)."""

from __future__ import annotations

from realm.buildings import BUILDINGS
from realm.ids import MaterialId, PartyId
from realm.inventory import MatterErr
from realm.world import World


def grant_turnkey_self_materials(world: World, party: PartyId, building_id: str) -> None:
    spec = BUILDINGS.get(building_id)
    if not spec or str(spec.get("kind")) != "contracted":
        return
    for mid_s, qty in (spec.get("self_materials") or {}).items():
        ad = world.inventory.add(party, MaterialId(str(mid_s)), int(qty))
        assert not isinstance(ad, MatterErr), ad
