"""Aggressive market tactics — cornering and predatory pricing."""

from __future__ import annotations

from typing import Any

from realm.agents.settler_identity import (
    _party_hash,
    get_settler_personality,
    get_settler_world_model,
)
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.economy.markets import (
    _ask_total_remaining,
    _asks,
    cancel_party_asks_for_material,
    market_buy,
    place_sell_order,
)
from realm.events.event_log import log_event
from realm.genesis.settler_cost_basis import settler_listing_price_cents, settler_output_basis_cents
from realm.infrastructure.plot_logistics import party_material_held
from realm.world import World

_TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY
_TICKS_PER_GAME_MONTH = 30 * TICKS_PER_GAME_DAY
_CORNER_GREED_THRESHOLD = 0.75
_CORNER_MIN_CASH_CENTS = 50_000
_CORNER_MAX_ASK_DEPTH = 30
_CORNER_MARKUP_BPS = 15_000  # 2.5×
_CORNER_UNFILLED_DAYS = 7
_PREDATORY_GREED_THRESHOLD = 0.75
_PREDATORY_CASH_MULTIPLIER = 5
_PREDATORY_DISCOUNT_BPS = 1_500  # sell at 85% of cost
_PREDATORY_MAX_DAYS = 14


def _corners_store(world: World) -> list[dict[str, Any]]:
    raw = world.scenario_state.setdefault("market_corners", [])
    if not isinstance(raw, list):
        world.scenario_state["market_corners"] = []
        raw = world.scenario_state["market_corners"]
    return raw


def _campaigns_store(world: World) -> list[dict[str, Any]]:
    raw = world.scenario_state.setdefault("predatory_campaigns", [])
    if not isinstance(raw, list):
        world.scenario_state["predatory_campaigns"] = []
        raw = world.scenario_state["predatory_campaigns"]
    return raw


def _display_name(world: World, party: PartyId) -> str:
    return world.party_display_names.get(str(party), str(party))


def _ask_depth(world: World, material: MaterialId) -> int:
    return sum(_ask_total_remaining(a) for a in _asks(world, material))


def _lowest_competitor_ask(world: World, material: MaterialId, holder: PartyId) -> int | None:
    asks = _asks(world, material)
    holder_s = str(holder)
    prices = [
        int(a.price_per_unit_cents)
        for a in asks
        if str(a.party) != holder_s and _ask_total_remaining(a) > 0
    ]
    return min(prices) if prices else None


def _holder_corner_ask(world: World, material: MaterialId, holder: PartyId) -> tuple[int, int] | None:
    """Return (price_cents, qty_remaining) for holder's best ask, if any."""
    holder_s = str(holder)
    for ask in _asks(world, material):
        if str(ask.party) != holder_s:
            continue
        rem = _ask_total_remaining(ask)
        if rem > 0:
            return int(ask.price_per_unit_cents), rem
    return None


def _primary_material(world: World, party: PartyId) -> str:
    counts: dict[str, int] = {}
    ps = str(party)
    for b in world.plot_buildings:
        if str(b.get("party", "")) != ps:
            continue
        bid = str(b.get("building_id", ""))
        counts[bid] = counts.get(bid, 0) + 1
    if not counts:
        return ""
    return max(counts, key=lambda k: counts[k])


