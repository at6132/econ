"""Phase 2 contract stubs — loan, equity cash-flow, prepaid service (Primitive 8).

These are **stubs**: small FSMs with ledger-backed cash movement and reputation hooks,
not full negotiable terms or enforcement of future player-defined contract types.

FSM summaries
-------------
**loan:** ``proposed`` → (borrower ``accept``: principal moves lender→borrower) → ``active``
→ (borrower ``repay`` or overdue tick auto-settle) → ``repaid`` | ``breached``.

**equity_stub:** ``proposed`` → (investor ``accept``: investment moves investor→issuer) →
``active`` → each tick one dividend issuer→investor until ``completed``; issuer shortfall →
``breached``.

**service_sub:** ``proposed`` → (subscriber ``accept``: fee moves subscriber→provider) →
``active`` until ``expires_tick`` → ``expired``.

**forward_contract** (Sprint 4 — Phase C): ``proposed`` → (buyer ``accept``: seller deposit
escrowed) → ``active`` → (seller ``deliver``: goods + payment + deposit release) →
``delivered``. Missed deadline ⇒ seller deposit transferred to buyer, ``defaulted``,
seller reputation hit.
"""

from __future__ import annotations

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.world import World


def _next_contract_id(world: World) -> str:
    world.next_contract_seq += 1
    return f"c-{world.next_contract_seq}"


def propose_loan_contract(
    world: World,
    lender: PartyId,
    borrower: PartyId,
    principal_cents: int,
    repay_cents: int,
    due_in_ticks: int,
) -> dict:
    if principal_cents <= 0 or repay_cents <= 0:
        return {"ok": False, "reason": "principal and repay must be positive"}
    if repay_cents < principal_cents:
        return {"ok": False, "reason": "repay must be at least principal"}
    if due_in_ticks < 1:
        return {"ok": False, "reason": "due_in_ticks must be at least 1"}
    if lender not in world.parties or borrower not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if lender == borrower:
        return {"ok": False, "reason": "lender and borrower must differ"}
    cid = _next_contract_id(world)
    world.contracts.append(
        {
            "id": cid,
            "kind": "loan",
            "status": "proposed",
            "lender": str(lender),
            "borrower": str(borrower),
            "principal_cents": principal_cents,
            "repay_cents": repay_cents,
            "due_in_ticks": due_in_ticks,
        }
    )
    log_event(
        world,
        "contract_loan_propose",
        f"{lender} proposes loan {cid} to {borrower}: {principal_cents}¢ principal, repay {repay_cents}¢",
        contract_id=cid,
        lender=str(lender),
        borrower=str(borrower),
        principal_cents=principal_cents,
        repay_cents=repay_cents,
        due_in_ticks=due_in_ticks,
    )
    return {"ok": True, "contract_id": cid}


def accept_loan_contract(world: World, borrower: PartyId, contract_id: str) -> dict:
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "loan":
            return {"ok": False, "reason": "not a loan contract"}
        if c.get("status") != "proposed":
            return {"ok": False, "reason": "loan not awaiting acceptance"}
        if PartyId(c["borrower"]) != borrower:
            return {"ok": False, "reason": "not the borrower on this loan"}
        lender = PartyId(c["lender"])
        principal = int(c["principal_cents"])
        lc = party_cash_account(lender)
        bc = party_cash_account(borrower)
        tr = world.ledger.transfer(debit=lc, credit=bc, amount_cents=principal)
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}
        due = world.tick + int(c["due_in_ticks"])
        c["due_tick"] = due
        c["status"] = "active"
        log_event(
            world,
            "contract_loan_accept",
            f"{borrower} accepted loan {contract_id}; due tick {due}",
            contract_id=contract_id,
            borrower=str(borrower),
            lender=str(lender),
            due_tick=due,
        )
        return {"ok": True, "due_tick": due}
    return {"ok": False, "reason": "contract not found"}


def repay_loan_contract(world: World, borrower: PartyId, contract_id: str) -> dict:
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "loan":
            return {"ok": False, "reason": "not a loan contract"}
        if c.get("status") != "active":
            return {"ok": False, "reason": "loan not active"}
        if PartyId(c["borrower"]) != borrower:
            return {"ok": False, "reason": "not the borrower"}
        repay = int(c["repay_cents"])
        lender = PartyId(c["lender"])
        bc = party_cash_account(borrower)
        lc = party_cash_account(lender)
        tr = world.ledger.transfer(debit=bc, credit=lc, amount_cents=repay)
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}
        c["status"] = "repaid"
        for pid in (lender, borrower):
            r = world.reputation.setdefault(str(pid), {"honored": 0, "breached": 0})
            r["honored"] += 1
        log_event(
            world,
            "contract_loan_repay",
            f"{borrower} repaid loan {contract_id} ({repay}¢)",
            contract_id=contract_id,
        )
        return {"ok": True}
    return {"ok": False, "reason": "contract not found"}


