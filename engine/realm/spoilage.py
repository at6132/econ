"""Organic spoilage — 1:1 transform conserves matter (Law 1)."""

from __future__ import annotations

from realm.event_log import log_event
from realm.inventory import MatterErr
from realm.materials import MATERIALS
from realm.storage_caps import try_add_inventory
from realm.world import World


def tick_material_spoilage(world: World) -> None:
    """Each tick: for materials with ``spoilage_interval_ticks``, maybe convert one unit to ``spoils_to``."""
    for mid, mdef in MATERIALS.items():
        if mdef.durable:
            continue
        interval = mdef.spoilage_interval_ticks
        if interval <= 0 or mdef.spoils_to is None:
            continue
        if world.tick % interval != 0:
            continue
        dest = mdef.spoils_to
        for party in world.parties:
            if world.inventory.qty(party, mid) <= 0:
                continue
            rng = world.rng(f"spoil:{party}:{mid}")
            if rng.random() >= 0.12:
                continue
            rm = world.inventory.remove(party, mid, 1)
            if isinstance(rm, MatterErr):
                continue
            ad = try_add_inventory(world, party, dest, 1)
            if isinstance(ad, MatterErr):
                world.inventory.add(party, mid, 1)
                continue
            log_event(
                world,
                "material_spoilage",
                f"{party}: 1×{mid} → {dest} (organic spoilage)",
                party=str(party),
                from_material=str(mid),
                to_material=str(dest),
            )
