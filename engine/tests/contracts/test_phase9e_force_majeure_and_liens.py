"""Phase 9E — generalised force-majeure + lien on breached suppliers.

Closes audit findings B7.1 (force-majeure only covered storms) and B7.2
(when a breached supplier couldn't fully cover liquidated damages, the
unpaid portion was just lost -- the buyer ate the loss).

* ``general_force_majeure_extension_ticks`` returns a global extension
  for any active drought / blight / mine_collapse / epidemic / seismic
  / storm event (whichever has the longest remaining duration).
* ``tick_supply_contract_breaches`` extends the contract deadline
  instead of breaching when any of those events is active.
* On a real breach, the unpaid portion of the liquidated damages is
  recorded as a lien on ``world.liens`` and ``tick_liens`` drains it
  from the supplier's cash on subsequent ticks until paid in full.
"""

from __future__ import annotations

from realm.contracts.social import (
    tick_liens,
    tick_supply_contract_breaches,
)
from realm.core.ids import PartyId
from realm.core.inventory import Inventory
from realm.core.ledger import (
    Ledger,
    contract_escrow_account,
    party_cash_account,
    system_reserve_account,
)
from realm.events.world_events import (
    WorldEvent,
    general_force_majeure_extension_ticks,
)
from realm.world import World


def _make_world() -> tuple[World, PartyId, PartyId]:
    ledger = Ledger()
    ledger.seed_system_reserve(100_000_000)
    inv = Inventory()
    w = World(seed=1, tick=0, plots={}, ledger=ledger, inventory=inv)
    buyer = PartyId("buyer_inc")
    supplier = PartyId("supplier_co")
    w.parties.add(buyer)
    w.parties.add(supplier)
    w.reputation[str(buyer)] = {"honored": 0, "breached": 0}
    w.reputation[str(supplier)] = {"honored": 0, "breached": 0}
    for p in (buyer, supplier):
        acct = party_cash_account(p)
        ledger.ensure_account(acct)
        ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=1_000_000,
        )
    return w, buyer, supplier


def _seed_supply_contract(
    w: World,
    buyer: PartyId,
    supplier: PartyId,
    *,
    deposit: int = 0,
    damages: int = 100_000,
) -> str:
    """Build a minimal active supply contract directly on world.contracts."""
    w.next_contract_seq += 1
    cid = f"c-{w.next_contract_seq}"
    if deposit > 0:
        esc = contract_escrow_account(cid)
        w.ledger.ensure_account(esc)
        w.ledger.transfer(
            debit=party_cash_account(buyer),
            credit=esc,
            amount_cents=int(deposit),
        )
    w.contracts.append(
        {
            "id": cid,
            "kind": "supply",
            "status": "active",
            "buyer": str(buyer),
            "supplier": str(supplier),
            "material": "grain",
            "qty": 5,
            "total_price_cents": 50_000,
            "deliver_by_tick": 100,
            "buyer_deposit_cents": int(deposit),
            "liquidated_damages_cents": int(damages),
        }
    )
    return cid


def _inject_active_event(w: World, event_type: str, *, duration: int = 1_000) -> None:
    """Force an active world event onto the world (bypasses the RNG roll).

    Events are stored on the lazy ``_world_events_cache`` attribute; we
    populate that directly so ``active_events`` sees the event without us
    having to drive the RNG roll path.
    """
    start = int(w.tick)
    end = start + int(duration)
    cache = getattr(w, "_world_events_cache", None)
    if cache is None:
        cache = []
        setattr(w, "_world_events_cache", cache)
    cache.append(
        WorldEvent(
            event_id=f"{event_type}-test-{len(cache) + 1}",
            event_type=event_type,
            started_tick=start,
            end_tick=end,
            severity=0.5,
            island_id=0,
        )
    )


# ─────────────────── force-majeure generalisation ───────────────────


def test_force_majeure_grace_zero_when_no_events_active():
    w, _, _ = _make_world()
    assert general_force_majeure_extension_ticks(w) == 0


def test_drought_grants_force_majeure_grace():
    w, _, _ = _make_world()
    _inject_active_event(w, "drought", duration=5_000)
    grace = general_force_majeure_extension_ticks(w)
    assert grace > 0


def test_epidemic_grants_force_majeure_grace():
    w, _, _ = _make_world()
    _inject_active_event(w, "epidemic", duration=3_000)
    assert general_force_majeure_extension_ticks(w) > 0


