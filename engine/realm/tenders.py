"""Open supply tenders — buyers post, suppliers bid, lowest wins (Sprint 2 — Phase C).

A tender is a public RFQ: a buyer publishes a need (material, quantity per
cycle, interval, duration), a bidding window opens, suppliers submit price
quotes, and at the bid deadline the lowest bid is awarded a SupplyContract
covering the full duration.

State (JSON-safe; lives under ``scenario_state["tenders"]``):

    {
        "next_seq": int,
        "list": [
            {
                "id": "t-1",
                "kind": "supply_tender",
                "posted_by": <party_id>,
                "material": <material_id>,
                "qty_per_cycle": int,
                "interval_ticks": int,
                "duration_cycles": int,
                "bid_deadline_tick": int,
                "posted_at_tick": int,
                "bids": [
                    {"bidder": ..., "price_per_unit_cents": int,
                     "submitted_at_tick": int},
                    ...
                ],
                "awarded_to": <party_id> | None,
                "awarded_price_per_unit_cents": int | None,
                "awarded_contract_id": str | None,
                "status": "open" | "awarded" | "expired",
            },
            ...
        ],
    }

Settlers consult the open tenders each game-day and bid on any whose implied
price beats their own cost basis by ``SETTLER_TENDER_BID_RATIO_BPS``. (Phase 7
removed the automated ``tick_hub_tender_posting`` that used the deleted
``pop_hub_e/w`` parties; tenders are now posted directly by entrepreneurs.)
"""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.genesis_pricing import exchange_ask_cents, hub_max_bid_cents
from realm.ids import MaterialId, PartyId
from realm.settler_cost_basis import (
    settler_output_basis_cents,
)
from realm.social import propose_supply_contract, accept_supply_contract
from realm.world import World


__all__ = [
    "ensure_tender_state",
    "post_tender",
    "submit_tender_bid",
    "tick_tender_lifecycle",
    "tick_settler_tender_bidding",
    "list_open_tenders",
    "list_all_tenders",
    "tender_by_id",
    "TENDER_BID_WINDOW_TICKS",
    "TENDER_DURATION_CYCLES",
    "TENDER_INTERVAL_PER_CYCLE_TICKS",
    "SETTLER_TENDER_BID_THRESHOLD_BPS",
    "SETTLER_TENDER_BID_MARGIN_BPS",
]


# ───────────────────────── tunables ─────────────────────────


TENDER_BID_WINDOW_TICKS: int = 1440  # default 24 game-hours open for bidding
TENDER_DURATION_CYCLES: int = 30  # default 30 cycles per awarded contract
TENDER_INTERVAL_PER_CYCLE_TICKS: int = 1440  # default 1 game-day per cycle

# Settler bidding heuristics.
SETTLER_TENDER_BID_THRESHOLD_BPS: int = 13_500  # bid when implied price > basis × 1.35
SETTLER_TENDER_BID_MARGIN_BPS: int = 12_500  # bid at basis × 1.25

# Phase 7: ``_HUB_TENDER_BASKET`` and ``tick_hub_tender_posting`` were removed
# along with ``pop_hub_e/w``. Entrepreneur NPCs and the player post tenders
# directly via ``post_tender`` when they need a multi-cycle supply commitment.


# ───────────────────────── state ─────────────────────────


def ensure_tender_state(world: World) -> dict[str, Any]:
    """Get-or-create ``scenario_state["tenders"]`` and its sub-fields."""
    state = world.scenario_state.setdefault("tenders", {})
    state.setdefault("next_seq", 0)
    state.setdefault("list", [])
    return state


def _next_tender_id(world: World) -> str:
    state = ensure_tender_state(world)
    state["next_seq"] = int(state.get("next_seq", 0)) + 1
    return f"t-{state['next_seq']}"


# ───────────────────────── core API ─────────────────────────


