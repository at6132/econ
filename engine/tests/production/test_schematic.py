"""Schematic linear-chain validation (engine authority)."""

from __future__ import annotations

from realm.production.decay import BUILDING_CONDITION_FULL_BPS
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.production.schematic import validate_linear_recipe_chain
from realm.world.terrain import Terrain
from realm.world import bootstrap_frontier

from plot_helpers import first_land_plot_id


def _wood_shop_row(plot_id: str) -> dict:
    return {
        "instance_id": "schematic-ws",
        "condition_bps": BUILDING_CONDITION_FULL_BPS,
        "plot_id": plot_id,
        "party": "player",
        "building_id": "wood_shop",
        "label": "Wood shop",
        "cost_cents": 118_000,
        "build_mode": "turnkey",
    }


def _power_shed_row(plot_id: str) -> dict:
    return {
        "instance_id": "schematic-ps",
        "condition_bps": BUILDING_CONDITION_FULL_BPS,
        "plot_id": plot_id,
        "party": "player",
        "building_id": "power_shed",
        "label": "Power shed",
        "cost_cents": 78_000,
        "build_mode": "turnkey",
    }


def _land_plot(w) -> tuple[PlotId, object]:
    pid = first_land_plot_id(w)
    return pid, w.plots[pid]


def test_schematic_coal_generator_then_sawmill_two_workshops() -> None:
    w = bootstrap_frontier(seed=93, grid_width=2, grid_height=2)
    party = PartyId("player")
    pid, plot = _land_plot(w)
    ps = str(pid)
    w.plot_buildings.append(_power_shed_row(ps))
    w.plot_buildings.append(_wood_shop_row(ps))
    w.inventory.add(party, MaterialId("coal"), 3)
    w.inventory.add(party, MaterialId("timber"), 4)
    w.inventory.add(party, MaterialId("electricity"), 2)
    r = validate_linear_recipe_chain(w, party, ["coal_generator", "sawmill"], plot=plot)
    assert r["ok"] is True
    fin = r["final_inventory"]
    assert fin.get("lumber", 0) >= 1


def test_schematic_twist_rope_and_mill_flour_requires_gristmill() -> None:
    w = bootstrap_frontier(seed=93, grid_width=2, grid_height=2)
    party = PartyId("player")
    pid, plot = _land_plot(w)
    w.plot_buildings.append(_wood_shop_row(str(pid)))
    w.inventory.add(party, MaterialId("timber"), 4)
    w.inventory.add(party, MaterialId("coal"), 2)
    w.inventory.add(party, MaterialId("grain"), 4)
    r = validate_linear_recipe_chain(
        w,
        party,
        ["twist_rope", "mill_flour"],
        plot=plot,
    )
    assert r["ok"] is False
    assert any("needs workshop" in e for e in r["errors"])


def test_schematic_mill_flour_requires_gristmill_even_with_wood_shop() -> None:
    w = bootstrap_frontier(seed=93, grid_width=2, grid_height=2)
    party = PartyId("player")
    pid, plot = _land_plot(w)
    w.plot_buildings.append(_wood_shop_row(str(pid)))
    bucket = w.inventory.stock.get(party, {})
    for mid in list(bucket.keys()):
        q = bucket.get(mid, 0)
        if q > 0:
            w.inventory.remove(party, mid, q)
    w.inventory.add(party, MaterialId("timber"), 1)
    w.inventory.add(party, MaterialId("lumber"), 4)
    w.inventory.add(party, MaterialId("electricity"), 10)
    w.inventory.add(party, MaterialId("grain"), 4)
    r = validate_linear_recipe_chain(w, party, ["twist_rope", "mill_flour"], plot=plot)
    assert r["ok"] is False
    assert any("gristmill" in e for e in r["errors"])


def test_schematic_unknown_recipe() -> None:
    w = bootstrap_frontier(seed=91, grid_width=2, grid_height=2)
    _, plot = _land_plot(w)
    r = validate_linear_recipe_chain(w, PartyId("player"), ["not_a_real_recipe"], plot=plot)
    assert r["ok"] is False
    assert any("unknown recipe" in e for e in r["errors"])


def test_schematic_shortfall() -> None:
    w = bootstrap_frontier(seed=93, grid_width=2, grid_height=2)
    party = PartyId("player")
    pid, plot = _land_plot(w)
    w.plot_buildings.append(_wood_shop_row(str(pid)))
    bucket = w.inventory.stock.get(party, {})
    for mid in list(bucket.keys()):
        q = bucket.get(mid, 0)
        if q > 0:
            w.inventory.remove(party, mid, q)
    r = validate_linear_recipe_chain(w, party, ["sawmill"], plot=plot)
    assert r["ok"] is False
    assert r["errors"]


def test_schematic_twist_rope_then_build_ladder() -> None:
    w = bootstrap_frontier(seed=93, grid_width=2, grid_height=2)
    party = PartyId("player")
    pid, plot = _land_plot(w)
    w.plot_buildings.append(_wood_shop_row(str(pid)))
    bucket = w.inventory.stock.get(party, {})
    for mid in list(bucket.keys()):
        q = bucket.get(mid, 0)
        if q > 0:
            w.inventory.remove(party, mid, q)
    w.inventory.add(party, MaterialId("timber"), 1)
    w.inventory.add(party, MaterialId("lumber"), 4)
    w.inventory.add(party, MaterialId("electricity"), 10)
    r = validate_linear_recipe_chain(w, party, ["twist_rope", "build_ladder"], plot=plot)
    assert r["ok"] is True
    assert r["final_inventory"].get("ladder", 0) >= 1


def test_schematic_rejects_sawmill_on_mountain() -> None:
    w = bootstrap_frontier(seed=9, grid_width=8, grid_height=4)
    plot = next(
        (p for p in w.plots.values() if p.terrain == Terrain.MOUNTAIN),
        None,
    )
    if plot is None:
        pid = first_land_plot_id(w)
        plot = w.plots[pid]
        plot.terrain = Terrain.MOUNTAIN
    assert plot.terrain == Terrain.MOUNTAIN
    party = PartyId("player")
    w.plot_buildings.append(_wood_shop_row(str(plot.plot_id)))
    w.inventory.add(party, MaterialId("timber"), 4)
    w.inventory.add(party, MaterialId("electricity"), 2)
    r = validate_linear_recipe_chain(w, party, ["sawmill"], plot=plot)
    assert r["ok"] is False
    assert any("not available on this plot" in e for e in r["errors"])
