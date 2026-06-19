"""Public company share offerings (IPO-style) on the frontier."""

from __future__ import annotations

from typing import Any, Final

from realm.core.ids import PartyId
from realm.core.ledger import MoneyErr, party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.corporations.company import Company, company_cash_account, get_company, store_company
from realm.economy.market_feed import feed_company_ipo, party_market_label
from realm.events.event_log import log_event
from realm.world import World

_OFFERING_DURATION_TICKS: Final[int] = 14 * TICKS_PER_GAME_DAY
_MIN_IPO_SHARES: Final[int] = 50
_MAX_IPO_SHARES: Final[int] = 200


def _offerings_store(world: World) -> list[dict[str, Any]]:
    raw = world.scenario_state.setdefault("equity_offerings", [])
    if not isinstance(raw, list):
        raw = []
        world.scenario_state["equity_offerings"] = raw
    return raw


def _next_offering_id(world: World) -> str:
    st = world.scenario_state.setdefault("corporations", {})
    if not isinstance(st, dict):
        st = {}
        world.scenario_state["corporations"] = st
    seq = int(st.get("next_equity_offering_seq", 1))
    st["next_equity_offering_seq"] = seq + 1
    return f"ipo-{seq:04d}"


def list_open_equity_offerings(world: World) -> list[dict[str, Any]]:
    now = int(world.tick)
    out: list[dict[str, Any]] = []
    for row in _offerings_store(world):
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "")) != "open":
            continue
        if now > int(row.get("expires_at_tick", 0)):
            continue
        remaining = int(row.get("shares_remaining", 0))
        if remaining <= 0:
            continue
        out.append(dict(row))
    return out


