"""Genesis — population hubs periodically propose supply contracts to the player (Pacts tab)."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.event_log import log_event
from realm.social import propose_supply_contract
from realm.world import World

_PLAYER = PartyId("player")
_POP_HUB_E = PartyId("pop_hub_e")
_POP_HUB_W = PartyId("pop_hub_w")


def _has_pending_supply(
    world: World,
    *,
    supplier: PartyId,
    buyer: PartyId,
    material: MaterialId,
) -> bool:
    for c in world.contracts:
        if c.get("kind") != "supply" or c.get("status") != "proposed":
            continue
        if PartyId(str(c["supplier"])) != supplier or PartyId(str(c["buyer"])) != buyer:
            continue
        if str(c.get("material")) != str(material):
            continue
        return True
    return False


def tick_genesis_pop_hub_contracts(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    if world.tick < 36 or world.tick % 52 != 8:
        return
    if _POP_HUB_E in world.parties and not _has_pending_supply(
        world, supplier=_PLAYER, buyer=_POP_HUB_E, material=MaterialId("coal")
    ):
        qc = world.inventory.qty(_PLAYER, MaterialId("coal"))
        if qc >= 8:
            qty = min(14, max(8, qc // 2))
            unit = 68
            r = propose_supply_contract(
                world, _PLAYER, _POP_HUB_E, MaterialId("coal"), qty, qty * unit, 44
            )
            if r.get("ok"):
                log_event(
                    world,
                    "world_feed",
                    f"Eastern pop hub posted a draft supply pact: {qty}× coal @ {unit}¢/u — check Pacts.",
                )
    if _POP_HUB_W in world.parties and not _has_pending_supply(
        world, supplier=_PLAYER, buyer=_POP_HUB_W, material=MaterialId("grain")
    ):
        qg = world.inventory.qty(_PLAYER, MaterialId("grain"))
        if qg >= 10:
            qty = min(16, max(10, qg // 2))
            unit = 122
            r = propose_supply_contract(
                world, _PLAYER, _POP_HUB_W, MaterialId("grain"), qty, qty * unit, 56
            )
            if r.get("ok"):
                log_event(
                    world,
                    "world_feed",
                    f"Western pop hub drafted a grain standing order: {qty}× @ {unit}¢/u — check Pacts.",
                )
