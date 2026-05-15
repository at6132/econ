"""Thin dispatch for futures, FX, and bank-issued currencies (API → economy)."""

from __future__ import annotations

from typing import Any

from realm.core.ids import MaterialId, PartyId
from realm.world import World


def post_futures_order_action(
    world: World,
    poster: PartyId,
    side: str,
    material: str,
    qty: int,
    price_per_unit_cents: int,
    delivery_tick: int,
) -> dict[str, Any]:
    from realm.economy import futures as fut

    return fut.post_futures_order(
        world,
        poster,
        str(side),
        MaterialId(str(material)),
        int(qty),
        int(price_per_unit_cents),
        int(delivery_tick),
    )


def cancel_futures_order_action(
    world: World, party: PartyId, order_id: str
) -> dict[str, Any]:
    from realm.economy import futures as fut

    return fut.cancel_futures_order(world, party, str(order_id))


def post_fx_order_action(
    world: World,
    poster: PartyId,
    sell_material: str,
    sell_qty: int,
    buy_material: str,
    buy_qty_min: int,
) -> dict[str, Any]:
    from realm.economy import fx_market as fx

    return fx.post_fx_order(
        world,
        poster,
        str(sell_material),
        int(sell_qty),
        str(buy_material),
        int(buy_qty_min),
    )


def cancel_fx_order_action(world: World, party: PartyId, order_id: str) -> dict[str, Any]:
    from realm.economy import fx_market as fx

    return fx.cancel_fx_order(world, party, str(order_id))


def create_currency_action(
    world: World,
    bank_party: PartyId,
    business_id: str,
    symbol: str,
    name: str,
    reserve_ratio: float = 0.20,
) -> dict[str, Any]:
    from realm.economy import currencies as cur

    return cur.create_currency(
        world, bank_party, str(business_id), str(symbol), str(name), float(reserve_ratio)
    )


def mint_currency_action(
    world: World, bank_party: PartyId, currency_id: str, amount: int
) -> dict[str, Any]:
    from realm.economy import currencies as cur

    return cur.mint_currency(world, bank_party, str(currency_id), int(amount))


def redeem_currency_action(
    world: World, holder: PartyId, currency_id: str, amount: int
) -> dict[str, Any]:
    from realm.economy import currencies as cur

    return cur.redeem_currency(world, holder, str(currency_id), int(amount))
