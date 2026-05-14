"""Contracts + reputation (Primitive 8 / Law 7)."""

from __future__ import annotations

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, contract_escrow_account, party_cash_account
from realm.infrastructure.plot_logistics import ensure_inventory_from_stash, plot_logistics_enabled
from realm.production.storage_caps import try_add_inventory
from realm.world import World


def propose_contract_stub(world: World, party_a: PartyId, party_b: PartyId, kind: str) -> dict:
    """Legacy generic handshake (honor-only). Supply deals use ``propose_supply_contract``."""
    if kind in ("loan", "equity_stub", "service_sub"):
        return {
            "ok": False,
            "reason": "use POST /contracts/loan/propose, /contracts/equity/propose, or /contracts/service/propose",
        }
    if kind == "supply":
        return {
            "ok": False,
            "reason": "use POST /contracts/supply/propose with material, qty, price, and due_in_ticks",
        }
    world.next_contract_seq += 1
    cid = f"c-{world.next_contract_seq}"
    world.contracts.append(
        {
            "id": cid,
            "party_a": str(party_a),
            "party_b": str(party_b),
            "kind": kind,
            "status": "open",
        }
    )
    log_event(
        world,
        "contract_propose",
        f"Contract {cid}: {party_a} ↔ {party_b} ({kind})",
        contract_id=cid,
        party_a=str(party_a),
        party_b=str(party_b),
        contract_kind=kind,
    )
    return {"ok": True, "contract_id": cid}


def honor_contract_stub(world: World, contract_id: str) -> dict:
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") in ("loan", "equity_stub", "service_sub"):
            return {"ok": False, "reason": "use phase-2 contract routes for this kind"}
        if c.get("kind") == "supply" and "deliver_by_tick" in c:
            return {"ok": False, "reason": "supply contracts use accept then fulfill endpoints"}
        if c.get("status") not in ("open", "active"):
            return {"ok": False, "reason": "contract not open"}
        c["status"] = "honored"
        for k in ("party_a", "party_b"):
            p = PartyId(c[k])
            r = world.reputation.setdefault(str(p), {"honored": 0, "breached": 0})
            r["honored"] += 1
        log_event(world, "contract_honor", f"Contract {contract_id} honored", contract_id=contract_id)
        return {"ok": True}
    return {"ok": False, "reason": "contract not found"}


def propose_supply_contract(
    world: World,
    supplier: PartyId,
    buyer: PartyId,
    material: MaterialId,
    qty: int,
    total_price_cents: int,
    due_in_ticks: int,
    *,
    buyer_deposit_cents: int = 0,
    liquidated_damages_cents: int = 0,
) -> dict:
    """
    Supplier offers to deliver ``qty`` of ``material`` by ``deliver_by_tick`` (inclusive).
    Buyer must call ``accept_supply_contract`` before fulfillment is allowed.

    Optional ``buyer_deposit_cents``: moved from buyer to contract escrow on accept; released to
    supplier on fulfill or returned to buyer on breach.

    Optional ``liquidated_damages_cents``: on breach, supplier pays buyer up to this amount (capped
    by supplier cash), after deposit refund.
    """
    if qty <= 0:
        return {"ok": False, "reason": "qty must be positive"}
    if total_price_cents < 0:
        return {"ok": False, "reason": "price must be non-negative"}
    if due_in_ticks < 1:
        return {"ok": False, "reason": "due_in_ticks must be at least 1"}
    if buyer_deposit_cents < 0 or liquidated_damages_cents < 0:
        return {"ok": False, "reason": "deposit and damages must be non-negative"}
    if supplier not in world.parties or buyer not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if supplier == buyer:
        return {"ok": False, "reason": "supplier and buyer must differ"}
    world.next_contract_seq += 1
    cid = f"c-{world.next_contract_seq}"
    deliver_by = world.tick + due_in_ticks
    world.contracts.append(
        {
            "id": cid,
            "kind": "supply",
            "supplier": str(supplier),
            "buyer": str(buyer),
            "material": str(material),
            "qty": qty,
            "total_price_cents": total_price_cents,
            "deliver_by_tick": deliver_by,
            "status": "proposed",
            "buyer_deposit_cents": buyer_deposit_cents,
            "liquidated_damages_cents": liquidated_damages_cents,
        }
    )
    log_event(
        world,
        "contract_supply_propose",
        f"{supplier} proposes supply {cid}: {qty}×{material} to {buyer} for {total_price_cents}¢ by tick {deliver_by}",
        contract_id=cid,
        supplier=str(supplier),
        buyer=str(buyer),
        material=str(material),
        qty=qty,
        total_price_cents=total_price_cents,
        deliver_by_tick=deliver_by,
    )
    return {"ok": True, "contract_id": cid, "deliver_by_tick": deliver_by}


