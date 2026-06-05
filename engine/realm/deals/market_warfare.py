"""Advanced market warfare — cartels, panic cycles, speculation, and short selling."""

from __future__ import annotations

from typing import Any

from realm.agents.settler_identity import (
    _party_hash,
    get_settler_personality,
    get_settler_world_model,
)
from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.economy.markets import (
    _ask_total_remaining,
    _asks,
    best_resting_ask_cents,
    cancel_party_asks_for_material,
    market_buy,
    place_sell_order,
)
from realm.events.event_log import log_event
from realm.genesis.settler_cost_basis import (
    record_settler_buy,
    settler_output_basis_cents,
)
from realm.infrastructure.plot_logistics import (
    ensure_inventory_from_stash,
    owned_plot_ids_sorted,
    party_material_held,
)
from realm.production.storage_caps import party_matter_value_cents
from realm.world import World

_TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY
_CARTEL_FORMATION_INTERVAL = 14 * TICKS_PER_GAME_DAY
_SPEC_POSITION_HORIZON = 14 * TICKS_PER_GAME_DAY
_SHORT_POSITION_HORIZON = 14 * TICKS_PER_GAME_DAY
_SHORT_BORROW_FEE_BPS = 200  # 2% per week of notional at open

_CARTEL_MIN_MEMBERS = 3
_CARTEL_MIN_SHARE_BPS = 1_500  # 15% of ask depth
_CARTEL_FORMATION_PROB_SCALE = 0.3
_CARTEL_FLOOR_MARKUP_BPS = 14_000  # best_ask × 1.4

_PANIC_CASH_DECLINE_BPS = 4_000  # 40% drop over 7 days
_PANIC_MIN_INVENTORY_CENTS = 20_000
_PANIC_SELL_DISCOUNT_BPS = 4_000  # cost_basis × 0.6
_PANIC_CASCADE_DROP_BPS = 2_000  # 20% price drop triggers cascade

_SPEC_MIN_RISK = 0.7
_SPEC_MIN_CASH_CENTS = 100_000
_SPEC_MIN_TREND_STREAK = 3
_SPEC_BUY_MULTIPLIER = 2
_SPEC_MIN_DAYS_OBSERVED = 14
_SPEC_MIN_PRICE_HISTORY_DAYS = 7

_SHORT_MIN_RISK = 0.8
_SHORT_MIN_LENDER_STOCK = 10