def _valuation_cents_per_share(world: World, company: Company) -> int:
    cash = world.ledger.balance(company_cash_account(company.company_id))
    plot_bonus = len(company.managed_plots) * 25_000
    total = max(100_000, cash + plot_bonus)
    shares = max(1, int(company.total_shares))
    return max(100, total // shares)


def schedule_company_ipo(world: World, company: Company, seller: PartyId) -> dict[str, Any]:
    """Founding partner lists a slice of their shares after company formation."""
    seller_s = str(seller)
    held = int(company.share_registry.get(seller_s, 0))
    if held < _MIN_IPO_SHARES * 2:
        return {"ok": False, "reason": "insufficient founder shares"}
    for row in _offerings_store(world):
        if (
            isinstance(row, dict)
            and str(row.get("company_id", "")) == company.company_id
            and str(row.get("status", "")) == "open"
        ):
            return {"ok": False, "reason": "open offering already exists"}

    shares = min(_MAX_IPO_SHARES, max(_MIN_IPO_SHARES, held // 4))
    px = _valuation_cents_per_share(world, company)
    oid = _next_offering_id(world)
    record = {
        "offering_id": oid,
        "company_id": company.company_id,
        "company_name": company.name,
        "seller_party": seller_s,
        "shares_remaining": int(shares),
        "shares_total": int(shares),
        "price_cents_per_share": int(px),
        "posted_at_tick": int(world.tick),
        "expires_at_tick": int(world.tick) + _OFFERING_DURATION_TICKS,
        "status": "open",
    }
    _offerings_store(world).append(record)
    feed_company_ipo(
        world,
        company_id=company.company_id,
        company_name=company.name,
        seller=seller,
        shares=shares,
        price_cents_per_share=px,
        offering_id=oid,
    )
    log_event(
        world,
        "equity_offering_posted",
        f"{company.name} IPO {oid}: {shares} shares @ {px}¢ from {seller_s}",
        offering_id=oid,
        company_id=company.company_id,
        seller=seller_s,
        shares=int(shares),
        price_cents_per_share=int(px),
    )
    return {"ok": True, "offering_id": oid}


def accept_equity_offering(
    world: World,
    buyer: PartyId,
    offering_id: str,
    shares: int,
) -> dict[str, Any]:
    if int(shares) <= 0:
        return {"ok": False, "reason": "shares must be positive"}
    row = next(
        (r for r in _offerings_store(world) if isinstance(r, dict) and str(r.get("offering_id")) == offering_id),
        None,
    )
    if row is None:
        return {"ok": False, "reason": "offering not found"}
    if str(row.get("status", "")) != "open":
        return {"ok": False, "reason": "offering not open"}
    if int(world.tick) > int(row.get("expires_at_tick", 0)):
        row["status"] = "expired"
        return {"ok": False, "reason": "offering expired"}
    remaining = int(row.get("shares_remaining", 0))
    if int(shares) > remaining:
        return {"ok": False, "reason": "not enough shares remaining"}

    company = get_company(world, str(row["company_id"]))
    if company is None:
        return {"ok": False, "reason": "company missing"}
    seller = PartyId(str(row["seller_party"]))
    if buyer == seller:
        return {"ok": False, "reason": "cannot buy your own offering"}
    if buyer not in world.parties:
        return {"ok": False, "reason": "unknown buyer"}

    seller_held = int(company.share_registry.get(str(seller), 0))
    if seller_held < int(shares):
        return {"ok": False, "reason": "seller no longer holds those shares"}

    px = int(row["price_cents_per_share"])
    total = int(shares) * px
    tr = world.ledger.transfer(
        debit=party_cash_account(buyer),
        credit=party_cash_account(seller),
        amount_cents=total,
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}

    company.share_registry[str(seller)] = seller_held - int(shares)
    company.share_registry[str(buyer)] = int(company.share_registry.get(str(buyer), 0)) + int(shares)
    store_company(world, company)
    row["shares_remaining"] = remaining - int(shares)
    if int(row["shares_remaining"]) <= 0:
        row["status"] = "filled"

    buyer_n = party_market_label(world, buyer)
    log_event(
        world,
        "equity_offering_filled",
        f"{buyer_n} bought {shares} shares of {company.name} @ {px}¢/share ({offering_id})",
        offering_id=offering_id,
        buyer=str(buyer),
        seller=str(seller),
        company_id=company.company_id,
        shares=int(shares),
        price_cents_per_share=int(px),
    )
    log_event(
        world,
        "world_feed",
        f"{buyer_n} bought {shares} shares of {company.name} @ {px}¢/share.",
        feed_source="equity_fill",
        offering_id=offering_id,
        buyer=str(buyer),
        company_id=company.company_id,
        shares=int(shares),
    )
    return {"ok": True, "offering_id": offering_id, "shares": int(shares), "spent_cents": total}


def tick_equity_offerings(world: World) -> None:
    """Expire stale offerings; NPC investors occasionally take open IPO slices."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return

    now = int(world.tick)
    for row in _offerings_store(world):
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "")) != "open":
            continue
        if now > int(row.get("expires_at_tick", 0)):
            row["status"] = "expired"
            continue
        remaining = int(row.get("shares_remaining", 0))
        if remaining <= 0:
            row["status"] = "filled"
            continue

        seller = PartyId(str(row["seller_party"]))
        px = int(row["price_cents_per_share"])
        slice_shares = min(remaining, max(10, remaining // 3))
        candidates = [
            p
            for p in sorted(world.parties, key=str)
            if str(p).startswith("settler_")
            and p != seller
            and world.ledger.balance(party_cash_account(p)) >= slice_shares * px + 50_000
        ]
        if not candidates:
            continue
        day = now // TICKS_PER_GAME_DAY
        buyer = candidates[(day + hash(str(row.get("offering_id")))) % len(candidates)]
        rng = world.rng(f"ipo-accept:{row.get('offering_id')}:{day}")
        if rng.random() > 0.55:
            continue
        accept_equity_offering(world, buyer, str(row["offering_id"]), slice_shares)


__all__ = [
    "list_open_equity_offerings",
    "schedule_company_ipo",
    "accept_equity_offering",
    "tick_equity_offerings",
]