def tick_loan_contracts(world: World) -> None:
    """Auto-settle overdue loans or seize available cash and mark breach."""
    t = world.tick
    for c in world.contracts:
        if c.get("kind") != "loan" or c.get("status") != "active":
            continue
        due = int(c.get("due_tick", t))
        if t <= due:
            continue
        borrower = PartyId(c["borrower"])
        lender = PartyId(c["lender"])
        need = int(c["repay_cents"])
        bc = party_cash_account(borrower)
        lc = party_cash_account(lender)
        bal = world.ledger.balance(bc)
        if bal >= need:
            tr = world.ledger.transfer(debit=bc, credit=lc, amount_cents=need)
            if not isinstance(tr, MoneyErr):
                c["status"] = "repaid"
                for pid in (lender, borrower):
                    r = world.reputation.setdefault(str(pid), {"honored": 0, "breached": 0})
                    r["honored"] += 1
                log_event(
                    world,
                    "contract_loan_auto_repay",
                    f"Loan {c['id']}: overdue auto-settled ({need}¢)",
                    contract_id=c["id"],
                )
            continue
        if bal > 0:
            world.ledger.transfer(debit=bc, credit=lc, amount_cents=bal)
        c["status"] = "breached"
        br = world.reputation.setdefault(str(borrower), {"honored": 0, "breached": 0})
        br["breached"] += 1
        log_event(
            world,
            "contract_loan_breach",
            f"Loan {c['id']}: borrower missed deadline (seized {bal}¢ of {need}¢)",
            contract_id=c["id"],
            borrower=str(borrower),
        )


def propose_equity_stub(
    world: World,
    issuer: PartyId,
    investor: PartyId,
    investment_cents: int,
    dividend_per_tick_cents: int,
    dividend_ticks: int,
) -> dict:
    if investment_cents <= 0:
        return {"ok": False, "reason": "investment must be positive"}
    if dividend_per_tick_cents <= 0 or dividend_ticks < 1:
        return {"ok": False, "reason": "invalid dividend schedule"}
    if issuer not in world.parties or investor not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if issuer == investor:
        return {"ok": False, "reason": "issuer and investor must differ"}
    cid = _next_contract_id(world)
    world.contracts.append(
        {
            "id": cid,
            "kind": "equity_stub",
            "status": "proposed",
            "issuer": str(issuer),
            "investor": str(investor),
            "investment_cents": investment_cents,
            "dividend_per_tick_cents": dividend_per_tick_cents,
            "dividend_ticks": dividend_ticks,
            "dividends_remaining": dividend_ticks,
        }
    )
    log_event(
        world,
        "contract_equity_propose",
        f"{issuer} proposes equity stub {cid}: {investment_cents}¢ for {dividend_ticks}×{dividend_per_tick_cents}¢/tick",
        contract_id=cid,
    )
    return {"ok": True, "contract_id": cid}


def accept_equity_stub(world: World, investor: PartyId, contract_id: str) -> dict:
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "equity_stub":
            return {"ok": False, "reason": "not an equity stub contract"}
        if c.get("status") != "proposed":
            return {"ok": False, "reason": "equity stub not awaiting acceptance"}
        if PartyId(c["investor"]) != investor:
            return {"ok": False, "reason": "not the investor on this contract"}
        issuer = PartyId(c["issuer"])
        inv_amt = int(c["investment_cents"])
        ic = party_cash_account(investor)
        isc = party_cash_account(issuer)
        tr = world.ledger.transfer(debit=ic, credit=isc, amount_cents=inv_amt)
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}
        c["status"] = "active"
        log_event(
            world,
            "contract_equity_accept",
            f"{investor} funded equity stub {contract_id}",
            contract_id=contract_id,
        )
        return {"ok": True}
    return {"ok": False, "reason": "contract not found"}


