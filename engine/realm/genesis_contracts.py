"""Genesis — population hubs periodically propose supply contracts to the player (Pacts tab)."""

from __future__ import annotations

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId
from realm.plot_logistics import party_material_held
from realm.social import propose_supply_contract
from realm.time_scale import legacy_scaled
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


def _player_units_visible(world: World, material: MaterialId) -> int:
    """On-hand (inventory + staged on owned plots) + resting sell orders."""
    held = party_material_held(world, _PLAYER, material)
    listed = 0
    for o in world.market_asks_by_material.get(str(material), []):
        if o.party == _PLAYER:
            listed += int(o.qty) + int(o.iceberg_hidden_qty)
    return held + listed


def tick_genesis_pop_hub_contracts(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    period = legacy_scaled(24)
    if world.tick < legacy_scaled(18) or world.tick % period != 2:
        return
    if _POP_HUB_E in world.parties and not _has_pending_supply(
        world, supplier=_PLAYER, buyer=_POP_HUB_E, material=MaterialId("coal")
    ):
        qc = _player_units_visible(world, MaterialId("coal"))
        if qc >= 3:
            qty = min(18, max(3, qc // 2))
            unit = 68
            r = propose_supply_contract(
                world, _PLAYER, _POP_HUB_E, MaterialId("coal"), qty, qty * unit, legacy_scaled(44)
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
        qg = _player_units_visible(world, MaterialId("grain"))
        if qg >= 4:
            qty = min(20, max(4, qg // 2))
            unit = 122
            r = propose_supply_contract(
                world, _PLAYER, _POP_HUB_W, MaterialId("grain"), qty, qty * unit, legacy_scaled(56)
            )
            if r.get("ok"):
                log_event(
                    world,
                    "world_feed",
                    f"Western pop hub drafted a grain standing order: {qty}× @ {unit}¢/u — check Pacts.",
                )
