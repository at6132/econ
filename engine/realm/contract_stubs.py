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
"""

from __future__ import annotations

from realm.event_log import log_event
from realm.ids import PartyId
from realm.ledger import MoneyErr, party_cash_account
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