def post_tender(
    world: World,
    *,
    posted_by: PartyId,
    material: MaterialId,
    qty_per_cycle: int,
    interval_ticks: int,
    duration_cycles: int,
    bid_window_ticks: int,
) -> dict[str, Any]:
    """Publish a new open tender; returns ``{"ok": True, "tender_id": ...}``."""
    if int(qty_per_cycle) <= 0:
        return {"ok": False, "reason": "qty_per_cycle must be positive"}
    if int(interval_ticks) <= 0:
        return {"ok": False, "reason": "interval_ticks must be positive"}
    if int(duration_cycles) <= 0:
        return {"ok": False, "reason": "duration_cycles must be positive"}
    if int(bid_window_ticks) <= 0:
        return {"ok": False, "reason": "bid_window_ticks must be positive"}
    if posted_by not in world.parties:
        return {"ok": False, "reason": "unknown posting party"}
    state = ensure_tender_state(world)
    tid = _next_tender_id(world)
    record = {
        "id": tid,
        "kind": "supply_tender",
        "posted_by": str(posted_by),
        "material": str(material),
        "qty_per_cycle": int(qty_per_cycle),
        "interval_ticks": int(interval_ticks),
        "duration_cycles": int(duration_cycles),
        "bid_deadline_tick": int(world.tick) + int(bid_window_ticks),
        "posted_at_tick": int(world.tick),
        "bids": [],
        "awarded_to": None,
        "awarded_price_per_unit_cents": None,
        "awarded_contract_id": None,
        "status": "open",
    }
    state["list"].append(record)
    log_event(
        world,
        "tender_posted",
        f"{posted_by} posted tender {tid}: {qty_per_cycle}×{material}/cycle × {duration_cycles} cycles",
        tender_id=tid,
        posted_by=str(posted_by),
        material=str(material),
        qty_per_cycle=int(qty_per_cycle),
        duration_cycles=int(duration_cycles),
        bid_deadline_tick=int(record["bid_deadline_tick"]),
    )
    return {"ok": True, "tender_id": tid, "bid_deadline_tick": int(record["bid_deadline_tick"])}


def tender_by_id(world: World, tender_id: str) -> dict[str, Any] | None:
    state = world.scenario_state.get("tenders") or {}
    for t in state.get("list") or []:
        if str(t.get("id")) == str(tender_id):
            return t
    return None


def list_open_tenders(world: World) -> list[dict[str, Any]]:
    state = world.scenario_state.get("tenders") or {}
    return [t for t in (state.get("list") or []) if t.get("status") == "open"]


def list_all_tenders(world: World) -> list[dict[str, Any]]:
    state = world.scenario_state.get("tenders") or {}
    return list(state.get("list") or [])


def submit_tender_bid(
    world: World,
    bidder: PartyId,
    tender_id: str,
    price_per_unit_cents: int,
) -> dict[str, Any]:
    """Submit (or revise) a bid on an open tender.

    A bidder is *not* required to hold inventory at submission — the awarded
    SupplyContract obligates them to deliver by its ``deliver_by_tick``, but
    they may produce/buy in between. Multiple submissions overwrite the
    bidder's previous entry (price revision).
    """
    if int(price_per_unit_cents) < 1:
        return {"ok": False, "reason": "price_per_unit_cents must be >= 1"}
    if bidder not in world.parties:
        return {"ok": False, "reason": "unknown bidder"}
    record = tender_by_id(world, tender_id)
    if record is None:
        return {"ok": False, "reason": "tender not found"}
    if record.get("status") != "open":
        return {"ok": False, "reason": "tender not open"}
    if str(record.get("posted_by")) == str(bidder):
        return {"ok": False, "reason": "cannot bid on your own tender"}
    if int(world.tick) > int(record.get("bid_deadline_tick", 0)):
        return {"ok": False, "reason": "bid deadline passed"}
    bids: list[dict[str, Any]] = record.setdefault("bids", [])
    bids[:] = [b for b in bids if str(b.get("bidder")) != str(bidder)]
    bids.append(
        {
            "bidder": str(bidder),
            "price_per_unit_cents": int(price_per_unit_cents),
            "submitted_at_tick": int(world.tick),
        }
    )
    log_event(
        world,
        "tender_bid_submitted",
        f"{bidder} bid {price_per_unit_cents}¢/unit on {tender_id}",
        tender_id=str(tender_id),
        bidder=str(bidder),
        price_per_unit_cents=int(price_per_unit_cents),
    )
    return {"ok": True, "tender_id": str(tender_id)}


