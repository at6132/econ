"""Schematic linear-chain validation (engine authority)."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.schematic import validate_linear_recipe_chain
from realm.world import bootstrap_frontier


def test_schematic_chain_ok_compounds_outputs() -> None:
    w = bootstrap_frontier(seed=90, grid_width=2, grid_height=2)
    party = PartyId("player")
    w.inventory.add(party, MaterialId("timber"), 4)
    w.inventory.add(party, MaterialId("coal"), 2)
    w.inventory.add(party, MaterialId("grain"), 4)
    r = validate_linear_recipe_chain(
        w,
        party,
        ["coal_generator", "sawmill", "mill_flour"],
    )
    assert r["ok"] is True
    fin = r["final_inventory"]
    assert fin.get("electricity", 0) >= 1
    assert fin.get("lumber", 0) >= 1
    assert fin.get("flour", 0) >= 1


def test_schematic_unknown_recipe() -> None:
    w = bootstrap_frontier(seed=91, grid_width=2, grid_height=2)
    r = validate_linear_recipe_chain(w, PartyId("player"), ["not_a_real_recipe"])
    assert r["ok"] is False
    assert any("unknown recipe" in e for e in r["errors"])


def test_schematic_shortfall() -> None:
    w = bootstrap_frontier(seed=92, grid_width=2, grid_height=2)
    party = PartyId("player")
    bucket = w.inventory.stock.get(party, {})
    for mid in list(bucket.keys()):
        q = bucket.get(mid, 0)
        if q > 0:
            w.inventory.remove(party, mid, q)
    r = validate_linear_recipe_chain(w, party, ["sawmill"])
    assert r["ok"] is False
    assert r["errors"]


def test_schematic_twist_rope_then_build_ladder() -> None:
    w = bootstrap_frontier(seed=93, grid_width=2, grid_height=2)
    party = PartyId("player")
    bucket = w.inventory.stock.get(party, {})
    for mid in list(bucket.keys()):
        q = bucket.get(mid, 0)
        if q > 0:
            w.inventory.remove(party, mid, q)
    w.inventory.add(party, MaterialId("timber"), 1)
    w.inventory.add(party, MaterialId("lumber"), 4)
    w.inventory.add(party, MaterialId("electricity"), 10)
    r = validate_linear_recipe_chain(w, party, ["twist_rope", "build_ladder"])
    assert r["ok"] is True
    assert r["final_inventory"].get("ladder", 0) >= 1