def test_drought_extends_supply_contract_instead_of_breaching():
    w, buyer, supplier = _make_world()
    cid = _seed_supply_contract(w, buyer, supplier, damages=100_000)
    _inject_active_event(w, "drought", duration=4_000)
    w.tick = 200  # past the deliver_by_tick of 100
    tick_supply_contract_breaches(w)
    contract = next(c for c in w.contracts if c["id"] == cid)
    assert contract["status"] == "active"
    assert contract["deliver_by_tick"] > 100
    assert "force_majeure_extensions" in contract


def test_no_event_means_normal_breach_path():
    w, buyer, supplier = _make_world()
    cid = _seed_supply_contract(w, buyer, supplier, damages=100_000)
    w.tick = 200
    tick_supply_contract_breaches(w)
    contract = next(c for c in w.contracts if c["id"] == cid)
    assert contract["status"] == "breached"


# ─────────────────── lien creation + draining ───────────────────


def test_breach_with_undercapitalised_supplier_creates_lien():
    w, buyer, supplier = _make_world()
    # Drain supplier so they can only cover half the damages.
    sc = party_cash_account(supplier)
    bal = w.ledger.balance(sc)
    drain = bal - 60_000  # leave $600
    if drain > 0:
        w.ledger.transfer(
            debit=sc, credit=system_reserve_account(), amount_cents=drain
        )
    cid = _seed_supply_contract(w, buyer, supplier, damages=100_000)
    w.tick = 200
    buyer_before = w.ledger.balance(party_cash_account(buyer))
    tick_supply_contract_breaches(w)
    buyer_after = w.ledger.balance(party_cash_account(buyer))
    # Buyer gets whatever was on hand (60_000) + a lien for the remaining 40_000.
    assert buyer_after - buyer_before == 60_000
    open_liens = [l for l in w.liens if l["status"] == "open"]
    assert len(open_liens) == 1
    lien = open_liens[0]
    assert lien["debtor"] == str(supplier)
    assert lien["creditor"] == str(buyer)
    assert lien["amount_remaining_cents"] == 40_000
    assert lien["source_contract_id"] == cid


def test_lien_drains_when_supplier_earns_money_back():
    w, buyer, supplier = _make_world()
    # Cause an undercapitalised breach: supplier has only $300, damages $1,000.
    sc = party_cash_account(supplier)
    drain = w.ledger.balance(sc) - 30_000
    if drain > 0:
        w.ledger.transfer(
            debit=sc, credit=system_reserve_account(), amount_cents=drain
        )
    _seed_supply_contract(w, buyer, supplier, damages=100_000)
    w.tick = 200
    tick_supply_contract_breaches(w)
    lien = w.liens[0]
    assert lien["status"] == "open"
    # Top supplier back up.
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=sc,
        amount_cents=200_000,
    )
    w.tick = 250
    tick_liens(w)
    # Lien should have been fully drained (40_000 outstanding).
    assert lien["amount_remaining_cents"] == 0
    assert lien["status"] == "closed"


def test_partial_lien_payment_doesnt_close_the_lien():
    w, buyer, supplier = _make_world()
    sc = party_cash_account(supplier)
    drain = w.ledger.balance(sc)
    w.ledger.transfer(
        debit=sc, credit=system_reserve_account(), amount_cents=drain
    )  # supplier broke
    _seed_supply_contract(w, buyer, supplier, damages=200_000)
    w.tick = 200
    tick_supply_contract_breaches(w)
    lien = w.liens[0]
    assert lien["amount_remaining_cents"] == 200_000
    # Give supplier only $700; lien should drain 70_000 and remain open.
    w.ledger.transfer(
        debit=system_reserve_account(), credit=sc, amount_cents=70_000
    )
    w.tick = 250
    tick_liens(w)
    assert lien["amount_remaining_cents"] == 130_000
    assert lien["status"] == "open"


def test_money_conservation_through_breach_and_lien_drain():
    w, buyer, supplier = _make_world()
    _seed_supply_contract(w, buyer, supplier, damages=100_000)
    total_before = w.ledger.total_cents()
    w.tick = 200
    tick_supply_contract_breaches(w)
    # Eventually pay the lien if any was opened.
    for _ in range(3):
        tick_liens(w)
        w.tick += 1
    total_after = w.ledger.total_cents()
    assert total_before == total_after


def test_no_lien_when_supplier_fully_covers_damages():
    w, buyer, supplier = _make_world()
    _seed_supply_contract(w, buyer, supplier, damages=100_000)
    w.tick = 200
    tick_supply_contract_breaches(w)
    open_liens = [l for l in w.liens if l["status"] == "open"]
    assert open_liens == []