def _award_tender(world: World, record: dict[str, Any]) -> None:
    """Award the lowest-priced bid and create a SupplyContract for the full duration."""
    bids = list(record.get("bids") or [])
    if not bids:
        record["status"] = "expired"
        log_event(
            world,
            "tender_expired",
            f"Tender {record.get('id')} expired with no bids",
            tender_id=str(record.get("id")),
            posted_by=str(record.get("posted_by")),
        )
        return
    bids.sort(key=lambda b: (int(b.get("price_per_unit_cents", 0)), int(b.get("submitted_at_tick", 0))))
    winner = bids[0]
    winner_party = PartyId(str(winner["bidder"]))
    price = int(winner["price_per_unit_cents"])
    qty_per_cycle = int(record.get("qty_per_cycle", 0))
    duration_cycles = int(record.get("duration_cycles", 1))
    interval = int(record.get("interval_ticks", TENDER_INTERVAL_PER_CYCLE_TICKS))
    total_qty = qty_per_cycle * duration_cycles
    total_price = price * total_qty
    deliver_in_ticks = max(1, interval * duration_cycles)
    proposal = propose_supply_contract(
        world,
        supplier=winner_party,
        buyer=PartyId(str(record["posted_by"])),
        material=MaterialId(str(record["material"])),
        qty=total_qty,
        total_price_cents=total_price,
        due_in_ticks=deliver_in_ticks,
    )
    if not proposal.get("ok"):
        record["status"] = "expired"
        log_event(
            world,
            "tender_award_failed",
            f"Tender {record.get('id')} could not be awarded: {proposal.get('reason')}",
            tender_id=str(record.get("id")),
            reason=str(proposal.get("reason")),
        )
        return
    cid = str(proposal["contract_id"])
    # Auto-accept on the buyer's behalf so the contract goes active immediately.
    accept = accept_supply_contract(world, PartyId(str(record["posted_by"])), cid)
    if not accept.get("ok"):
        record["status"] = "expired"
        log_event(
            world,
            "tender_award_failed",
            f"Tender {record.get('id')} buyer failed to accept: {accept.get('reason')}",
            tender_id=str(record.get("id")),
            reason=str(accept.get("reason")),
        )
        return
    record["status"] = "awarded"
    record["awarded_to"] = str(winner_party)
    record["awarded_price_per_unit_cents"] = price
    record["awarded_contract_id"] = cid
    log_event(
        world,
        "tender_awarded",
        f"Tender {record.get('id')} → {winner_party} @ {price}¢/unit (contract {cid})",
        tender_id=str(record.get("id")),
        winner=str(winner_party),
        price_per_unit_cents=price,
        contract_id=cid,
    )


def tick_tender_lifecycle(world: World) -> None:
    """Award any open tender whose ``bid_deadline_tick`` has passed."""
    state = world.scenario_state.get("tenders")
    if not state:
        return
    for record in state.get("list") or []:
        if record.get("status") != "open":
            continue
        if int(world.tick) <= int(record.get("bid_deadline_tick", 0)):
            continue
        _award_tender(world, record)


# ───────────────────────── settler bidding ─────────────────────────


def _settler_implied_tender_price(world: World, material: MaterialId) -> int:
    """Implied per-unit price for a tender. Default proxy: hub max bid."""
    proxy = hub_max_bid_cents(material)
    if proxy and proxy > 0:
        return int(proxy)
    return max(1, int(exchange_ask_cents(material, world=world)) * 92 // 100)


def tick_settler_tender_bidding(world: World) -> None:
    """Daily: each settler considers each open tender for a material they produce.

    The settler bids when ``implied_price > own_cost_basis × 1.35`` and submits
    a quote at ``own_cost_basis × 1.25``. Settlers without a recorded basis
    skip (they can't size a confident bid).
    """
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0:
        return
    if int(world.tick) % 1440 != 0:
        return
    open_tenders = list_open_tenders(world)
    if not open_tenders:
        return
    settlers = sorted(
        (p for p in world.parties if str(p).startswith("settler_")), key=str
    )
    for record in open_tenders:
        mid = MaterialId(str(record.get("material")))
        implied = _settler_implied_tender_price(world, mid)
        for party in settlers:
            basis = settler_output_basis_cents(world, party, mid)
            if basis is None or basis <= 0:
                continue
            threshold = (basis * SETTLER_TENDER_BID_THRESHOLD_BPS + 9_999) // 10_000
            if implied <= threshold:
                continue
            bid_px = max(1, (basis * SETTLER_TENDER_BID_MARGIN_BPS + 9_999) // 10_000)
            # Skip if this settler is already bidding at this price (no-op revision).
            already = next(
                (
                    b
                    for b in record.get("bids") or []
                    if str(b.get("bidder")) == str(party)
                    and int(b.get("price_per_unit_cents", 0)) == bid_px
                ),
                None,
            )
            if already is not None:
                continue
            submit_tender_bid(world, party, str(record.get("id")), bid_px)
