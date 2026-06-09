"""Bilateral supply contracts between named settler counterparties."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from realm.actions._shared import ActionResult
from realm.agents.settler_identity import (
    SettlerPersonality,
    _party_hash,
    get_settler_personality,
)
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import MoneyErr, party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.economy.markets import best_resting_ask_cents
from realm.economy.pricing import exchange_ask_cents
from realm.events.event_log import log_event
from realm.infrastructure.plot_logistics import (
    add_party_plot_stock,
    party_material_held,
    remove_party_plot_stock,
)
from realm.production.recipes import RECIPES
from realm.core.inventory import MatterErr
from realm.production.storage_caps import party_uses_plot_storage, try_add_inventory
from realm.world import World

_TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY
_PROPOSAL_INTERVAL_TICKS = 5 * TICKS_PER_GAME_DAY
_CONSISTENT_OUTPUT_DAYS = 14
_GENESIS_CONSISTENT_OUTPUT_DAYS = 7
_INSTITUTIONAL_BUYERS: frozenset[str] = frozenset(
    {
        "kessler_industrial",
        "genesis_storekeeper",
        "genesis_exchange",
        "genesis_settlement",
    }
)
_BREACH_PENALTY_BPS = 1_000  # 10%
_PROPOSAL_DISCOUNT_BPS = 500  # 5% below current ask
_EXCLUSIVITY_LOYALTY_THRESHOLD = 0.7


@dataclass(frozen=True, slots=True)
class BilateralContract:
    contract_id: str
    seller_party: PartyId
    buyer_party: PartyId
    material_id: MaterialId
    qty_per_week: int
    price_cents_per_unit: int
    duration_weeks: int
    created_tick: int
    breaches: int = 0
    exclusivity: bool = False


def _contracts_store(world: World) -> list[dict[str, Any]]:
    raw = world.scenario_state.setdefault("bilateral_contracts", [])
    if not isinstance(raw, list):
        world.scenario_state["bilateral_contracts"] = []
        raw = world.scenario_state["bilateral_contracts"]
    return raw


def _next_contract_id(world: World) -> str:
    world.next_contract_seq += 1
    return f"bc-{world.next_contract_seq}"


def _contract_to_dict(c: BilateralContract) -> dict[str, Any]:
    return {
        "contract_id": c.contract_id,
        "seller_party": str(c.seller_party),
        "buyer_party": str(c.buyer_party),
        "material_id": str(c.material_id),
        "qty_per_week": int(c.qty_per_week),
        "price_cents_per_unit": int(c.price_cents_per_unit),
        "duration_weeks": int(c.duration_weeks),
        "created_tick": int(c.created_tick),
        "breaches": int(c.breaches),
        "exclusivity": bool(c.exclusivity),
        "fulfilled_weeks": 0,
        "status": "active",
    }


def _contract_from_dict(d: dict[str, Any]) -> BilateralContract:
    return BilateralContract(
        contract_id=str(d["contract_id"]),
        seller_party=PartyId(str(d["seller_party"])),
        buyer_party=PartyId(str(d["buyer_party"])),
        material_id=MaterialId(str(d["material_id"])),
        qty_per_week=int(d["qty_per_week"]),
        price_cents_per_unit=int(d["price_cents_per_unit"]),
        duration_weeks=int(d["duration_weeks"]),
        created_tick=int(d["created_tick"]),
        breaches=int(d.get("breaches", 0)),
        exclusivity=bool(d.get("exclusivity", False)),
    )


def _display_name(world: World, party: PartyId) -> str:
    return world.party_display_names.get(str(party), str(party))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _buyer_acceptance_probability(
    world: World,
    buyer: PartyId,
    material: MaterialId,
    price_cents_per_unit: int,
    personality: SettlerPersonality,
) -> float:
    spot = best_resting_ask_cents(world, material)
    if spot is None or spot <= 0:
        spot = exchange_ask_cents(material, world=world)
    if spot <= 0:
        return 0.05
    margin_improvement = (spot - price_cents_per_unit) / float(spot)
    weighted = margin_improvement * (0.5 + personality.risk_tolerance)
    return min(0.95, max(0.05, _sigmoid(weighted * 8.0)))


def _reduce_honored(world: World, party: PartyId, amount: int = 1) -> None:
    rep = world.reputation.setdefault(str(party), {"honored": 0, "breached": 0})
    rep["honored"] = max(0, int(rep.get("honored", 0)) - amount)


def _increment_breached(world: World, party: PartyId) -> None:
    rep = world.reputation.setdefault(str(party), {"honored": 0, "breached": 0})
    rep["breached"] = int(rep.get("breached", 0)) + 1


def _transfer_material(
    world: World,
    seller: PartyId,
    buyer: PartyId,
    material: MaterialId,
    qty: int,
) -> ActionResult:
    if party_material_held(world, seller, material) < qty:
        return {"ok": False, "reason": "insufficient seller stock"}
    if party_uses_plot_storage(world, seller):
        rm = remove_party_plot_stock(world, seller, material, qty)
    else:
        rm = world.inventory.remove(seller, material, qty)
    if isinstance(rm, MatterErr):
        return {"ok": False, "reason": rm.reason}
    if party_uses_plot_storage(world, buyer):
        ad = add_party_plot_stock(world, buyer, material, qty)
    else:
        ad = try_add_inventory(world, buyer, material, qty)
    if isinstance(ad, MatterErr):
        if party_uses_plot_storage(world, seller):
            add_party_plot_stock(world, seller, material, qty)
        else:
            world.inventory.add(seller, material, qty)
        return {"ok": False, "reason": ad.reason}
    return {"ok": True}


def _rollback_delivery(
    world: World,
    seller: PartyId,
    buyer: PartyId,
    material: MaterialId,
    qty: int,
) -> None:
    if party_uses_plot_storage(world, buyer):
        remove_party_plot_stock(world, buyer, material, qty)
        add_party_plot_stock(world, seller, material, qty)
    else:
        rb = world.inventory.remove(buyer, material, qty)
        if not isinstance(rb, MatterErr):
            world.inventory.add(seller, material, qty)


def _fulfill_contract_delivery(
    world: World,
    row: dict[str, Any],
) -> bool:
    seller = PartyId(str(row["seller_party"]))
    buyer = PartyId(str(row["buyer_party"]))
    material = MaterialId(str(row["material_id"]))
    qty = int(row["qty_per_week"])
    unit_price = int(row["price_cents_per_unit"])
    total_price = qty * unit_price

    xfer = _transfer_material(world, seller, buyer, material, qty)
    if not xfer["ok"]:
        return False

    buyer_cash = party_cash_account(buyer)
    seller_cash = party_cash_account(seller)
    if world.ledger.balance(buyer_cash) < total_price:
        _rollback_delivery(world, seller, buyer, material, qty)
        return False

    pay = world.ledger.transfer(debit=buyer_cash, credit=seller_cash, amount_cents=total_price)
    if isinstance(pay, MoneyErr):
        _rollback_delivery(world, seller, buyer, material, qty)
        return False

    row["fulfilled_weeks"] = int(row.get("fulfilled_weeks", 0)) + 1
    rep_s = world.reputation.setdefault(str(seller), {"honored": 0, "breached": 0})
    rep_b = world.reputation.setdefault(str(buyer), {"honored": 0, "breached": 0})
    rep_s["honored"] = int(rep_s.get("honored", 0)) + 1
    rep_b["honored"] = int(rep_b.get("honored", 0)) + 1
    log_event(
        world,
        "contract_fulfilled",
        f"{seller} delivered {qty}×{material} to {buyer} under {row['contract_id']}",
        contract_id=str(row["contract_id"]),
        seller=str(seller),
        buyer=str(buyer),
        material=str(material),
        qty=qty,
        total_price_cents=total_price,
    )
    return True


def _remaining_contract_value_cents(row: dict[str, Any]) -> int:
    fulfilled = int(row.get("fulfilled_weeks", 0))
    remaining_weeks = max(0, int(row["duration_weeks"]) - fulfilled)
    return remaining_weeks * int(row["qty_per_week"]) * int(row["price_cents_per_unit"])


def _terminate_with_penalty(world: World, row: dict[str, Any]) -> None:
    seller = PartyId(str(row["seller_party"]))
    buyer = PartyId(str(row["buyer_party"]))
    penalty = (_remaining_contract_value_cents(row) * _BREACH_PENALTY_BPS) // 10_000
    if penalty > 0:
        seller_cash = party_cash_account(seller)
        buyer_cash = party_cash_account(buyer)
        bal = world.ledger.balance(seller_cash)
        pay = min(penalty, bal)
        if pay > 0:
            world.ledger.transfer(debit=seller_cash, credit=buyer_cash, amount_cents=pay)
    row["status"] = "terminated"
    _increment_breached(world, seller)
    log_event(
        world,
        "contract_terminated",
        f"{buyer} terminated {row['contract_id']} after seller breaches — penalty ${penalty / 100:.2f}",
        contract_id=str(row["contract_id"]),
        seller=str(seller),
        buyer=str(buyer),
        penalty_cents=penalty,
    )


def _seller_listed_material_this_week(
    world: World,
    seller: PartyId,
    material: MaterialId,
) -> bool:
    cutoff = int(world.tick) - _TICKS_PER_GAME_WEEK
    seller_s = str(seller)
    mat_s = str(material)
    for ev in world.event_log:
        if int(ev.get("tick", 0)) < cutoff:
            continue
        if str(ev.get("kind", "")) != "market_list":
            continue
        if str(ev.get("party", "")) != seller_s:
            continue
        if str(ev.get("material", "")) == mat_s:
            return True
    return False


def _record_breach(world: World, row: dict[str, Any], reason: str) -> None:
    seller = PartyId(str(row["seller_party"]))
    row["breaches"] = int(row.get("breaches", 0)) + 1
    _reduce_honored(world, seller, 1)
    _increment_breached(world, seller)
    log_event(
        world,
        "contract_breach",
        f"{row['contract_id']} breach ({reason}): seller {seller}",
        contract_id=str(row["contract_id"]),
        seller=str(seller),
        reason=reason,
    )
    if int(row["breaches"]) >= 2:
        _terminate_with_penalty(world, row)


def propose_bilateral_contract(
    world: World,
    seller: PartyId,
    buyer: PartyId,
    material: MaterialId,
    qty_per_week: int,
    price_cents_per_unit: int,
    duration_weeks: int,
    exclusive: bool,
    *,
    force_accept: bool = False,
) -> ActionResult:
    if seller == buyer:
        return {"ok": False, "reason": "seller and buyer must differ"}
    if seller not in world.parties or buyer not in world.parties:
        return {"ok": False, "reason": "party missing"}
    if qty_per_week <= 0 or price_cents_per_unit <= 0 or duration_weeks <= 0:
        return {"ok": False, "reason": "invalid contract terms"}

    personality = get_settler_personality(world, buyer)
    if personality is None:
        return {"ok": False, "reason": "buyer has no personality"}

    accept_prob = _buyer_acceptance_probability(
        world, buyer, material, price_cents_per_unit, personality
    )
    if not force_accept:
        rng = world.rng(f"bilateral_accept:{seller}:{buyer}:{material}:{world.tick}")
        if rng.random() >= accept_prob:
            return {"ok": False, "reason": "buyer declined"}

    contract = BilateralContract(
        contract_id=_next_contract_id(world),
        seller_party=seller,
        buyer_party=buyer,
        material_id=material,
        qty_per_week=qty_per_week,
        price_cents_per_unit=price_cents_per_unit,
        duration_weeks=duration_weeks,
        created_tick=int(world.tick),
        exclusivity=exclusive,
    )
    _contracts_store(world).append(_contract_to_dict(contract))

    seller_name = _display_name(world, seller)
    buyer_name = _display_name(world, buyer)
    msg = (
        f"{seller_name} signed a supply deal with {buyer_name}: "
        f"{qty_per_week}×{material}/week at ${price_cents_per_unit / 100:.2f}/unit"
    )
    if exclusive:
        msg += " (exclusive)"
    log_event(
        world,
        "contract_signed",
        msg,
        contract_id=contract.contract_id,
        seller=str(seller),
        buyer=str(buyer),
        material=str(material),
        qty_per_week=qty_per_week,
        price_cents_per_unit=price_cents_per_unit,
        duration_weeks=duration_weeks,
        exclusivity=exclusive,
    )
    log_event(
        world,
        "world_feed",
        msg,
        feed_source="bilateral_contract",
        contract_id=contract.contract_id,
    )
    return {"ok": True, "contract_id": contract.contract_id}


def tick_bilateral_contracts(world: World) -> None:
    """Weekly fulfillment, breach handling, and expiry."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_WEEK != 0:
        return

    for row in _contracts_store(world):
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "active")) != "active":
            continue
        seller = PartyId(str(row["seller_party"]))
        buyer = PartyId(str(row["buyer_party"]))
        if seller not in world.parties or buyer not in world.parties:
            row["status"] = "void"
            continue

        fulfilled = int(row.get("fulfilled_weeks", 0))
        if fulfilled >= int(row["duration_weeks"]):
            row["status"] = "completed"
            continue

        material = MaterialId(str(row["material_id"]))
        qty = int(row["qty_per_week"])

        if bool(row.get("exclusivity")) and _seller_listed_material_this_week(
            world, seller, material
        ):
            _record_breach(world, row, "exclusivity violation")
            if str(row.get("status")) != "active":
                continue

        if party_material_held(world, seller, material) < qty:
            _record_breach(world, row, "insufficient stock")
            continue

        if not _fulfill_contract_delivery(world, row):
            _record_breach(world, row, "delivery failed")