def accept_supply_contract(world: World, buyer: PartyId, contract_id: str) -> dict:
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "supply":
            return {"ok": False, "reason": "not a supply contract"}
        if c.get("status") != "proposed":
            return {"ok": False, "reason": "contract not awaiting acceptance"}
        if PartyId(c["buyer"]) != buyer:
            return {"ok": False, "reason": "not the buyer on this contract"}
        dep = int(c.get("buyer_deposit_cents", 0))
        if dep > 0:
            bc = party_cash_account(buyer)
            esc = contract_escrow_account(c["id"])
            world.ledger.ensure_account(esc)
            trd = world.ledger.transfer(debit=bc, credit=esc, amount_cents=dep)
            if isinstance(trd, MoneyErr):
                return {"ok": False, "reason": trd.reason}
        c["status"] = "active"
        log_event(
            world,
            "contract_supply_accept",
            f"{buyer} accepted supply {contract_id}",
            contract_id=contract_id,
            buyer=str(buyer),
        )
        return {"ok": True}
    return {"ok": False, "reason": "contract not found"}


def fulfill_supply_contract(world: World, supplier: PartyId, contract_id: str) -> dict:
    """Deliver goods and (if priced) payment; both parties gain ``honored`` reputation."""
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "supply":
            return {"ok": False, "reason": "not a supply contract"}
        if c.get("status") != "active":
            return {"ok": False, "reason": "contract not active"}
        if PartyId(c["supplier"]) != supplier:
            return {"ok": False, "reason": "not the supplier"}
        if world.tick > int(c["deliver_by_tick"]):
            return {"ok": False, "reason": "deadline passed"}
        buyer = PartyId(c["buyer"])
        mat = MaterialId(c["material"])
        qty = int(c["qty"])
        price = int(c["total_price_cents"])
        if plot_logistics_enabled(world):
            ensure_inventory_from_stash(world, supplier, mat, qty)
        if world.inventory.qty(supplier, mat) < qty:
            return {"ok": False, "reason": "insufficient material to fulfill"}
        bc = party_cash_account(buyer)
        sc = party_cash_account(supplier)
        if world.ledger.balance(bc) < price:
            return {"ok": False, "reason": "buyer insufficient cash"}
        if price > 0:
            pay = world.ledger.transfer(debit=bc, credit=sc, amount_cents=price)
            if isinstance(pay, MoneyErr):
                return {"ok": False, "reason": pay.reason}
        rm = world.inventory.remove(supplier, mat, qty)
        if isinstance(rm, MatterErr):
            if price > 0:
                world.ledger.transfer(debit=sc, credit=bc, amount_cents=price)
            return {"ok": False, "reason": rm.reason}
        ad = try_add_inventory(world, buyer, mat, qty)
        if isinstance(ad, MatterErr):
            world.inventory.add(supplier, mat, qty)
            if price > 0:
                world.ledger.transfer(debit=sc, credit=bc, amount_cents=price)
            return {"ok": False, "reason": ad.reason}
        dep = int(c.get("buyer_deposit_cents", 0))
        if dep > 0:
            esc = contract_escrow_account(c["id"])
            trd = world.ledger.transfer(debit=esc, credit=sc, amount_cents=dep)
            if isinstance(trd, MoneyErr):
                rb = world.inventory.remove(buyer, mat, qty)
                if not isinstance(rb, MatterErr):
                    world.inventory.add(supplier, mat, qty)
                if price > 0:
                    world.ledger.transfer(debit=sc, credit=bc, amount_cents=price)
                return {"ok": False, "reason": trd.reason}
        c["status"] = "fulfilled"
        for pid in (supplier, buyer):
            r = world.reputation.setdefault(str(pid), {"honored": 0, "breached": 0})
            r["honored"] += 1
        log_event(
            world,
            "contract_supply_fulfill",
            f"{supplier} fulfilled {contract_id}: {qty}×{mat} → {buyer}",
            contract_id=contract_id,
            supplier=str(supplier),
            buyer=str(buyer),
            material=str(mat),
            qty=qty,
            total_price_cents=price,
        )
        return {"ok": True}
    return {"ok": False, "reason": "contract not found"}


