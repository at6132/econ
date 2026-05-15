"""Profit-linked equity stakes (Phase 10+)."""

from __future__ import annotations

from realm.events.event_log import log_event
from realm.core.ids import PartyId
from realm.core.ledger import MoneyErr, business_cash_account, party_cash_account
from realm.population.laborers import TICKS_PER_GAME_DAY
from realm.world import World


MIN_BUSINESS_DISTRIBUTABLE_RESERVE_CENTS: int = 20_000


def _equity_bps_committed(world: World, business_id: str) -> int:
    total = 0
    for c in world.contracts:
        if str(c.get("kind", "")) != "equity_stake":
            continue
        if str(c.get("business_id", "")) != str(business_id):
            continue
        if str(c.get("status", "")) not in ("active", "proposed"):
            continue
        total += int(c.get("ownership_pct_bps", 0))
    return total


def propose_equity_stake(
    world: World,
    issuer: PartyId,
    investor: PartyId,
    business_id: str,
    ownership_pct_bps: int,
    investment_cents: int,
) -> dict:
    if ownership_pct_bps <= 0 or ownership_pct_bps >= 10_000:
        return {"ok": False, "reason": "ownership_pct_bps must be 1–9999 (0.01%–99.99%)"}
    if investment_cents <= 0:
        return {"ok": False, "reason": "investment must be positive"}
    if business_id not in world.businesses:
        return {"ok": False, "reason": "unknown business_id"}
    biz = world.businesses[business_id]
    if PartyId(str(biz.owner_party)) != issuer:
        return {"ok": False, "reason": "not your business"}
    if issuer not in world.parties or investor not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if issuer == investor:
        return {"ok": False, "reason": "issuer and investor must differ"}
    if _equity_bps_committed(world, business_id) + int(ownership_pct_bps) >= 10_000:
        return {"ok": False, "reason": "total equity would reach or exceed 100%"}
    world.next_contract_seq += 1
    cid = f"c-{world.next_contract_seq}"
    world.contracts.append(
        {
            "id": cid,
            "kind": "equity_stake",
            "status": "proposed",
            "issuer": str(issuer),
            "investor": str(investor),
            "business_id": str(business_id),
            "ownership_pct_bps": int(ownership_pct_bps),
            "investment_cents": int(investment_cents),
            "proposed_at_tick": int(world.tick),
        }
    )
    log_event(
        world,
        "contract_equity_stake_propose",
        f"{issuer} proposes equity stake {cid} on {business_id}",
        contract_id=cid,
        business_id=str(business_id),
        ownership_pct_bps=int(ownership_pct_bps),
        investment_cents=int(investment_cents),
    )
    return {"ok": True, "contract_id": cid}


def accept_equity_stake(world: World, investor: PartyId, contract_id: str) -> dict:
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "equity_stake":
            return {"ok": False, "reason": "not an equity stake contract"}
        if c.get("status") != "proposed":
            return {"ok": False, "reason": "equity stake not awaiting acceptance"}
        if PartyId(c["investor"]) != investor:
            return {"ok": False, "reason": "not the investor on this contract"}
        issuer = PartyId(c["issuer"])
        bid = str(c["business_id"])
        if bid not in world.businesses:
            return {"ok": False, "reason": "unknown business_id"}
        biz = world.businesses[bid]
        if PartyId(str(biz.owner_party)) != issuer:
            return {"ok": False, "reason": "issuer no longer owns this business"}
        cur_bps = int(c["ownership_pct_bps"])
        other = 0
        for x in world.contracts:
            if str(x.get("kind", "")) != "equity_stake":
                continue
            if str(x.get("business_id", "")) != bid:
                continue
            if str(x.get("id", "")) == str(contract_id):
                continue
            if str(x.get("status", "")) not in ("active", "proposed"):
                continue
            other += int(x.get("ownership_pct_bps", 0))
        if other + cur_bps >= 10_000:
            return {"ok": False, "reason": "total equity would reach or exceed 100%"}
        inv_amt = int(c["investment_cents"])
        ic = party_cash_account(investor)
        isc = party_cash_account(issuer)
        tr = world.ledger.transfer(debit=ic, credit=isc, amount_cents=inv_amt)
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}
        c["status"] = "active"
        if contract_id not in biz.equity_contract_ids:
            biz.equity_contract_ids.append(contract_id)
        log_event(
            world,
            "contract_equity_stake_accept",
            f"{investor} funded equity stake {contract_id}",
            contract_id=contract_id,
            business_id=bid,
        )
        return {"ok": True}
    return {"ok": False, "reason": "contract not found"}


def tick_equity_stakes(world: World) -> None:
    """Each game-day: distribute a share of business cash above reserve to investors."""
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return
    for c in world.contracts:
        if c.get("kind") != "equity_stake" or c.get("status") != "active":
            continue
        bid = str(c.get("business_id", ""))
        if bid not in world.businesses:
            continue
        biz = world.businesses[bid]
        pct_bps = int(c.get("ownership_pct_bps", 0))
        if pct_bps <= 0:
            continue
        investor = PartyId(str(c["investor"]))
        src = business_cash_account(bid)
        dst = party_cash_account(investor)
        world.ledger.ensure_account(src)
        bal = world.ledger.balance(src)
        distributable = max(0, int(bal) - MIN_BUSINESS_DISTRIBUTABLE_RESERVE_CENTS)
        dividend = (distributable * pct_bps) // 10_000
        if dividend <= 0:
            continue
        tr = world.ledger.transfer(debit=src, credit=dst, amount_cents=dividend)
        if isinstance(tr, MoneyErr):
            log_event(
                world,
                "contract_equity_stake_shortfall",
                f"Equity stake {c['id']}: could not pay dividend ({tr.reason})",
                contract_id=str(c["id"]),
            )
            continue
        log_event(
            world,
            "equity_dividend_paid",
            f"Equity stake {c['id']}: {dividend}¢ to {investor} ({pct_bps} bps of {biz.business_name} cash)",
            contract_id=str(c["id"]),
            investor=str(investor),
            dividend_cents=dividend,
            ownership_pct_bps=pct_bps,
        )