def _recipe_outputs_material(recipe_id: str, material: str) -> bool:
    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        return False
    return material in {str(mid) for mid in recipe.outputs}


def _consistent_output_days(world: World, party: PartyId, material: str) -> int:
    """Count distinct game-days with production_done for ``material`` in the lookback window."""
    lookback_days = (
        _GENESIS_CONSISTENT_OUTPUT_DAYS
        if world.scenario_id == "genesis"
        else _CONSISTENT_OUTPUT_DAYS
    )
    party_s = str(party)
    tracked = (world.scenario_state.get("settler_production_days") or {}).get(party_s) or {}
    day_list = tracked.get(material)
    if isinstance(day_list, list) and day_list:
        cutoff_day = int(world.tick) // TICKS_PER_GAME_DAY - lookback_days
        return sum(1 for d in day_list if int(d) >= cutoff_day)
    cutoff = int(world.tick) - lookback_days * TICKS_PER_GAME_DAY
    days: set[int] = set()
    for ev in world.event_log:
        tick = int(ev.get("tick", 0))
        if tick < cutoff:
            continue
        if str(ev.get("kind", "")) != "production_done":
            continue
        if str(ev.get("party", "")) != party_s:
            continue
        recipe_id = str(ev.get("recipe_id", ""))
        if _recipe_outputs_material(recipe_id, material):
            days.add(tick // TICKS_PER_GAME_DAY)
    return len(days)


def _repeat_buyers(world: World, seller: PartyId, material: str) -> list[PartyId]:
    lookback_days = (
        _GENESIS_CONSISTENT_OUTPUT_DAYS
        if world.scenario_id == "genesis"
        else _CONSISTENT_OUTPUT_DAYS
    )
    cutoff = int(world.tick) - lookback_days * TICKS_PER_GAME_DAY
    seller_s = str(seller)
    buyers: dict[str, int] = {}
    trade_kinds = ("market_buy", "market_match")
    for ev in world.event_log:
        tick = int(ev.get("tick", 0))
        if tick < cutoff:
            continue
        if str(ev.get("kind", "")) not in trade_kinds:
            continue
        if str(ev.get("material", "")) != material:
            continue
        if str(ev.get("kind", "")) == "market_match":
            seller_hit = str(ev.get("seller") or "")
            if seller_hit != seller_s:
                continue
            buyer_s = str(ev.get("buyer") or ev.get("party") or "")
        else:
            sellers_raw = str(ev.get("sellers", "") or ev.get("seller", ""))
            if seller_s not in {s.strip() for s in sellers_raw.split(",") if s.strip()}:
                continue
            buyer_s = str(ev.get("buyer", "") or ev.get("party", ""))
        if not buyer_s or buyer_s == seller_s:
            continue
        if (
            buyer_s.startswith("settler_")
            or buyer_s in _INSTITUTIONAL_BUYERS
            or buyer_s.startswith("pop_hub")
        ):
            buyers[buyer_s] = buyers.get(buyer_s, 0) + 1
    ranked = sorted(buyers.items(), key=lambda x: (-x[1], x[0]))
    return [PartyId(b) for b, _ in ranked]


def tick_contract_proposals(world: World) -> None:
    """Every 5 game-days, qualifying sellers propose bilateral deals to repeat buyers."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _PROPOSAL_INTERVAL_TICKS != 0:
        return

    slot = int(world.tick) % _TICKS_PER_GAME_WEEK
    for party in world.parties:
        ps = str(party)
        if not ps.startswith("settler_"):
            continue
        if _party_hash(party) % _TICKS_PER_GAME_WEEK != slot:
            continue

        personality = get_settler_personality(world, party)
        if personality is None:
            continue

        from realm.genesis.settler_cost_basis import settler_output_basis_cents

        root = world.scenario_state.get("settler_cost_basis") or {}
        blob = root.get(ps) or {}
        output_qty = blob.get("output_qty_produced") or {}
        if not output_qty:
            continue

        material_s = max(output_qty, key=lambda m: int(output_qty[m]))
        min_out_days = (
            _GENESIS_CONSISTENT_OUTPUT_DAYS
            if world.scenario_id == "genesis"
            else _CONSISTENT_OUTPUT_DAYS
        )
        if _consistent_output_days(world, party, material_s) < min_out_days:
            continue

        buyers = _repeat_buyers(world, party, material_s)
        if not buyers:
            continue

        material = MaterialId(material_s)
        ask = best_resting_ask_cents(world, material)
        if ask is None or ask <= 0:
            ask = settler_output_basis_cents(world, party, material)
        if ask is None or ask <= 0:
            ask = exchange_ask_cents(material, world=world)
        price = max(4, (ask * (10_000 - _PROPOSAL_DISCOUNT_BPS)) // 10_000)

        exclusive = personality.specialization_loyalty > _EXCLUSIVITY_LOYALTY_THRESHOLD
        qty_map = output_qty
        qty_per_week = max(
            1,
            min(20, int(qty_map.get(material_s, 1)) // max(1, min_out_days)),
        )

        for buyer in buyers[:3]:
            if buyer not in world.parties:
                continue
            terms = {
                "material_id": str(material),
                "qty_per_week": qty_per_week,
                "price_cents_per_unit": price,
                "duration_weeks": 8,
                "exclusive": exclusive,
            }
            from realm.agents.llm_negotiation import negotiate_bilateral_contract

            seller_cash = world.ledger.balance(party_cash_account(party))
            buyer_cash = world.ledger.balance(party_cash_account(buyer))
            if seller_cash + buyer_cash > 10_000:
                nego = negotiate_bilateral_contract(world, party, buyer, terms)
                if nego.get("ok"):
                    break
                if nego.get("reason") == "negotiation cooldown":
                    continue
            result = propose_bilateral_contract(
                world,
                party,
                buyer,
                material,
                qty_per_week,
                price,
                duration_weeks=8,
                exclusive=exclusive,
            )
            if result.get("ok"):
                break
