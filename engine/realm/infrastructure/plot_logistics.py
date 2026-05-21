"""Plot-local bulk storage — source of truth for matter at a site (Option B)."""

from __future__ import annotations

from collections.abc import Sequence

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr, MatterOk, MatterResult
from realm.production.storage_caps import (
    is_carried_material,
    party_uses_plot_storage,
    plot_storage_cap_units,
    try_add_inventory,
)
from realm.world import World


def plot_logistics_enabled(world: World) -> bool:
    return bool(world.use_plot_output_logistics)


def uses_plot_logistics(world: World, party: PartyId) -> bool:
    return plot_logistics_enabled(world) and party_uses_plot_storage(world, party)


def party_material_on_plot(
    world: World, party: PartyId, plot_id: PlotId, material: MaterialId
) -> int:
    """Units on ``plot_id`` usable for production (excludes market-listed / FOB-committed)."""
    if is_carried_material(material):
        return world.inventory.qty(party, material, "any")
    if not uses_plot_logistics(world, party):
        return world.inventory.qty(party, material, "any")
    from realm.economy.market_reserves import plot_available_qty

    return plot_available_qty(world, plot_id, material)


def party_material_held(
    world: World,
    party: PartyId,
    material: MaterialId,
    *,
    owned_plot_ids: Sequence[PlotId] | None = None,
) -> int:
    """Carried portable stock plus bulk staged on owned plots."""
    if not uses_plot_logistics(world, party):
        return world.inventory.qty(party, material, "any")
    t = world.inventory.qty(party, material, "any") if is_carried_material(material) else 0
    ms = str(material)
    if is_carried_material(material):
        pass
    elif owned_plot_ids is not None:
        for pid in owned_plot_ids:
            t += plot_output_qty(world, pid, material)
        return t
    for pid_str, bucket in world.plot_output_stock.items():
        q = int(bucket.get(ms, 0))
        if q <= 0:
            continue
        pl = world.plots.get(PlotId(pid_str))
        if pl is None or pl.owner != party:
            continue
        t += q
    return t


def _plot_owned_by(world: World, party: PartyId, plot_id: PlotId) -> bool:
    p = world.plots.get(plot_id)
    return p is not None and p.owner == party


def owned_plot_ids_sorted(world: World, party: PartyId) -> list[PlotId]:
    return sorted(
        (p.plot_id for p in world.plots.values() if p.owner == party),
        key=str,
    )


def plot_output_total(world: World, plot_id: PlotId) -> int:
    d = world.plot_output_stock.get(str(plot_id))
    if not d:
        return 0
    return sum(int(v) for v in d.values())


def plot_output_qty(world: World, plot_id: PlotId, material: MaterialId) -> int:
    d = world.plot_output_stock.get(str(plot_id))
    if not d:
        return 0
    return int(d.get(str(material), 0))


def try_add_plot_output(
    world: World,
    plot_id: PlotId,
    party: PartyId,
    material: MaterialId,
    qty: int,
) -> MatterResult:
    if qty < 0:
        return MatterErr(reason="quantity must be non-negative")
    if qty == 0:
        return MatterOk()
    if is_carried_material(material):
        return try_add_inventory(world, party, material, qty)
    if not _plot_owned_by(world, party, plot_id):
        return MatterErr(reason="plot not owned")
    if plot_output_total(world, plot_id) + qty > plot_storage_cap_units(world, plot_id):
        return MatterErr(reason="plot storage full")
    bucket = world.plot_output_stock.setdefault(str(plot_id), {})
    bucket[str(material)] = int(bucket.get(str(material), 0)) + qty
    return MatterOk()