def _cartels_store(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault("cartels", {})
    if not isinstance(raw, dict):
        world.scenario_state["cartels"] = {}
        raw = world.scenario_state["cartels"]
    return raw


def _spec_positions_store(world: World) -> dict[str, list[dict[str, Any]]]:
    raw = world.scenario_state.setdefault("spec_positions", {})
    if not isinstance(raw, dict):
        world.scenario_state["spec_positions"] = {}
        raw = world.scenario_state["spec_positions"]
    return raw


def _short_positions_store(world: World) -> list[dict[str, Any]]:
    raw = world.scenario_state.setdefault("short_positions", [])
    if not isinstance(raw, list):
        world.scenario_state["short_positions"] = []
        raw = world.scenario_state["short_positions"]
    return raw


def _cash_snapshots_store(world: World) -> dict[str, list[list[int]]]:
    raw = world.scenario_state.setdefault("settler_cash_snapshots", {})
    if not isinstance(raw, dict):
        world.scenario_state["settler_cash_snapshots"] = {}
        raw = world.scenario_state["settler_cash_snapshots"]
    return raw


def _trend_streaks_store(world: World) -> dict[str, dict[str, int]]:
    raw = world.scenario_state.setdefault("trend_streaks", {})
    if not isinstance(raw, dict):
        world.scenario_state["trend_streaks"] = {}
        raw = world.scenario_state["trend_streaks"]
    return raw


def _panic_baseline_store(world: World) -> dict[str, int]:
    raw = world.scenario_state.setdefault("panic_baseline_asks", {})
    if not isinstance(raw, dict):
        world.scenario_state["panic_baseline_asks"] = {}
        raw = world.scenario_state["panic_baseline_asks"]
    return raw


def _display_name(world: World, party: PartyId) -> str:
    return world.party_display_names.get(str(party), str(party))


def _party_held_materials(world: World, party: PartyId) -> list[MaterialId]:
    """Personal carry plus plot-bulk stock for a settler."""
    counts: dict[str, int] = {}
    for mat, qty in world.inventory.stock_for_party(party).items():
        counts[str(mat)] = counts.get(str(mat), 0) + int(qty)
    for pid in owned_plot_ids_sorted(world, party):
        bucket = world.plot_output_stock.get(str(pid)) or {}
        for mat_s, qty in bucket.items():
            counts[mat_s] = counts.get(mat_s, 0) + int(qty)
    return [MaterialId(k) for k, v in sorted(counts.items()) if int(v) > 0]


def _settler_parties(world: World) -> list[PartyId]:
    return [p for p in world.parties if str(p).startswith("settler_")]


def _party_ask_depth(world: World, material: MaterialId, party: PartyId) -> int:
    ps = str(party)
    return sum(
        _ask_total_remaining(a)
        for a in _asks(world, material)
        if str(a.party) == ps and _ask_total_remaining(a) > 0
    )


def _total_ask_depth(world: World, material: MaterialId) -> int:
    return sum(_ask_total_remaining(a) for a in _asks(world, material))


def cartel_listing_floor_cents(
    world: World, party: PartyId, material: MaterialId
) -> int | None:
    """Return the cartel floor price for a member party, if any."""
    row = _cartels_store(world).get(str(material))
    if not isinstance(row, dict) or str(row.get("status", "active")) != "active":
        return None
    members = row.get("members") or []
    if str(party) not in members:
        return None
    floor = int(row.get("floor_price_cents", 0))
    return floor if floor > 0 else None


def _break_cartel(world: World, material: str, *, reason: str, message: str) -> None:
    row = _cartels_store(world).get(material)
    if not isinstance(row, dict) or str(row.get("status", "active")) != "active":
        return
    row["status"] = "broken"
    row["break_reason"] = reason
    row["broken_tick"] = int(world.tick)
    log_event(
        world,
        "world_feed",
        message,
        feed_source="cartel_break",
        material=material,
        reason=reason,
    )


def _check_cartel_undercuts(world: World) -> None:
    for material, row in list(_cartels_store(world).items()):
        if not isinstance(row, dict) or str(row.get("status", "active")) != "active":
            continue
        floor = int(row.get("floor_price_cents", 0))
        if floor <= 0:
            continue
        members = {str(m) for m in (row.get("members") or [])}
        for ask in _asks(world, MaterialId(material)):
            if _ask_total_remaining(ask) <= 0:
                continue
            ps = str(ask.party)
            if ps in members:
                continue
            if int(ask.price_per_unit_cents) < floor:
                _break_cartel(
                    world,
                    material,
                    reason="undercut",
                    message=f"The {material} cartel has been broken by a new entrant",
                )
                break


def _check_cartel_defections(world: World) -> None:
    for material, row in list(_cartels_store(world).items()):
        if not isinstance(row, dict) or str(row.get("status", "active")) != "active":
            continue
        formed = int(row.get("formed_tick", 0))
        days_since = max(0, (int(world.tick) - formed) // TICKS_PER_GAME_DAY)
        members = list(row.get("members") or [])
        defectors: list[str] = []
        for member_s in members:
            member = PartyId(member_s)
            if member not in world.parties:
                defectors.append(member_s)
                continue
            defect_prob = 0.05 + days_since * 0.01
            roll = world.rng(f"cartel-defect:{material}:{member_s}:{world.tick}").random()
            if roll < defect_prob:
                defectors.append(member_s)
        if not defectors:
            continue
        remaining = [m for m in members if m not in defectors]
        if len(remaining) < _CARTEL_MIN_MEMBERS:
            _break_cartel(
                world,
                material,
                reason="defection",
                message=f"The {material} cartel collapsed after member defections",
            )
        else:
            row["members"] = remaining
            for d in defectors:
                log_event(
                    world,
                    "cartel_defection",
                    f"{d} defected from the {material} cartel",
                    party=d,
                    material=material,
                )


def _try_form_cartels(world: World) -> None:
    depth_by_material: dict[str, int] = {}
    share_by_material: dict[str, dict[str, int]] = {}
    for mat_key in sorted(world.market_asks_by_material.keys()):
        material = MaterialId(mat_key)
        total = _total_ask_depth(world, material)
        if total <= 0:
            continue
        depth_by_material[mat_key] = total
        shares: dict[str, int] = {}
        for party in _settler_parties(world):
            depth = _party_ask_depth(world, material, party)
            if depth * 10_000 >= total * _CARTEL_MIN_SHARE_BPS:
                shares[str(party)] = depth
        if len(shares) >= _CARTEL_MIN_MEMBERS:
            share_by_material[mat_key] = shares

    for material, shares in share_by_material.items():
        if material in _cartels_store(world):
            existing = _cartels_store(world)[material]
            if isinstance(existing, dict) and str(existing.get("status", "active")) == "active":
                continue
        members = sorted(shares.keys())
        greed_sum = 0.0
        greed_count = 0
        for member_s in members:
            personality = get_settler_personality(world, PartyId(member_s))
            if personality is not None:
                greed_sum += personality.greed_index
                greed_count += 1
        if greed_count <= 0:
            continue
        avg_greed = greed_sum / greed_count
        roll = world.rng(f"cartel:{material}:{world.tick}").random()
        if roll >= _CARTEL_FORMATION_PROB_SCALE * avg_greed:
            continue
        best_ask = best_resting_ask_cents(world, MaterialId(material))
        if best_ask is None or best_ask <= 0:
            continue
        floor = max(4, (int(best_ask) * _CARTEL_FLOOR_MARKUP_BPS) // 10_000)
        _cartels_store(world)[material] = {
            "members": members,
            "floor_price_cents": floor,
            "formed_tick": int(world.tick),
            "status": "active",
        }
        log_event(
            world,
            "cartel_formed",
            f"Cartel formed on {material} — floor ${floor / 100:.2f}",
            material=material,
            members=",".join(members),
            floor_price_cents=floor,
        )


def tick_cartel_formation(world: World) -> None:
    """Daily upkeep; formation rolls every 14 game-days; defections weekly."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0:
        return
    _check_cartel_undercuts(world)
    if int(world.tick) % _TICKS_PER_GAME_WEEK == 0:
        _check_cartel_defections(world)
    if int(world.tick) % _CARTEL_FORMATION_INTERVAL != 0:
        return
    _try_form_cartels(world)


def _record_cash_snapshot(world: World, party: PartyId) -> None:
    cash = world.ledger.balance(party_cash_account(party))
    history = _cash_snapshots_store(world).setdefault(str(party), [])
    history.append([int(world.tick), int(cash)])
    cutoff = int(world.tick) - _TICKS_PER_GAME_WEEK
    while history and int(history[0][0]) < cutoff:
        history.pop(0)


def _cash_decline_bps(world: World, party: PartyId) -> int | None:
    history = _cash_snapshots_store(world).get(str(party)) or []
    if len(history) < 2:
        return None
    oldest_cash = int(history[0][1])
    if oldest_cash <= 0:
        return None
    latest_cash = int(history[-1][1])
    if latest_cash >= oldest_cash:
        return 0
    return int((oldest_cash - latest_cash) * 10_000 // oldest_cash)


def _panic_sell_price_cents(world: World, party: PartyId, material: MaterialId) -> int:
    basis = settler_output_basis_cents(world, party, material)
    if basis is None or basis <= 0:
        basis = best_resting_ask_cents(world, material) or 4
    return max(4, (int(basis) * (10_000 - _PANIC_SELL_DISCOUNT_BPS)) // 10_000)


def _execute_panic_sell(
    world: World,
    party: PartyId,
    material: MaterialId,
    *,
    triggered: set[str],
) -> None:
    key = f"{party}|{material}"
    if key in triggered:
        return
    qty = party_material_held(world, party, material)
    if qty <= 0:
        return
    ensure_inventory_from_stash(world, party, material, qty)
    held = world.inventory.qty(party, material)
    if held <= 0:
        return
    baseline_store = _panic_baseline_store(world)
    if str(material) not in baseline_store:
        ask = best_resting_ask_cents(world, material)
        if ask is not None and ask > 0:
            baseline_store[str(material)] = int(ask)
    px = _panic_sell_price_cents(world, party, material)
    cancel_party_asks_for_material(world, party, material)
    place_sell_order(world, party, material, held, px)
    triggered.add(key)
    label = _display_name(world, party)
    log_event(
        world,
        "world_feed",
        f"{label} is panic-selling {material} inventory — market price collapsing",
        feed_source="panic_sell",
        party=str(party),
        material=str(material),
        price_cents=px,
    )


def _panic_cascade_candidates(world: World, material: MaterialId) -> bool:
    baseline = _panic_baseline_store(world).get(str(material))
    if baseline is None or baseline <= 0:
        return False
    current = best_resting_ask_cents(world, material)
    if current is None or current <= 0:
        return True
    drop_bps = int((baseline - current) * 10_000 // baseline)
    return drop_bps >= _PANIC_CASCADE_DROP_BPS


def tick_panic_selling(world: World) -> None:
    """Daily panic liquidation when cash craters; cascades on 20%+ price drops."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return

    for party in _settler_parties(world):
        _record_cash_snapshot(world, party)

    triggered: set[str] = set()
    for party in _settler_parties(world):
        decline = _cash_decline_bps(world, party)
        if decline is None or decline < _PANIC_CASH_DECLINE_BPS:
            continue
        if party_matter_value_cents(world, party) <= _PANIC_MIN_INVENTORY_CENTS:
            continue
        for material in _party_held_materials(world, party):
            _execute_panic_sell(world, party, material, triggered=triggered)

    if not triggered:
        return

    for party in _settler_parties(world):
        for material in _party_held_materials(world, party):
            if not _panic_cascade_candidates(world, material):
                continue
            held_value = party_matter_value_cents(world, party)
            if held_value <= _PANIC_MIN_INVENTORY_CENTS:
                continue
            decline = _cash_decline_bps(world, party)
            if decline is None or decline < _PANIC_CASH_DECLINE_BPS // 2:
                continue
            _execute_panic_sell(world, party, material, triggered=triggered)


def _update_trend_streak(world: World, party: PartyId, material: str, trend: str) -> int:
    party_store = _trend_streaks_store(world).setdefault(str(party), {})
    if trend == "+":
        party_store[material] = int(party_store.get(material, 0)) + 1
    else:
        party_store[material] = 0
    return int(party_store[material])


def _normal_inventory_target(world: World, party: PartyId, material: MaterialId) -> int:
    held = party_material_held(world, party, material)
    return max(10, held if held > 0 else 10)


def _material_price_history_days(world: World, material: str) -> int:
    """Distinct game-days with a recorded best ask for ``material``."""
    days: set[int] = set()
    for row in world.market_history:
        asks = row.get("best_asks_cents") or {}
        if material not in asks:
            continue
        tick = int(row.get("tick", 0))
        days.add(tick // TICKS_PER_GAME_DAY)
    return len(days)


def _close_spec_position(world: World, row: dict[str, Any], party: PartyId) -> None:
    material = MaterialId(str(row["material"]))
    qty = int(row.get("qty", 0))
    entry_px = int(row.get("entry_price_cents", 0))
    if qty <= 0:
        row["status"] = "closed"
        return
    ensure_inventory_from_stash(world, party, material, qty)
    held = world.inventory.qty(party, material)
    sell_qty = min(qty, held)
    if sell_qty <= 0:
        row["status"] = "closed"
        return
    exit_px = best_resting_ask_cents(world, material) or entry_px
    cancel_party_asks_for_material(world, party, material)
    place_sell_order(world, party, material, sell_qty, max(4, exit_px))
    pnl_per_unit = exit_px - entry_px
    label = _display_name(world, party)
    if pnl_per_unit >= 0:
        log_event(
            world,
            "world_feed",
            f"{label} closed a winning speculative bet on {material}",
            feed_source="spec_win",
            party=str(party),
            material=str(material),
        )
    else:
        log_event(
            world,
            "world_feed",
            f"{label} took a loss on speculative {material} — no rescue",
            feed_source="spec_loss",
            party=str(party),
            material=str(material),
        )
    row["status"] = "closed"
    row["closed_tick"] = int(world.tick)
    row["exit_price_cents"] = exit_px


def tick_speculative_positions(world: World) -> None:
    """Every 3 days: momentum buys; close after 14 days at market."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % (3 * TICKS_PER_GAME_DAY) != 0:
        return

    store = _spec_positions_store(world)
    for party in _settler_parties(world):
        ps = str(party)
        rows = store.setdefault(ps, [])
        for row in list(rows):
            if not isinstance(row, dict) or str(row.get("status", "open")) != "open":
                continue
            close_tick = int(row.get("close_tick", 0))
            if close_tick > 0 and int(world.tick) >= close_tick:
                _close_spec_position(world, row, party)

    slot = int(world.tick) % (3 * TICKS_PER_GAME_DAY)
    for party in _settler_parties(world):
        if _party_hash(party) % (3 * TICKS_PER_GAME_DAY) != slot:
            continue
        personality = get_settler_personality(world, party)
        if personality is None or personality.risk_tolerance <= _SPEC_MIN_RISK:
            continue
        cash = world.ledger.balance(party_cash_account(party))
        if cash <= _SPEC_MIN_CASH_CENTS:
            continue
        model = get_settler_world_model(world, party)
        for material, intel in sorted(model.material_intel.items()):
            if int(intel.get("days_observed", 0)) < _SPEC_MIN_DAYS_OBSERVED:
                continue
            if _material_price_history_days(world, material) < _SPEC_MIN_PRICE_HISTORY_DAYS:
                continue
            trend = str(intel.get("trend", "flat"))
            streak = _update_trend_streak(world, party, material, trend)
            if streak < _SPEC_MIN_TREND_STREAK:
                continue
            mat = MaterialId(material)
            ask = best_resting_ask_cents(world, mat)
            if ask is None or ask <= 0:
                continue
            target = _normal_inventory_target(world, party, mat) * _SPEC_BUY_MULTIPLIER
            result = market_buy(world, party, mat, target)
            if not result.get("ok"):
                continue
            filled = int(result.get("filled", 0))
            if filled <= 0:
                continue
            spent = int(result.get("spent_cents", 0))
            record_settler_buy(world, party, mat, filled, spent)
            entry_px = spent // filled if filled else int(ask)
            store.setdefault(str(party), []).append(
                {
                    "material": material,
                    "qty": filled,
                    "entry_price_cents": entry_px,
                    "opened_tick": int(world.tick),
                    "close_tick": int(world.tick) + _SPEC_POSITION_HORIZON,
                    "status": "open",
                }
            )
            break


def _has_forward_contract_infrastructure(world: World) -> bool:
    for contract in world.contracts:
        if str(contract.get("kind", "")) == "forward_contract":
            return True
    bilateral = world.scenario_state.get("bilateral_contracts")
    return isinstance(bilateral, list) and len(bilateral) > 0


def _pick_short_lender(
    world: World, borrower: PartyId, material: MaterialId
) -> PartyId | None:
    candidates: list[tuple[int, str, PartyId]] = []
    for party in _settler_parties(world):
        if party == borrower:
            continue
        stock = party_material_held(world, party, material)
        if stock < _SHORT_MIN_LENDER_STOCK:
            continue
        candidates.append((stock, str(party), party))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][2]


def _close_short_position(world: World, row: dict[str, Any]) -> None:
    party = PartyId(str(row["party"]))
    lender = PartyId(str(row["lender"]))
    material = MaterialId(str(row["material"]))
    qty = int(row.get("qty", 0))
    open_px = int(row.get("open_price_cents", 0))
    if qty <= 0 or party not in world.parties:
        row["status"] = "closed"
        return

    buy_result = market_buy(world, party, material, qty)
    filled = int(buy_result.get("filled", 0)) if buy_result.get("ok") else 0
    if filled < qty:
        shortfall = qty - filled
        log_event(
            world,
            "short_cover_failed",
            f"{party} failed to fully cover short on {material} ({shortfall} short)",
            party=str(party),
            material=str(material),
        )
    repay_qty = min(qty, filled, world.inventory.qty(party, material))
    if repay_qty > 0 and lender in world.parties:
        xfer = world.inventory.transfer(
            material=material,
            qty=repay_qty,
            from_party=party,
            to_party=lender,
        )
        if not isinstance(xfer, MatterErr):
            spent = int(buy_result.get("spent_cents", 0))
            record_settler_buy(world, party, material, repay_qty, spent * repay_qty // max(1, filled))

    borrow_fee = int(row.get("borrow_fee_cents", 0))
    if borrow_fee > 0 and party in world.parties:
        fee_result = world.ledger.transfer(
            debit=party_cash_account(party),
            credit=party_cash_account(lender),
            amount_cents=borrow_fee,
        )
        if isinstance(fee_result, MoneyErr):
            log_event(
                world,
                "short_fee_unpaid",
                f"{party} could not pay borrow fee on {material} short",
                party=str(party),
            )

    close_px = int(buy_result.get("spent_cents", 0)) // max(1, filled) if filled else open_px
    pnl_per_unit = open_px - close_px
    label = _display_name(world, party)
    if pnl_per_unit > 0:
        log_event(
            world,
            "world_feed",
            f"{label} profited on a short position in {material}",
            feed_source="short_win",
            party=str(party),
            material=str(material),
        )
    elif pnl_per_unit < 0:
        log_event(
            world,
            "world_feed",
            f"{label} took a loss covering a short in {material}",
            feed_source="short_loss",
            party=str(party),
            material=str(material),
        )
    row["status"] = "closed"
    row["closed_tick"] = int(world.tick)
    row["cover_price_cents"] = close_px


def tick_short_positions(world: World) -> None:
    """Weekly short selling when forward/bilateral contract infrastructure exists."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_WEEK != 0:
        return
    if not _has_forward_contract_infrastructure(world):
        return

    store = _short_positions_store(world)
    for row in list(store):
        if not isinstance(row, dict) or str(row.get("status", "open")) != "open":
            continue
        close_tick = int(row.get("close_tick", 0))
        if close_tick > 0 and int(world.tick) >= close_tick:
            _close_short_position(world, row)

    slot = int(world.tick) % _TICKS_PER_GAME_WEEK
    for party in _settler_parties(world):
        if _party_hash(party) % _TICKS_PER_GAME_WEEK != slot:
            continue
        personality = get_settler_personality(world, party)
        if personality is None or personality.risk_tolerance <= _SHORT_MIN_RISK:
            continue
        open_shorts = sum(
            1
            for r in store
            if isinstance(r, dict)
            and str(r.get("status", "open")) == "open"
            and str(r.get("party", "")) == str(party)
        )
        if open_shorts > 0:
            continue
        model = get_settler_world_model(world, party)
        for material, intel in sorted(model.material_intel.items()):
            if str(intel.get("trend", "flat")) != "+":
                continue
            mat = MaterialId(material)
            ask = best_resting_ask_cents(world, mat)
            if ask is None or ask <= 0:
                continue
            lender = _pick_short_lender(world, party, mat)
            if lender is None:
                continue
            qty = min(20, party_material_held(world, lender, mat) // 2)
            if qty <= 0:
                continue
            ensure_inventory_from_stash(world, lender, mat, qty)
            if world.inventory.qty(lender, mat) < qty:
                continue
            borrow = world.inventory.transfer(
                material=mat,
                qty=qty,
                from_party=lender,
                to_party=party,
            )
            if isinstance(borrow, MatterErr):
                continue
            sell_px = int(ask)
            place_sell_order(world, party, mat, qty, sell_px)
            notional = sell_px * qty
            borrow_fee = max(1, (notional * _SHORT_BORROW_FEE_BPS) // 10_000)
            store.append(
                {
                    "party": str(party),
                    "lender": str(lender),
                    "material": material,
                    "qty": qty,
                    "open_price_cents": sell_px,
                    "opened_tick": int(world.tick),
                    "close_tick": int(world.tick) + _SHORT_POSITION_HORIZON,
                    "borrow_fee_cents": borrow_fee,
                    "status": "open",
                }
            )
            log_event(
                world,
                "short_opened",
                f"{party} opened short on {material} borrowed from {lender}",
                party=str(party),
                lender=str(lender),
                material=material,
                qty=qty,
            )
            break