def _estimated_cash_tier_score(tier: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(tier, 1)


def _pick_predatory_target(world: World, attacker: PartyId, material: str) -> PartyId | None:
    model = get_settler_world_model(world, attacker)
    candidates: list[tuple[int, int, str, PartyId]] = []
    for other_s, intel in model.known_settlers.items():
        if other_s == str(attacker) or not other_s.startswith("settler_"):
            continue
        other = PartyId(other_s)
        if other not in world.parties:
            continue
        primary = str(intel.get("primary_material", "")) or _primary_material(world, other)
        if primary != material:
            continue
        rep = int(intel.get("reputation_score", 0))
        cash_tier = str(intel.get("estimated_cash_tier", "medium"))
        candidates.append((rep, _estimated_cash_tier_score(cash_tier), other_s, other))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    return candidates[0][3]


def _clear_corner(world: World, row: dict[str, Any], *, reason: str) -> None:
    row["status"] = "cleared"
    row["clear_reason"] = reason


def _maybe_break_corner(world: World, row: dict[str, Any]) -> None:
    if str(row.get("status", "active")) != "active":
        return
    party = PartyId(str(row["party"]))
    material = MaterialId(str(row["material"]))
    corner_price = int(row.get("corner_price_cents", 0))
    if party not in world.parties:
        _clear_corner(world, row, reason="party_gone")
        return

    undercut = _lowest_competitor_ask(world, material, party)
    if undercut is not None and undercut < corner_price:
        _clear_corner(world, row, reason="undercut")
        return

    holder_ask = _holder_corner_ask(world, material, party)
    if holder_ask is None:
        unfilled_since = int(row.get("unfilled_since_tick", 0))
        if unfilled_since <= 0:
            row["unfilled_since_tick"] = int(world.tick)
            return
        if int(world.tick) - unfilled_since >= _CORNER_UNFILLED_DAYS * TICKS_PER_GAME_DAY:
            basis = settler_output_basis_cents(world, party, material)
            if basis is not None and basis > 0:
                cancel_party_asks_for_material(world, party, material)
                stock = party_material_held(world, party, material)
                if stock > 0:
                    place_sell_order(world, party, material, stock, basis)
            _clear_corner(world, row, reason="unfilled_timeout")
        return

    row["unfilled_since_tick"] = 0


def tick_market_cornering(world: World) -> None:
    """Weekly scan for thin markets that high-greed settlers can corner."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_WEEK != 0:
        return

    for row in _corners_store(world):
        if isinstance(row, dict):
            _maybe_break_corner(world, row)

    slot = int(world.tick) % _TICKS_PER_GAME_WEEK
    for party in world.parties:
        ps = str(party)
        if not ps.startswith("settler_"):
            continue
        if _party_hash(party) % _TICKS_PER_GAME_WEEK != slot:
            continue
        personality = get_settler_personality(world, party)
        if personality is None or personality.greed_index <= _CORNER_GREED_THRESHOLD:
            continue
        cash = world.ledger.balance(party_cash_account(party))
        if cash <= _CORNER_MIN_CASH_CENTS:
            continue
        active = any(
            isinstance(r, dict)
            and str(r.get("status", "active")) == "active"
            and str(r.get("party", "")) == ps
            for r in _corners_store(world)
        )
        if active:
            continue

        for mat_key in sorted(world.market_asks_by_material.keys()):
            material = MaterialId(mat_key)
            depth = _ask_depth(world, material)
            if depth <= 0 or depth >= _CORNER_MAX_ASK_DEPTH:
                continue
            asks = _asks(world, material)
            if not asks:
                continue
            original_price = int(asks[0].price_per_unit_cents)
            spent = 0
            bought = 0
            prior_depth = depth + 1
            while depth > 0 and depth < prior_depth:
                prior_depth = depth
                r = market_buy(world, party, material, depth)
                if not r.get("ok"):
                    break
                filled = int(r.get("filled", 0))
                if filled <= 0:
                    break
                bought += filled
                spent += int(r.get("spent_cents", 0))
                depth = _ask_depth(world, material)
                if world.ledger.balance(party_cash_account(party)) <= 0:
                    break
            if bought <= 0:
                continue

            new_price = max(4, (original_price * _CORNER_MARKUP_BPS) // 10_000)
            cancel_party_asks_for_material(world, party, material)
            place_sell_order(world, party, material, bought, new_price)
            _corners_store(world).append(
                {
                    "party": ps,
                    "material": str(material),
                    "original_price_cents": original_price,
                    "corner_price_cents": new_price,
                    "corner_tick": int(world.tick),
                    "qty_cornered": bought,
                    "spent_cents": spent,
                    "status": "active",
                    "unfilled_since_tick": 0,
                }
            )
            label = _display_name(world, party)
            log_event(
                world,
                "world_feed",
                f"{label} cornered the {material} market — best ask now ${new_price / 100:.2f}",
                feed_source="market_corner",
                party=ps,
                material=str(material),
                corner_price_cents=new_price,
            )
            from realm.agents.llm_voice import generate_settler_voice

            generate_settler_voice(
                world,
                party,
                "market_corner",
                {"party_display_name": label, "material": str(material)},
            )
            break


def _end_predatory_campaign(world: World, row: dict[str, Any], *, reason: str) -> None:
    attacker = PartyId(str(row["attacker"]))
    material = MaterialId(str(row["material"]))
    if attacker in world.parties:
        cancel_party_asks_for_material(world, attacker, material)
        stock = party_material_held(world, attacker, material)
        if stock > 0:
            normal = settler_listing_price_cents(world, attacker, material)
            if normal is not None and normal > 0:
                place_sell_order(world, attacker, material, stock, normal)
    row["status"] = "ended"
    row["end_reason"] = reason


def tick_predatory_pricing(world: World) -> None:
    """Monthly predatory undercut campaigns by very high-greed settlers."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_MONTH != 0:
        return

    for row in list(_campaigns_store(world)):
        if not isinstance(row, dict) or str(row.get("status", "active")) != "active":
            continue
        target = PartyId(str(row["target"]))
        elapsed_days = (int(world.tick) - int(row.get("start_tick", 0))) // TICKS_PER_GAME_DAY
        if target not in world.parties:
            label = _display_name(world, target)
            log_event(
                world,
                "world_feed",
                f"Predatory pricing campaign crushed {label} — they left the economy",
                feed_source="predatory_pricing",
                target=str(target),
            )
            _end_predatory_campaign(world, row, reason="target_bankrupt")
            continue
        if elapsed_days >= _PREDATORY_MAX_DAYS:
            _end_predatory_campaign(world, row, reason="duration_expired")

    slot = int(world.tick) % _TICKS_PER_GAME_WEEK
    for party in world.parties:
        ps = str(party)
        if not ps.startswith("settler_"):
            continue
        if _party_hash(party) % _TICKS_PER_GAME_WEEK != slot:
            continue
        personality = get_settler_personality(world, party)
        if personality is None or personality.greed_index <= _PREDATORY_GREED_THRESHOLD:
            continue
        active = any(
            isinstance(r, dict)
            and str(r.get("status", "active")) == "active"
            and str(r.get("attacker", "")) == ps
            for r in _campaigns_store(world)
        )
        if active:
            continue

        material_s = _primary_material(world, party)
        if not material_s:
            continue
        target = _pick_predatory_target(world, party, material_s)
        if target is None:
            continue

        model = get_settler_world_model(world, party)
        intel = model.known_settlers.get(str(target), {})
        target_cash_score = _estimated_cash_tier_score(str(intel.get("estimated_cash_tier", "medium")))
        attacker_cash = world.ledger.balance(party_cash_account(party))
        if attacker_cash < target_cash_score * 500_000 * _PREDATORY_CASH_MULTIPLIER:
            continue

        material = MaterialId(material_s)
        basis = settler_output_basis_cents(world, party, material)
        if basis is None or basis <= 0:
            continue
        predatory_price = max(4, (basis * (10_000 - _PREDATORY_DISCOUNT_BPS)) // 10_000)
        stock = party_material_held(world, party, material)
        if stock <= 0:
            continue

        cancel_party_asks_for_material(world, party, material)
        place_sell_order(world, party, material, stock, predatory_price)
        _campaigns_store(world).append(
            {
                "attacker": ps,
                "target": str(target),
                "material": material_s,
                "start_tick": int(world.tick),
                "predatory_price_cents": predatory_price,
                "status": "active",
            }
        )
        log_event(
            world,
            "predatory_pricing_start",
            f"{party} began undercut campaign vs {target} on {material}",
            attacker=ps,
            target=str(target),
            material=material_s,
            price_cents=predatory_price,
        )