def tick_supply_contract_breaches(world: World) -> None:
    """After ``world.tick`` advances: active supply past ``deliver_by_tick`` becomes breached (supplier only).

    Phase 8 — Sub-phase 8B (B5/D3): contracts are NOT auto-breached while
    an active storm is delaying global shipping. The supplier gets a
    ``force_majeure_extension_tick`` grace period equal to the storm's
    remaining duration plus one game-day. This avoids unfair breaches
    when ocean weather suspends the player's ability to ship.
    """
    from realm.events.world_events import (
        active_events as _active_events,
        storm_force_majeure_extension_ticks,
    )

    t = world.tick
    # Cache the global storm extension once per tick — supply contracts
    # don't carry island info so we apply the longest active storm grace
    # period to any contract that would otherwise breach right now.
    active_storms = [ev for ev in _active_events(world) if ev.event_type == "storm"]
    storm_grace = 0
    if active_storms:
        storm_grace = max(
            storm_force_majeure_extension_ticks(world, ev.island_id)
            for ev in active_storms
        )
    for c in world.contracts:
        if c.get("kind") != "supply":
            continue
        if c.get("status") != "active":
            continue
        if t <= int(c["deliver_by_tick"]):
            continue
        if storm_grace > 0:
            # Extend the deadline rather than breach. Mark the contract so
            # the player can see force-majeure was applied.
            new_deadline = int(c["deliver_by_tick"]) + int(storm_grace)
            c["deliver_by_tick"] = new_deadline
            ext_log = c.setdefault("force_majeure_extensions", [])
            ext_log.append({"tick": int(t), "extra_ticks": int(storm_grace)})
            log_event(
                world,
                "contract_force_majeure",
                f"Supply {c['id']}: deadline extended by storm "
                f"(+{storm_grace} ticks → new deadline {new_deadline})",
                contract_id=c["id"],
                extra_ticks=int(storm_grace),
            )
            continue
        c["status"] = "breached"
        sup = PartyId(c["supplier"])
        buyer = PartyId(c["buyer"])
        r = world.reputation.setdefault(str(sup), {"honored": 0, "breached": 0})
        r["breached"] += 1
        dep = int(c.get("buyer_deposit_cents", 0))
        if dep > 0:
            esc = contract_escrow_account(c["id"])
            world.ledger.transfer(debit=esc, credit=party_cash_account(buyer), amount_cents=dep)
        dmg = int(c.get("liquidated_damages_cents", 0))
        if dmg > 0:
            bc = party_cash_account(buyer)
            sc = party_cash_account(sup)
            pay = min(dmg, world.ledger.balance(sc))
            if pay > 0:
                world.ledger.transfer(debit=sc, credit=bc, amount_cents=pay)
        log_event(
            world,
            "contract_supply_breach",
            f"Supply {c['id']}: {sup} missed deadline (due by tick {c['deliver_by_tick']}, now {t})",
            contract_id=c["id"],
            supplier=str(sup),
            buyer=str(c.get("buyer", "")),
        )


def bump_spot_exchange_honored(world: World, party_a: PartyId, party_b: PartyId) -> None:
    """Successful spot trade (order book or P2P): increment honored for both parties (Law 7)."""
    for pid in (party_a, party_b):
        r = world.reputation.setdefault(str(pid), {"honored": 0, "breached": 0})
        r["honored"] = int(r.get("honored", 0)) + 1
