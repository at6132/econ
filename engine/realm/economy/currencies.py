"""Player-issued currency materials backed by ledger reserves."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from realm.economy.business_requirements import (
    BANK_MAX_CURRENCY_SUPPLY_MULTIPLE,
    BANK_MIN_RESERVE_RATIO,
)
from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, named_reserve_account, party_cash_account
from realm.materials import register_currency_material
from realm.world import World


@dataclass
class IssuedCurrency:
    currency_id: str
    symbol: str
    name: str
    issuer_party: str
    business_id: str
    material_id: str
    reserve_ratio: float
    total_issued: int = 0
    reserve_cents: int = 0
    created_at_tick: int = 0
    status: str = "active"


def _reserve_acct(currency_id: str) -> Any:
    return named_reserve_account(f"currency:{currency_id}")


def create_currency(
    world: World,
    bank_party: PartyId,
    business_id: str,
    symbol: str,
    name: str,
    reserve_ratio: float = 0.20,
) -> dict[str, Any]:
    if not (0.10 <= float(reserve_ratio) <= 1.0):
        return {"ok": False, "reason": "reserve_ratio must be 0.10–1.00"}
    if business_id not in world.businesses:
        return {"ok": False, "reason": "unknown business_id"}
    biz = world.businesses[business_id]
    if str(biz.business_type_tag) != "banking":
        return {"ok": False, "reason": "only bank businesses can issue currency"}
    if PartyId(str(biz.owner_party)) != bank_party:
        return {"ok": False, "reason": "not your bank"}
    sym = symbol.upper().strip()
    if not sym.isalpha() or not (2 <= len(sym) <= 6):
        return {"ok": False, "reason": "symbol must be 2–6 letters"}
    existing = {c.symbol for c in world.issued_currencies.values()}
    if sym in existing:
        return {"ok": False, "reason": f"symbol {sym} already taken"}
    currency_id = f"curr_{business_id}_{sym.lower()}"
    material_id_s = f"currency_{sym.lower()}"
    mid = MaterialId(material_id_s)
    register_currency_material(mid, name)
    world.issued_currencies[currency_id] = IssuedCurrency(
        currency_id=currency_id,
        symbol=sym,
        name=name,
        issuer_party=str(bank_party),
        business_id=business_id,
        material_id=material_id_s,
        reserve_ratio=float(reserve_ratio),
        created_at_tick=int(world.tick),
        status="active",
    )
    log_event(
        world,
        "currency_created",
        f"{bank_party} established {name} ({sym})",
        currency_id=currency_id,
        symbol=sym,
        business_id=business_id,
    )
    world.world_feed_log.append(
        {
            "tick": int(world.tick),
            "kind": "world_feed",
            "message": f"A new currency was issued: {name} ({sym}) by {world.party_display_names.get(str(bank_party), str(bank_party))}.",
        }
    )
    return {"ok": True, "currency_id": currency_id, "material_id": material_id_s}


def mint_currency(world: World, bank_party: PartyId, currency_id: str, amount: int) -> dict[str, Any]:
    curr = world.issued_currencies.get(currency_id)
    if curr is None:
        return {"ok": False, "reason": "unknown currency"}
    if curr.issuer_party != str(bank_party):
        return {"ok": False, "reason": "not your currency"}
    if curr.status != "active":
        return {"ok": False, "reason": "currency is not active"}
    if amount <= 0:
        return {"ok": False, "reason": "amount must be positive"}
    reserve_needed = max(1, int(int(amount) * float(curr.reserve_ratio)))
    bank_cash = party_cash_account(bank_party)
    if world.ledger.balance(bank_cash) < reserve_needed:
        return {"ok": False, "reason": f"insufficient reserves: need {reserve_needed}¢ locked"}
    proj_total = int(curr.total_issued) + int(amount)
    proj_res = int(curr.reserve_cents) + int(reserve_needed)
    if proj_total > BANK_MAX_CURRENCY_SUPPLY_MULTIPLE * proj_res:
        return {"ok": False, "reason": "currency supply cap reached for current reserves"}
    ra = _reserve_acct(currency_id)
    tr = world.ledger.transfer(debit=bank_cash, credit=ra, amount_cents=reserve_needed)
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    mat = MaterialId(curr.material_id)
    ad = world.inventory.add(bank_party, mat, int(amount))
    if isinstance(ad, MatterErr):
        world.ledger.transfer(debit=ra, credit=bank_cash, amount_cents=reserve_needed)
        return {"ok": False, "reason": ad.reason}
    curr.total_issued += int(amount)
    curr.reserve_cents += int(reserve_needed)
    log_event(
        world,
        "currency_minted",
        f"{bank_party} minted {amount} {curr.symbol}",
        currency_id=currency_id,
        amount=int(amount),
        reserve_locked=reserve_needed,
    )
    return {"ok": True, "minted": int(amount), "reserve_locked": reserve_needed}


def redeem_currency(world: World, holder: PartyId, currency_id: str, amount: int) -> dict[str, Any]:
    curr = world.issued_currencies.get(currency_id)
    if curr is None:
        return {"ok": False, "reason": "unknown currency"}
    mat = MaterialId(curr.material_id)
    if world.inventory.qty(holder, mat) < int(amount):
        return {"ok": False, "reason": "insufficient currency to redeem"}
    if curr.total_issued <= 0:
        return {"ok": False, "reason": "no currency in circulation"}
    redemption_rate = float(curr.reserve_cents) / float(curr.total_issued)
    payout = int(int(amount) * redemption_rate)
    rm = world.inventory.remove(holder, mat, int(amount))
    if isinstance(rm, MatterErr):
        return {"ok": False, "reason": rm.reason}
    curr.total_issued -= int(amount)
    ra = _reserve_acct(currency_id)
    if payout > 0:
        tr = world.ledger.transfer(debit=ra, credit=party_cash_account(holder), amount_cents=payout)
        if isinstance(tr, MoneyErr):
            world.inventory.add(holder, mat, int(amount))
            curr.total_issued += int(amount)
            return {"ok": False, "reason": tr.reason}
        curr.reserve_cents -= int(payout)
    log_event(
        world,
        "currency_redeemed",
        f"{holder} redeemed {amount} {curr.symbol} for {payout}¢",
        currency_id=currency_id,
        amount=int(amount),
        payout_cents=payout,
    )
    return {"ok": True, "payout_cents": payout, "redemption_rate": redemption_rate}


def tick_bank_reserves(world: World) -> None:
    if int(world.tick) <= 0 or int(world.tick) % 1440 != 0:
        return
    for curr in world.issued_currencies.values():
        if curr.status != "active" or int(curr.total_issued) <= 0:
            continue
        actual = float(curr.reserve_cents) / float(curr.total_issued)
        if actual < BANK_MIN_RESERVE_RATIO:
            curr.status = "suspended"
            log_event(
                world,
                "bank_under_capitalized",
                f"{curr.name} ({curr.symbol}) under-reserved at {actual:.1%}",
                currency_id=curr.currency_id,
            )
            world.world_feed_log.append(
                {
                    "tick": int(world.tick),
                    "kind": "world_feed",
                    "message": (
                        f"BANKING ALERT: {curr.name} ({curr.symbol}) is under-reserved. "
                        "Redemptions may be limited."
                    ),
                }
            )
