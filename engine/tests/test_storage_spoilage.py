"""Party storage caps and organic spoilage (Law 1)."""

from __future__ import annotations

from realm.actions import claim_plot
from realm.production.buildings import build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.production.spoilage import tick_material_spoilage
from realm.production.storage_caps import party_storage_cap_units, try_add_inventory
from realm.world import bootstrap_frontier


def test_try_add_respects_low_storage_cap(monkeypatch) -> None:
    from realm.production import storage_caps

    monkeypatch.setattr(storage_caps, "BASE_PARTY_STORAGE_UNITS", 10)
    w = bootstrap_frontier(seed=90, grid_width=2, grid_height=2)
    p = PartyId("player")
    r = try_add_inventory(w, p, MaterialId("grain"), 1)
    assert isinstance(r, MatterErr)
    assert r.reason == "storage capacity exceeded"


def test_field_stockade_increases_cap(monkeypatch) -> None:
    from realm.production import storage_caps

    monkeypatch.setattr(storage_caps, "BASE_PARTY_STORAGE_UNITS", 50)
    w = bootstrap_frontier(seed=91, grid_width=2, grid_height=2)
    p = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(w, p, pid)["ok"] is True
    assert isinstance(try_add_inventory(w, p, MaterialId("grain"), 10), MatterErr)
    assert build_on_plot(w, p, pid, "field_stockade")["ok"] is True
    row = next(b for b in w.plot_buildings if b.get("building_id") == "field_stockade")
    row.pop("completes_at_tick", None)
    assert party_storage_cap_units(w, p) == 50 + storage_caps.FIELD_STOCKADE_BONUS_UNITS
    assert not isinstance(try_add_inventory(w, p, MaterialId("grain"), 10), MatterErr)


def test_spoilage_transforms_one_grain_conserving_units() -> None:
    w = bootstrap_frontier(seed=92, grid_width=2, grid_height=2)
    w.tick = 600
    p = PartyId("player")

    def rng_stub(_purpose: str):
        class R:
            def random(self) -> float:
                return 0.0

        return R()

    w.rng = rng_stub  # type: ignore[method-assign]

    g0 = w.inventory.qty(p, MaterialId("grain"))
    sg0 = w.inventory.qty(p, MaterialId("spoiled_grain"))
    assert g0 > 0
    u_before = w.inventory.total_units()
    tick_material_spoilage(w)
    assert w.inventory.total_units() == u_before
    assert w.inventory.qty(p, MaterialId("grain")) == g0 - 1
    assert w.inventory.qty(p, MaterialId("spoiled_grain")) == sg0 + 1