def tick_equity_stub(world: World) -> None:
    for c in world.contracts:
        if c.get("kind") != "equity_stub" or c.get("status") != "active":
            continue
        remaining = int(c.get("dividends_remaining", 0))
        if remaining <= 0:
            c["status"] = "completed"
            continue
        issuer = PartyId(c["issuer"])
        investor = PartyId(c["investor"])
        div = int(c["dividend_per_tick_cents"])
        isc = party_cash_account(issuer)
        invc = party_cash_account(investor)
        bal = world.ledger.balance(isc)
        pay = min(div, bal)
        if pay < div:
            if pay > 0:
                world.ledger.transfer(debit=isc, credit=invc, amount_cents=pay)
            c["status"] = "breached"
            r = world.reputation.setdefault(str(issuer), {"honored": 0, "breached": 0})
            r["breached"] += 1
            log_event(
                world,
                "contract_equity_breach",
                f"Equity stub {c['id']}: issuer could not pay full dividend ({pay}/{div}¢)",
                contract_id=c["id"],
            )
            continue
        tr = world.ledger.transfer(debit=isc, credit=invc, amount_cents=div)
        if isinstance(tr, MoneyErr):
            c["status"] = "breached"
            world.reputation.setdefault(str(issuer), {"honored": 0, "breached": 0})["breached"] += 1
            continue
        c["dividends_remaining"] = remaining - 1
        if c["dividends_remaining"] <= 0:
            c["status"] = "completed"
            for pid in (issuer, investor):
                world.reputation.setdefault(str(pid), {"honored": 0, "breached": 0})["honored"] += 1
            log_event(
                world,
                "contract_equity_complete",
                f"Equity stub {c['id']}: dividend schedule finished",
                contract_id=c["id"],
            )
        else:
            log_event(
                world,
                "contract_equity_dividend",
                f"Equity stub {c['id']}: paid {div}¢ dividend",
                contract_id=c["id"],
            )


def propose_service_sub(
    world: World,
    provider: PartyId,
    subscriber: PartyId,
    fee_cents: int,
    duration_ticks: int,
) -> dict:
    if fee_cents <= 0 or duration_ticks < 1:
        return {"ok": False, "reason": "fee and duration must be positive"}
    if provider not in world.parties or subscriber not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if provider == subscriber:
        return {"ok": False, "reason": "provider and subscriber must differ"}
    cid = _next_contract_id(world)
    world.contracts.append(
        {
            "id": cid,
            "kind": "service_sub",
            "status": "proposed",
            "provider": str(provider),
            "subscriber": str(subscriber),
            "fee_cents": fee_cents,
            "duration_ticks": duration_ticks,
            "service_id": "stub_service",
        }
    )
    log_event(
        world,
        "contract_service_propose",
        f"{provider} proposes prepaid service {cid} to {subscriber} ({fee_cents}¢ / {duration_ticks} ticks)",
        contract_id=cid,
    )
    return {"ok": True, "contract_id": cid}


def accept_service_sub(world: World, subscriber: PartyId, contract_id: str) -> dict:
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "service_sub":
            return {"ok": False, "reason": "not a service subscription"}
        if c.get("status") != "proposed":
            return {"ok": False, "reason": "subscription not awaiting acceptance"}
        if PartyId(c["subscriber"]) != subscriber:
            return {"ok": False, "reason": "not the subscriber"}
        provider = PartyId(c["provider"])
        fee = int(c["fee_cents"])
        dur = int(c["duration_ticks"])
        sc = party_cash_account(subscriber)
        pc = party_cash_account(provider)
        tr = world.ledger.transfer(debit=sc, credit=pc, amount_cents=fee)
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}
        c["expires_tick"] = world.tick + dur
        c["status"] = "active"
        log_event(
            world,
            "contract_service_accept",
            f"{subscriber} subscribed {contract_id} until tick {c['expires_tick']}",
            contract_id=contract_id,
        )
        return {"ok": True, "expires_tick": c["expires_tick"]}
    return {"ok": False, "reason": "contract not found"}


def tick_service_subscriptions(world: World) -> None:
    t = world.tick
    for c in world.contracts:
        if c.get("kind") != "service_sub" or c.get("status") != "active":
            continue
        if t <= int(c.get("expires_tick", t)):
            continue
        c["status"] = "expired"
        log_event(
            world,
            "contract_service_expired",
            f"Service sub {c['id']} expired",
            contract_id=c["id"],
        )


