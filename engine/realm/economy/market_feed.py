"""Curated world_feed headlines for market, tender, and contract activity."""

from __future__ import annotations

from typing import Final

from realm.core.ids import MaterialId, PartyId
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event
from realm.world import World

RESTING_FEED_MIN_QTY: Final[int] = 10
FILL_FEED_MIN_QTY: Final[int] = 6
FILL_FEED_MIN_CENTS: Final[int] = 15_000
_FEED_COOLDOWN_TICKS: Final[int] = TICKS_PER_GAME_DAY // 2

_INSTITUTIONAL_PARTIES: Final[frozenset[str]] = frozenset(
    {
        "genesis_storekeeper",
        "genesis_exchange",
        "genesis_settlement",
        "kessler_industrial",
        "genesis_construction",
    }
)


def party_market_label(world: World, party: PartyId | str) -> str:
    key = str(party)
    return str(world.party_display_names.get(key, key))


def _is_named_market_actor(party: PartyId | str) -> bool:
    key = str(party)
    if key in _INSTITUTIONAL_PARTIES:
        return True
    if key.startswith("store_") or key.startswith("settler_"):
        return True
    if key == "player":
        return True
    return False


def _feed_cooldown_ok(world: World, key: str) -> bool:
    gst = world.scenario_state.setdefault("genesis", {})
    if not isinstance(gst, dict):
        return True
    last = gst.setdefault("market_feed_last_tick", {})
    if not isinstance(last, dict):
        last = {}
        gst["market_feed_last_tick"] = last
    prev = int(last.get(key, -10**9))
    now = int(world.tick)
    if now - prev < _FEED_COOLDOWN_TICKS:
        return False
    last[key] = now
    return True


def maybe_feed_resting_bid(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    max_price_cents: int,
) -> None:
    if qty < RESTING_FEED_MIN_QTY and not _is_named_market_actor(party):
        return
    key = f"bid:{party}:{material}"
    if not _feed_cooldown_ok(world, key):
        return
    pretty = party_market_label(world, party)
    mat = str(material).replace("_", " ")
    log_event(
        world,
        "world_feed",
        f"{pretty} posted buy bid — {qty}× {mat} up to {max_price_cents}¢/u.",
        feed_source="market_bid",
        party=str(party),
        material=str(material),
        qty=int(qty),
        price_per_unit_cents=int(max_price_cents),
    )


def maybe_feed_resting_ask(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    price_cents: int,
) -> None:
    if qty < RESTING_FEED_MIN_QTY and not _is_named_market_actor(party):
        return
    key = f"ask:{party}:{material}"
    if not _feed_cooldown_ok(world, key):
        return
    pretty = party_market_label(world, party)
    mat = str(material).replace("_", " ")
    log_event(
        world,
        "world_feed",
        f"{pretty} listed ask — {qty}× {mat} @ {price_cents}¢/u.",
        feed_source="market_ask",
        party=str(party),
        material=str(material),
        qty=int(qty),
        price_per_unit_cents=int(price_cents),
    )


def maybe_feed_market_fill(
    world: World,
    *,
    buyer: PartyId,
    seller: PartyId,
    material: MaterialId,
    qty: int,
    unit_price_cents: int,
    fill_kind: str,
) -> None:
    notional = int(qty) * int(unit_price_cents)
    if qty < FILL_FEED_MIN_QTY and notional < FILL_FEED_MIN_CENTS:
        return
    key = f"fill:{fill_kind}:{buyer}:{seller}:{material}"
    if not _feed_cooldown_ok(world, key):
        return
    mat = str(material).replace("_", " ")
    buyer_n = party_market_label(world, buyer)
    seller_n = party_market_label(world, seller)
    log_event(
        world,
        "world_feed",
        f"Trade: {buyer_n} bought {qty}× {mat} from {seller_n} @ {unit_price_cents}¢/u.",
        feed_source="market_fill",
        buyer=str(buyer),
        seller=str(seller),
        material=str(material),
        qty=int(qty),
        price_per_unit_cents=int(unit_price_cents),
        fill_kind=str(fill_kind),
    )


def maybe_feed_named_large_buy(
    world: World,
    party: PartyId,
    material: MaterialId,
    qty: int,
    max_price_cents: int,
) -> None:
    """Named headline for large institutional/store bids; settlers stay anonymous."""
    from realm.economy.supply_signals import LARGE_BUY_THRESHOLD_UNITS

    if int(qty) < LARGE_BUY_THRESHOLD_UNITS:
        return
    if not (
        str(party) in _INSTITUTIONAL_PARTIES
        or str(party).startswith("store_")
        or str(party) == "player"
    ):
        return
    key = f"large:{party}:{material}"
    if not _feed_cooldown_ok(world, key):
        return
    pretty = party_market_label(world, party)
    mat = str(material).replace("_", " ")
    log_event(
        world,
        "world_feed",
        f"Large buy: {pretty} bidding {qty}× {mat} up to {max_price_cents}¢/u.",
        feed_source="large_buy",
        party=str(party),
        material=str(material),
        qty=int(qty),
        price_per_unit_cents=int(max_price_cents),
    )


