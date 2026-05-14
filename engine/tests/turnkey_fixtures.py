"""Grant ``self_materials`` for contracted turnkey builds (tests only)."""

from __future__ import annotations

from realm.buildings import BUILDINGS
from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.world import World


def grant_turnkey_self_materials(
    world: World, party: PartyId, building_id: str, *, count: int = 1
) -> None:
    """Stock ``count`` copies of the turnkey ``self_materials`` for a build.

    ``count`` lets tests pre-supply enough inputs to build the same
    contracted building more than once (e.g. multiple residences on the
    same island in Phase 7C).
    """
    spec = BUILDINGS.get(building_id)
    if not spec or str(spec.get("kind")) != "contracted":
        return
    for mid_s, qty in (spec.get("self_materials") or {}).items():
        ad = world.inventory.add(party, MaterialId(str(mid_s)), int(qty) * int(count))
        assert not isinstance(ad, MatterErr), ad
