"""Plot-local output stock (Genesis player): outputs and inbound shipments land on the plot until harvested."""

from __future__ import annotations

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import MatterErr, MatterOk, MatterResult
from realm.storage_caps import try_add_inventory
from realm.world import World

# Per-plot cap on total units staged (all materials); separate from party inventory cap.
PLOT_OUTPUT_STORAGE_CAP_UNITS = 50_000


def uses_plot_logistics(world: World, party: PartyId) -> bool:
    """Solo human Genesis: production outputs and deliveries stage on owned plots."""
    return bool(world.use_plot_output_logistics) and party == PartyId("player")


def _plot_owned_by(world: World, party: PartyId, plot_id: PlotId) -> bool:
    p = world.plots.get(plot_id)
    return p is not None and p.owner == party


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
    world: World, plot_id: PlotId, party: PartyId, material: MaterialId, qty: int
) -> MatterResult:
    if qty < 0:
        return MatterErr(reason="quantity must be non-negative")
    if qty == 0:
        return MatterOk()
    if not _plot_owned_by(world, party, plot_id):
        return MatterErr(reason="plot not owned")
    if plot_output_total(world, plot_id) + qty > PLOT_OUTPUT_STORAGE_CAP_UNITS:
        return MatterErr(reason="plot output storage full")
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


def harvest_plot_output_to_party(
    world: World, party: PartyId, plot_id: PlotId, material: MaterialId, qty: int
) -> dict:
    """Move staged units from plot stock into party inventory (subject to party storage cap)."""
    if qty <= 0:
        return {"ok": False, "reason": "quantity must be positive"}
    if not uses_plot_logistics(world, party):
        return {"ok": False, "reason": "plot logistics not enabled"}
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
        f"{party} harvested {qty}×{material} from {plot_id} to inventory",
        party=str(party),
        plot_id=str(plot_id),
        material=str(material),
        qty=qty,
    )
    return {"ok": True}