def feed_tender_posted(
    world: World,
    *,
    posted_by: PartyId,
    material: MaterialId,
    qty_per_cycle: int,
    tender_id: str,
    duration_cycles: int,
) -> None:
    pretty = party_market_label(world, posted_by)
    mat = str(material).replace("_", " ")
    log_event(
        world,
        "world_feed",
        f"{pretty} posted supply tender {tender_id}: {qty_per_cycle}× {mat}/cycle × {duration_cycles} cycles.",
        feed_source="tender_posted",
        tender_id=str(tender_id),
        posted_by=str(posted_by),
        material=str(material),
        qty_per_cycle=int(qty_per_cycle),
    )


def feed_tender_awarded(
    world: World,
    *,
    tender_id: str,
    posted_by: PartyId,
    winner: PartyId,
    material: MaterialId,
    price_cents: int,
    contract_id: str,
) -> None:
    poster = party_market_label(world, posted_by)
    win = party_market_label(world, winner)
    mat = str(material).replace("_", " ")
    log_event(
        world,
        "world_feed",
        f"Tender {tender_id} awarded: {win} supplies {mat} to {poster} @ {price_cents}¢/u (contract {contract_id}).",
        feed_source="tender_awarded",
        tender_id=str(tender_id),
        winner=str(winner),
        posted_by=str(posted_by),
        material=str(material),
        contract_id=str(contract_id),
    )


def feed_company_ipo(
    world: World,
    *,
    company_id: str,
    company_name: str,
    seller: PartyId,
    shares: int,
    price_cents_per_share: int,
    offering_id: str,
) -> None:
    seller_n = party_market_label(world, seller)
    log_event(
        world,
        "world_feed",
        f"IPO: {company_name} ({company_id}) — {seller_n} offering {shares} shares @ {price_cents_per_share}¢ each ({offering_id}).",
        feed_source="equity_ipo",
        company_id=str(company_id),
        offering_id=str(offering_id),
        seller=str(seller),
        shares=int(shares),
        price_cents_per_share=int(price_cents_per_share),
    )


def tick_market_book_refresh(world: World) -> None:
    """Reprice stale institutional resting bids so the book visibly moves."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % (2 * TICKS_PER_GAME_DAY) != 0:
        return

    from realm.economy.market_signals import demand_supply_imbalance_bps, scarcity_premium_bps
    from realm.economy.markets import cancel_buy_order, place_buy_order
    from realm.economy.pricing import exchange_ask_cents

    stale_ticks = 3 * TICKS_PER_GAME_DAY
    now = int(world.tick)
    refreshed = 0
    for mat_s, bids in list(world.market_bids_by_material.items()):
        if refreshed >= 6:
            break
        mid = MaterialId(mat_s)
        imb = demand_supply_imbalance_bps(world, mid)
        if imb <= 0:
            continue
        asks = world.market_asks_by_material.get(mat_s, [])
        ref = (
            min(a.price_per_unit_cents for a in asks)
            if asks
            else exchange_ask_cents(mid, world=world)
        )
        premium = 600 + max(0, imb // 5) + scarcity_premium_bps(world, mid)
        target_px = max(4, int(ref * (10_000 + premium) // 10_000))
        for bid in list(bids):
            if refreshed >= 6:
                break
            party_s = str(bid.party)
            if not (
                party_s in _INSTITUTIONAL_PARTIES
                or party_s.startswith("store_")
            ):
                continue
            if now - int(bid.posted_at_tick) < stale_ticks:
                continue
            if int(bid.max_price_per_unit_cents) >= target_px:
                continue
            qty = int(bid.qty) + int(getattr(bid, "iceberg_hidden_qty", 0) or 0)
            if qty < 4:
                continue
            oid = str(bid.order_id)
            cancel_buy_order(world, PartyId(party_s), oid)
            place_buy_order(world, PartyId(party_s), mid, min(qty, 24), target_px)
            refreshed += 1


__all__ = [
    "party_market_label",
    "maybe_feed_resting_bid",
    "maybe_feed_resting_ask",
    "maybe_feed_market_fill",
    "maybe_feed_named_large_buy",
    "feed_tender_posted",
    "feed_tender_awarded",
    "feed_company_ipo",
    "tick_market_book_refresh",
]