def remove_plot_output(
    world: World, party: PartyId, plot_id: PlotId, material: MaterialId, qty: int
) -> MatterResult:
    if qty <= 0:
        return MatterErr(reason="quantity must be positive")
    if not _plot_owned_by(world, party, plot_id):
        return MatterErr(reason="plot not owned")
    pid = str(plot_id)
    bucket = world.plot_output_stock.get(pid)
    if not bucket:
        return MatterErr(reason="insufficient material")
    ms = str(material)
    cur = int(bucket.get(ms, 0))
    if cur < qty:
        return MatterErr(reason="insufficient material")
    new = cur - qty
    if new == 0:
        del bucket[ms]
    else:
        bucket[ms] = new
    if not bucket:
        del world.plot_output_stock[pid]
    return MatterOk()


def pick_plot_with_stock(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    *,
    preferred: PlotId | None = None,
) -> PlotId | None:
    from realm.economy.market_reserves import plot_available_qty

    if preferred is not None and plot_available_qty(world, preferred, material) >= qty:
        return preferred
    for pid in owned_plot_ids_sorted(world, party):
        if plot_available_qty(world, pid, material) >= qty:
            return pid
    return None


def remove_party_plot_stock(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    *,
    preferred_plot: PlotId | None = None,
) -> MatterResult:
    pid = pick_plot_with_stock(world, party, material, qty, preferred=preferred_plot)
    if pid is None:
        return MatterErr(reason="insufficient material on plots")
    return remove_plot_output(world, party, pid, material, qty)


def add_party_plot_stock(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    *,
    preferred_plot: PlotId | None = None,
) -> MatterResult:
    if is_carried_material(material):
        return try_add_inventory(world, party, material, qty)
    plots = owned_plot_ids_sorted(world, party)
    if not plots:
        return MatterErr(reason="no owned plot for bulk storage")
    pid = preferred_plot if preferred_plot in plots else plots[0]
    return try_add_plot_output(world, pid, party, material, qty)


def harvest_plot_output_to_party(
    world: World, party: PartyId, plot_id: PlotId, material: MaterialId, qty: int
) -> dict:
    """Move portable units from plot stock into personal carry."""
    if qty <= 0:
        return {"ok": False, "reason": "quantity must be positive"}
    if not uses_plot_logistics(world, party):
        return {"ok": False, "reason": "plot logistics not enabled"}
    if not is_carried_material(material):
        return {
            "ok": False,
            "reason": "bulk goods stay on the plot — ship them or sell from site",
        }
    if not _plot_owned_by(world, party, plot_id):
        return {"ok": False, "reason": "plot not owned"}
    rm = remove_plot_output(world, party, plot_id, material, qty)
    if isinstance(rm, MatterErr):
        return {"ok": False, "reason": rm.reason}
    ad = try_add_inventory(world, party, material, qty)
    if isinstance(ad, MatterErr):
        rb = try_add_plot_output(world, plot_id, party, material, qty)
        assert not isinstance(rb, MatterErr)
        return {"ok": False, "reason": ad.reason}
    log_event(
        world,
        "plot_harvest",
        f"{party} harvested {qty}×{material} from {plot_id} to carry",
        party=str(party),
        plot_id=str(plot_id),
        material=str(material),
        qty=qty,
    )
    return {"ok": True}


def ensure_inventory_from_stash(
    world: World, party: PartyId, material: MaterialId, target_inv_qty: int
) -> None:
    """Legacy helper — only moves portable goods from plot to carry."""
    if not uses_plot_logistics(world, party) or not is_carried_material(material):
        return
    target_inv_qty = max(0, target_inv_qty)
    while world.inventory.qty(party, material) < target_inv_qty:
        need = target_inv_qty - world.inventory.qty(party, material)
        moved = False
        for pid in owned_plot_ids_sorted(world, party):
            st = plot_output_qty(world, pid, material)
            if st <= 0:
                continue
            take = min(st, need)
            r = harvest_plot_output_to_party(world, party, pid, material, take)
            if not r.get("ok"):
                return
            moved = True
            if world.inventory.qty(party, material) >= target_inv_qty:
                return
        if not moved:
            return
