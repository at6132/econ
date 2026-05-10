"""Supply contracts: propose → accept → fulfill; deadlines and reputation."""

from __future__ import annotations

from realm.ids import MaterialId, PartyId
from realm.social import (
    accept_supply_contract,
    fulfill_supply_contract,
    propose_supply_contract,
)
from realm.tick import advance_tick
from realm.world import bootstrap_frontier


def test_supply_fulfill_moves_matter_and_money() -> None:
    w = bootstrap_frontier(seed=60, grid_width=2, grid_height=2)
    supplier = PartyId("player")
    buyer = PartyId("t1_consumer")
    t0 = w.ledger.total_cents()
    g0 = w.inventory.qty(supplier, MaterialId("grain"))
    b0 = w.inventory.qty(buyer, MaterialId("grain"))
    pr = propose_supply_contract(w, supplier, buyer, MaterialId("grain"), 2, 80, due_in_ticks=5)
    assert pr["ok"] is True
    cid = pr["contract_id"]
    assert accept_supply_contract(w, buyer, cid)["ok"] is True
    assert fulfill_supply_contract(w, supplier, cid)["ok"] is True
    assert w.ledger.total_cents() == t0
    assert w.inventory.qty(supplier, MaterialId("grain")) == g0 - 2
    assert w.inventory.qty(buyer, MaterialId("grain")) == b0 + 2
    assert w.reputation[str(supplier)]["honored"] >= 1
    assert w.reputation[str(buyer)]["honored"] >= 1


def test_supply_breach_marks_supplier() -> None:
    w = bootstrap_frontier(seed=61, grid_width=2, grid_height=2)
    vendor = PartyId("npc_grain_vendor")
    buyer = PartyId("t1_consumer")
    pr = propose_supply_contract(w, vendor, buyer, MaterialId("grain"), 1, 10, due_in_ticks=1)
    cid = pr["contract_id"]
    assert accept_supply_contract(w, buyer, cid)["ok"] is True
    br0 = w.reputation[str(vendor)]["breached"]
    advance_tick(w)
    assert w.tick == 1
    c = next(x for x in w.contracts if x["id"] == cid)
    assert c["status"] == "active"
    advance_tick(w)
    assert w.tick == 2
    c = next(x for x in w.contracts if x["id"] == cid)
    assert c["status"] == "breached"
    assert w.reputation[str(vendor)]["breached"] == br0 + 1


def test_supply_fulfill_rejects_wrong_supplier() -> None:
    w = bootstrap_frontier(seed=62, grid_width=2, grid_height=2)
    vendor = PartyId("npc_grain_vendor")
    buyer = PartyId("t1_consumer")
    pr = propose_supply_contract(w, vendor, buyer, MaterialId("grain"), 1, 1, due_in_ticks=3)
    cid = pr["contract_id"]
    assert accept_supply_contract(w, buyer, cid)["ok"] is True
    r = fulfill_supply_contract(w, buyer, cid)
    assert r["ok"] is False
