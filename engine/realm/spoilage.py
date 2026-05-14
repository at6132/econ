"""Organic / energy spoilage — 1:1 transform conserves matter (Law 1).

Covers both party inventory (the original Phase-1 surface) and plot-staged
inventory (Sprint 3 — Phase A.2). The latter is required for shipped
electricity to dissipate when held off-grid past its spoilage window.
"""

from __future__ import annotations

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.materials import MATERIALS
from realm.plot_logistics import (
    plot_output_qty,
    remove_plot_output,
    try_add_plot_output,
)
from realm.storage_caps import try_add_inventory
from realm.world import World


# Per-spoilable-material chance one unit transforms when the interval lands.
# Electricity is volatile (deterministically dissipates on its tick) so we use a
# higher rate; organic foods stay at the original gentle 12 % rate.
_SPOIL_RATES: dict[str, float] = {"electricity": 1.0}

# Materials that only dissipate while staged on a plot — they sit safely in
# party inventory (modelled as battery / reserve storage). Electricity is the
# canonical example: shipped electricity is volatile, but a producer's
# reserve cell is not.
_STAGED_ONLY_SPOILAGE: set[str] = {"electricity"}


def _spoil_chance(material: MaterialId) -> float:
    return _SPOIL_RATES.get(str(material), 0.12)


def _staged_only(material: MaterialId) -> bool:
    return str(material) in _STAGED_ONLY_SPOILAGE


def _spoil_party_inventory(world: World, mid: MaterialId, dest: MaterialId) -> None:
    chance = _spoil_chance(mid)
    for party in world.parties:
        if world.inventory.qty(party, mid) <= 0:
            continue
        rng = world.rng(f"spoil:{party}:{mid}")
        if chance < 1.0 and rng.random() >= chance:
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
            f"{party}: 1×{mid} → {dest} (spoilage)",
            party=str(party),
            from_material=str(mid),
            to_material=str(dest),
        )


def _spoil_plot_staged(world: World, mid: MaterialId, dest: MaterialId) -> None:
    chance = _spoil_chance(mid)
    # Iterate over a snapshot — we mutate plot_output_stock inside the loop.
    pids = list(world.plot_output_stock.keys())
    for pid_s in pids:
        bucket = world.plot_output_stock.get(pid_s) or {}
        if int(bucket.get(str(mid), 0)) <= 0:
            continue
        plot = world.plots.get(PlotId(pid_s))
        if plot is None or plot.owner is None:
            continue
        party = PartyId(str(plot.owner))
        rng = world.rng(f"spoilstaged:{pid_s}:{mid}")
        if chance < 1.0 and rng.random() >= chance:
            continue
        rm = remove_plot_output(world, party, PlotId(pid_s), mid, 1)
        if isinstance(rm, MatterErr):
            continue
        ad = try_add_plot_output(world, PlotId(pid_s), party, dest, 1)
        if isinstance(ad, MatterErr):
            # Roll back the staged removal — conservation must hold.
            try_add_plot_output(world, PlotId(pid_s), party, mid, 1)
            continue
        log_event(
            world,
            "material_spoilage",
            f"{party}: 1×{mid} (staged on {pid_s}) → {dest}",
            party=str(party),
            plot_id=pid_s,
            from_material=str(mid),
            to_material=str(dest),
        )


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
        if not _staged_only(mid):
            _spoil_party_inventory(world, mid, dest)
        _spoil_plot_staged(world, mid, dest)
