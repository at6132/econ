"""Honor-only contracts removed — enforced routing only."""

from __future__ import annotations

from realm.contracts.social import honor_contract_stub, propose_contract_stub, propose_enforced_contract
from realm.core.ids import MaterialId, PartyId
from realm.world import bootstrap_frontier


def test_honor_only_contract_rejected() -> None:
    w = bootstrap_frontier(seed=90, grid_width=2, grid_height=2)
    r = propose_contract_stub(w, PartyId("player"), PartyId("t1_consumer"), "handshake")
    assert r["ok"] is False


def test_honor_stub_deprecated() -> None:
    w = bootstrap_frontier(seed=91, grid_width=2, grid_height=2)
    r = honor_contract_stub(w, "c-1")
    assert r["ok"] is False
    assert "removed" in r["reason"].lower() or "enforce" in r["reason"].lower()


def test_enforced_supply_via_dispatcher() -> None:
    from realm.core.inventory import MatterErr

    w = bootstrap_frontier(seed=92, grid_width=2, grid_height=2)
    ad = w.inventory.add(PartyId("player"), MaterialId("grain"), 1)
    assert not isinstance(ad, MatterErr)
    r = propose_enforced_contract(
        w,
        PartyId("player"),
        PartyId("t1_consumer"),
        "supply",
        {"material": "grain", "qty": 1, "total_price_cents": 0, "due_in_ticks": 20},
    )
    assert r.get("ok") is True
