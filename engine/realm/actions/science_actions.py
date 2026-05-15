"""Phase 10E — laboratory bench reactions (no parallel production recipe)."""

from __future__ import annotations

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.production.buildings import BUILDINGS
from realm.science.chemistry import try_reaction
from realm.world import World


def run_laboratory_bench(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    material_a: str,
    material_b: str,
) -> dict:
    """Consume one unit of each input when a known reaction exists; grant output."""
    if party not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    plot = world.plots.get(plot_id)
    if plot is None or plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    has_lab = any(
        str(b.get("plot_id")) == str(plot_id)
        and str(b.get("party")) == str(party)
        and str(b.get("building_id")) == "laboratory"
        and int(b.get("completes_at_tick", 0)) <= int(world.tick)
        for b in world.plot_buildings
    )
    if not has_lab:
        return {"ok": False, "reason": "completed laboratory required on plot"}
    if material_a == material_b:
        return {"ok": False, "reason": "need two distinct materials"}
    out = try_reaction(material_a, material_b)
    if out is None:
        return {"ok": False, "reason": "no known reaction for inputs"}
    out_id, qty = out
    ma = MaterialId(material_a)
    mb = MaterialId(material_b)
    if world.inventory.qty(party, ma) < 1 or world.inventory.qty(party, mb) < 1:
        return {"ok": False, "reason": "insufficient inputs"}
    r1 = world.inventory.remove(party, ma, 1)
    if isinstance(r1, MatterErr):
        return {"ok": False, "reason": r1.reason}
    r2 = world.inventory.remove(party, mb, 1)
    if isinstance(r2, MatterErr):
        return {"ok": False, "reason": r2.reason}
    prod = MaterialId(out_id)
    ad = world.inventory.add(party, prod, int(qty))
    if isinstance(ad, MatterErr):
        return {"ok": False, "reason": ad.reason}
    return {"ok": True, "output": out_id, "qty": int(qty)}


def laboratory_catalog_public() -> dict:
    """Static reference for API."""
    lab = BUILDINGS.get("laboratory") or {}
    return {
        "building_id": "laboratory",
        "label": str(lab.get("label", "Laboratory")),
    }