def tick_phase2_financial_contracts(world: World) -> None:
    """Run after ``world.tick`` advances (same phase as supply breach checks)."""
    tick_equity_stub(world)
    tick_loan_contracts(world)
    tick_service_subscriptions(world)
    tick_forward_contracts(world)


# ─────────────────── Sprint 4 — Phase C: forward contracts ───────────────────

# Deposit = 10% of total notional value (default skin in the game).
FORWARD_DEPOSIT_BPS: int = 1_000


def _forward_deposit_cents(qty: int, price_per_unit_cents: int) -> int:
    notional = max(0, int(qty)) * max(0, int(price_per_unit_cents))
    return max(1, (notional * FORWARD_DEPOSIT_BPS) // 10_000) if notional > 0 else 0


def propose_forward_contract(
    world: World,
    seller: PartyId,
    buyer: PartyId,
    material: MaterialId,
    qty: int,
    price_per_unit_cents: int,
    delivery_tick: int,
) -> dict:
    """Create a ``proposed`` forward delivery contract (no escrow until accepted).

    Validations on accept (deposit availability). The contract sits as
    ``proposed`` in ``world.contracts`` until the buyer accepts.
    """
    if qty <= 0:
        return {"ok": False, "reason": "qty must be positive"}
    if price_per_unit_cents <= 0:
        return {"ok": False, "reason": "price must be positive"}
    if delivery_tick <= int(world.tick):
        return {"ok": False, "reason": "delivery_tick must be in the future"}
    if seller not in world.parties or buyer not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if seller == buyer:
        return {"ok": False, "reason": "seller and buyer must differ"}
    deposit = _forward_deposit_cents(qty, price_per_unit_cents)
    cid = _next_contract_id(world)
    world.contracts.append(
        {
            "id": cid,
            "kind": "forward_contract",
            "status": "proposed",
            "seller": str(seller),
            "buyer": str(buyer),
            "material": str(material),
            "qty": int(qty),
            "price_per_unit_cents": int(price_per_unit_cents),
            "delivery_tick": int(delivery_tick),
            "deposit_cents": int(deposit),
            "proposed_at_tick": int(world.tick),
        }
    )
    log_event(
        world,
        "contract_forward_propose",
        f"{seller} proposes forward {cid} to {buyer}: "
        f"{qty}×{material} at {price_per_unit_cents}¢/u by tick {delivery_tick} "
        f"(deposit ${deposit / 100:.2f})",
        contract_id=cid,
        seller=str(seller),
        buyer=str(buyer),
        material=str(material),
        qty=int(qty),
        price_per_unit_cents=int(price_per_unit_cents),
        delivery_tick=int(delivery_tick),
        deposit_cents=int(deposit),
    )
    return {"ok": True, "contract_id": cid, "deposit_cents": int(deposit)}


def accept_forward_contract(world: World, buyer: PartyId, contract_id: str) -> dict:
    """Buyer confirms the proposal; seller's deposit moves to system escrow."""
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "forward_contract":
            return {"ok": False, "reason": "not a forward contract"}
        if c.get("status") != "proposed":
            return {"ok": False, "reason": "forward not awaiting acceptance"}
        if PartyId(c["buyer"]) != buyer:
            return {"ok": False, "reason": "not the buyer on this forward"}
        seller = PartyId(c["seller"])
        deposit = int(c.get("deposit_cents", 0))
        if deposit > 0:
            sc = party_cash_account(seller)
            world.ledger.ensure_account(sc)
            if world.ledger.balance(sc) < deposit:
                return {"ok": False, "reason": "seller cannot post deposit"}
            tr = world.ledger.transfer(
                debit=sc,
                credit=system_reserve_account(),
                amount_cents=deposit,
            )
            if isinstance(tr, MoneyErr):
                return {"ok": False, "reason": tr.reason}
        c["status"] = "active"
        c["accepted_at_tick"] = int(world.tick)
        log_event(
            world,
            "contract_forward_accept",
            f"{buyer} accepted forward {contract_id} ({c['qty']}×{c['material']} "
            f"by tick {c['delivery_tick']}; deposit ${deposit / 100:.2f} escrowed)",
            contract_id=contract_id,
            buyer=str(buyer),
            seller=str(seller),
            deposit_cents=int(deposit),
        )
        return {"ok": True, "deposit_cents": int(deposit), "delivery_tick": int(c["delivery_tick"])}
    return {"ok": False, "reason": "contract not found"}


def deliver_forward_contract(world: World, seller: PartyId, contract_id: str) -> dict:
    """Seller fulfils the forward — goods + payment + deposit release, all atomic."""
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "forward_contract":
            return {"ok": False, "reason": "not a forward contract"}
        if c.get("status") != "active":
            return {"ok": False, "reason": "forward not active"}
        if PartyId(c["seller"]) != seller:
            return {"ok": False, "reason": "not the seller on this forward"}
        buyer = PartyId(c["buyer"])
        material = MaterialId(str(c["material"]))
        qty = int(c["qty"])
        unit_px = int(c["price_per_unit_cents"])
        payment = qty * unit_px
        deposit = int(c.get("deposit_cents", 0))
        if world.inventory.qty(seller, material) < qty:
            return {"ok": False, "reason": "insufficient material to deliver"}
        bc = party_cash_account(buyer)
        sc = party_cash_account(seller)
        world.ledger.ensure_account(bc)
        world.ledger.ensure_account(sc)
        if world.ledger.balance(bc) < payment:
            return {"ok": False, "reason": "buyer cannot pay locked price"}
        # Move materials first.
        mv = world.inventory.transfer(
            material=material, qty=qty, from_party=seller, to_party=buyer
        )
        if isinstance(mv, MatterErr):
            return {"ok": False, "reason": mv.reason}
        # Buyer pays at locked price.
        pay = world.ledger.transfer(debit=bc, credit=sc, amount_cents=payment)
        if isinstance(pay, MoneyErr):
            world.inventory.transfer(
                material=material, qty=qty, from_party=buyer, to_party=seller
            )
            return {"ok": False, "reason": pay.reason}
        # Release deposit back to seller.
        if deposit > 0:
            ret = world.ledger.transfer(
                debit=system_reserve_account(),
                credit=sc,
                amount_cents=deposit,
            )
            if isinstance(ret, MoneyErr):
                return {"ok": False, "reason": ret.reason}
        c["status"] = "delivered"
        c["delivered_at_tick"] = int(world.tick)
        for pid in (seller, buyer):
            r = world.reputation.setdefault(str(pid), {"honored": 0, "breached": 0})
            r["honored"] += 1
        log_event(
            world,
            "contract_forward_delivered",
            f"Forward {contract_id} delivered: {qty}×{material} @ {unit_px}¢/u "
            f"(payment ${payment / 100:.2f}, deposit ${deposit / 100:.2f} released)",
            contract_id=contract_id,
            seller=str(seller),
            buyer=str(buyer),
            material=str(material),
            qty=qty,
            payment_cents=payment,
            deposit_cents=deposit,
        )
        return {"ok": True, "payment_cents": payment, "deposit_cents": deposit}
    return {"ok": False, "reason": "contract not found"}


def tick_forward_contracts(world: World) -> None:
    """Default any active forwards whose delivery_tick has passed."""
    t = int(world.tick)
    for c in world.contracts:
        if c.get("kind") != "forward_contract":
            continue
        if c.get("status") != "active":
            continue
        if t <= int(c.get("delivery_tick", t)):
            continue
        seller = PartyId(c["seller"])
        buyer = PartyId(c["buyer"])
        deposit = int(c.get("deposit_cents", 0))
        bc = party_cash_account(buyer)
        world.ledger.ensure_account(bc)
        if deposit > 0:
            world.ledger.transfer(
                debit=system_reserve_account(),
                credit=bc,
                amount_cents=deposit,
            )
        c["status"] = "defaulted"
        c["defaulted_at_tick"] = int(world.tick)
        rs = world.reputation.setdefault(str(seller), {"honored": 0, "breached": 0})
        rs["breached"] += 1
        rb = world.reputation.setdefault(str(buyer), {"honored": 0, "breached": 0})
        rb["honored"] = int(rb.get("honored", 0))
        log_event(
            world,
            "contract_forward_default",
            f"Forward {c['id']}: seller {seller} missed delivery by tick {c['delivery_tick']} "
            f"— deposit ${deposit / 100:.2f} forfeited to {buyer}.",
            contract_id=c["id"],
            seller=str(seller),
            buyer=str(buyer),
            deposit_cents=deposit,
        )
        log_event(
            world,
            "world_feed",
            f"Forward contract {c['id']}: {seller} defaulted on {c['qty']}×{c['material']} delivery — "
            f"buyer {buyer} collected the escrowed deposit.",
            feed_source="forward_default",
            seller=str(seller),
            buyer=str(buyer),
            material=str(c["material"]),
        )
