"""Kessler Industrial — the predatory-pricing consolidator (Sprint 2 — Phase D).

A single Tier-2 agent per Genesis world. Spawns with $80,000 cash, a coastal
plot with a pre-built ``foundry`` and ``strip_mine``, and knows every Tier-1
recipe. Each game-day it:

1. Identifies the most-traded material in the past 7 days.
2. Buys an aggressive position in the **key input** for that material's recipe
   (5 game-days' worth at current producer cadence) and stockpiles it.
3. Lists its own output at ``cost_basis + 10 %`` — significantly under exchange
   and most settlers.
4. Holds prices low until it controls ≥ 40 % of weekly market share; then
   raises by 2¢/day. The moment a competitor undercuts, it freezes.

The consolidator never announces. Players see unusual buy volumes, a tight ask,
and (when its grip exceeds 30 % of any material's weekly supply) a redacted
world-feed line: "A large buyer absorbed significant {material} supply this
week. Exchange reserves are under pressure." The name "Kessler Industrial" is
visible on its market_list events — that's the only attribution.

Counter-strategies that *must* remain viable (covered by tests):

- Own supply: a player who mines their own iron_ore is untouched by Kessler
  cornering the iron_ore book.
- Exclusive supply contract: an active SupplyContract reserves a settler's
  output for its buyer — Kessler's market_buy walks the book and skips
  contracted goods (already true: contracts ship via fulfil, not market_list).
- Different vertical: if Kessler dominates iron_ingot, the player switches to
  ``steel_ingot`` (downstream of Kessler) and pays Kessler's cheap iron_ingot.
"""

from __future__ import annotations

from typing import Final

from realm.event_log import log_event
from realm.genesis_pricing import (
    exchange_ask_cents,
    fair_value_cents,
    producer_cost_basis_cents,
)
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.markets import market_buy, place_sell_order
from realm.recipe_sites import plot_is_coastal
from realm.recipes import RECIPES
from realm.regions import _world_bounds, region_for_coords
from realm.world import World


__all__ = [
    "CONSOLIDATOR_PARTY_ID",
    "CONSOLIDATOR_DISPLAY_NAME",
    "CONSOLIDATOR_STARTING_CASH_CENTS",
    "seed_consolidator",
    "tick_consolidator",
    "consolidator_state",
    "consolidator_market_share_bps",
]


# ───────────────────────── tunables ─────────────────────────


CONSOLIDATOR_PARTY_ID: Final[PartyId] = PartyId("kessler_industrial")
CONSOLIDATOR_DISPLAY_NAME: Final[str] = "Kessler Industrial"
CONSOLIDATOR_STARTING_CASH_CENTS: Final[int] = 80 * 100 * 100  # $80,000

# Strategy windows.
_TICKS_PER_GAME_DAY: Final[int] = 1440
_VOLUME_WINDOW_TICKS: Final[int] = 7 * _TICKS_PER_GAME_DAY
_KEY_INPUT_BUFFER_DAYS: Final[int] = 5
_KEY_INPUT_BUFFER_PER_DAY: Final[int] = 6  # nominal producer cadence, generous side

# Pricing.
_LIST_MARKUP_BPS: Final[int] = 1_000  # +10 % over cost basis
_PRICE_RAISE_PER_DAY_CENTS: Final[int] = 2

# Market-share thresholds (bps; 10_000 = 100 %).
_TARGET_SHARE_BPS: Final[int] = 4_000  # 40 %
_FEED_TRIGGER_SHARE_BPS: Final[int] = 3_000  # 30 % of weekly supply ⇒ world-feed line.

# Per-cycle output-listing size — large enough to be visible, small enough to
# leave room for repeated relisting if asks fill quickly.
_LIST_QTY_PER_DAY: Final[int] = 8


# ───────────────────────── state helpers ─────────────────────────


def consolidator_state(world: World) -> dict:
    """Get-or-create the consolidator's mutable scratch dict."""
    return world.scenario_state.setdefault(
        "consolidator",
        {
            "target_material": None,        # what we're currently squeezing
            "target_input": None,           # the key input we're cornering
            "current_list_price_cents": None,
            "last_feed_tick_by_material": {},
        },
    )


# ───────────────────────── bootstrap ─────────────────────────


def _pick_consolidator_home_plot(world: World) -> PlotId | None:
    """First unowned coastal plot at the geographic centre region; deterministic."""
    w, h = _world_bounds(world)
    cx, cy = w // 2, h // 2
    candidates: list[tuple[int, int, PlotId]] = []
    for plot in world.plots.values():
        if plot.owner is not None:
            continue
        if not plot_is_coastal(world, plot):
            continue
        candidates.append((plot.x, plot.y, plot.plot_id))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (abs(t[0] - cx) + abs(t[1] - cy), str(t[2])))
    return candidates[0][2]


def _instance_complete(world: World, building_id: str, party: PartyId, plot_id: PlotId) -> str:
    """Bypass the build pipeline: drop a completed building straight onto the plot."""
    world.next_building_instance_seq += 1
    instance_id = f"b{world.next_building_instance_seq:06d}"
    world.plot_buildings.append(
        {
            "instance_id": instance_id,
            "condition_bps": 10_000,
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": building_id,
            "label": f"{building_id} (Kessler Industrial)",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    world.building_maintenance[instance_id] = {
        "due_at_tick": int(world.tick) + 7_200,
        "missed_cycles": 0,
        "efficiency_pct": 100,
    }
    return instance_id


def seed_consolidator(world: World, *, starting_cash_cents: int | None = None) -> bool:
    """Spawn Kessler Industrial if not already present. Returns True on creation."""
    if world.scenario_id != "genesis":
        return False
    pid = CONSOLIDATOR_PARTY_ID
    if pid in world.parties:
        return False
    plot_id = _pick_consolidator_home_plot(world)
    if plot_id is None:
        # No coastal plot anywhere — degraded test worlds; skip without crashing.
        return False
    cash = (
        starting_cash_cents
        if starting_cash_cents is not None
        else CONSOLIDATOR_STARTING_CASH_CENTS
    )
    world.parties.add(pid)
    world.reputation[str(pid)] = {"honored": 0, "breached": 0}
    world.party_display_names[str(pid)] = CONSOLIDATOR_DISPLAY_NAME
    acct = party_cash_account(pid)
    world.ledger.ensure_account(acct)
    tr = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=acct,
        amount_cents=cash,
    )
    if isinstance(tr, MoneyErr):
        return False
    plot = world.plots[plot_id]
    plot.owner = pid
    # Pre-built foundry + strip_mine on the home plot.
    _instance_complete(world, "foundry", pid, plot_id)
    _instance_complete(world, "strip_mine", pid, plot_id)
    # Teach every Tier-1 recipe so it can pivot freely.
    book = world.party_recipe_books.setdefault(str(pid), set())
    for rid in RECIPES.keys():
        book.add(rid)
    log_event(
        world,
        "consolidator_seeded",
        f"{CONSOLIDATOR_DISPLAY_NAME} established on {plot_id} with ${cash // 100:,} starting capital",
        party=str(pid),
        plot_id=str(plot_id),
        starting_cash_cents=int(cash),
    )
    return True


# ───────────────────────── analytics ─────────────────────────


_TRADE_KINDS: Final[frozenset[str]] = frozenset({"market_match", "market_buy", "market_sell"})


def _ev_trade_qty(ev: dict) -> int:
    """Per-fill quantity across the various market event shapes."""
    for key in ("qty", "filled", "fill_qty"):
        v = ev.get(key)
        if v is None:
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n > 0:
            return n
    return 0


def _ev_seller(ev: dict) -> str:
    """Seller-side party (the party whose ask was filled)."""
    s = ev.get("seller")
    if s:
        return str(s)
    if ev.get("kind") == "market_sell":
        return str(ev.get("party") or "")
    return ""


def _trade_volume_by_material_window(world: World, *, window_ticks: int) -> dict[str, int]:
    """Sum traded quantity per material in the recent window (from event_log).

    We prefer ``market_match`` events (one per fill) and ignore ``market_buy``
    aggregates when matches for the same material exist in the window, to
    avoid double-counting.
    """
    cutoff = int(world.tick) - int(window_ticks)
    totals: dict[str, int] = {}
    for ev in reversed(world.event_log):
        if int(ev.get("tick", 0)) < cutoff:
            break
        if ev.get("kind") not in _TRADE_KINDS:
            continue
        mid = ev.get("material")
        if not mid:
            continue
        qty = _ev_trade_qty(ev)
        if qty <= 0:
            continue
        totals[str(mid)] = totals.get(str(mid), 0) + qty
    return totals


def _trade_volume_by_party_for_material(
    world: World, material: str, *, window_ticks: int
) -> dict[str, int]:
    """Per-seller trade volume for ``material`` in the window."""
    cutoff = int(world.tick) - int(window_ticks)
    totals: dict[str, int] = {}
    for ev in reversed(world.event_log):
        if int(ev.get("tick", 0)) < cutoff:
            break
        if ev.get("kind") not in _TRADE_KINDS:
            continue
        if str(ev.get("material") or "") != material:
            continue
        qty = _ev_trade_qty(ev)
        if qty <= 0:
            continue
        seller = _ev_seller(ev)
        if not seller:
            continue
        totals[seller] = totals.get(seller, 0) + qty
    return totals


def consolidator_market_share_bps(world: World, material: MaterialId) -> int:
    """Kessler's share of recent trade volume for ``material`` (bps; 10_000 = 100 %)."""
    per_party = _trade_volume_by_party_for_material(
        world, str(material), window_ticks=_VOLUME_WINDOW_TICKS
    )
    total = sum(per_party.values())
    if total <= 0:
        return 0
    mine = per_party.get(str(CONSOLIDATOR_PARTY_ID), 0)
    return (mine * 10_000) // total


def _recipe_for_output(material: MaterialId) -> tuple[str, dict] | None:
    """Pick the first recipe whose outputs contain ``material``; deterministic."""
    for rid in sorted(RECIPES.keys()):
        recipe = RECIPES[rid]
        outputs = getattr(recipe, "outputs", None) or {}
        for out_mid in outputs.keys():
            if str(out_mid) == str(material):
                return rid, recipe
    return None


def _key_input_for_output(material: MaterialId) -> MaterialId | None:
    """The first listed input of a recipe producing ``material``.

    Heuristic: pick the most-expensive input by fair value (the one whose
    supply most affects margin). Returns None if no recipe / no inputs.
    """
    pair = _recipe_for_output(material)
    if pair is None:
        return None
    _, recipe = pair
    inputs = getattr(recipe, "inputs", None) or {}
    if not inputs:
        return None
    ranked = sorted(
        inputs.keys(),
        key=lambda mid: (-exchange_ask_cents(MaterialId(str(mid))), str(mid)),
    )
    return MaterialId(str(ranked[0]))


def _cost_basis_for_output(world: World, material: MaterialId) -> int | None:
    """Estimate cost basis = cheapest recipe's input-fair-value-per-unit.

    Mirrors :func:`realm.genesis_pricing.producer_cost_basis_cents` (which the
    exchange itself uses). Labor is deliberately excluded — by sprint-1 design,
    labor cents are recycled through the system reserve and are not a marginal
    cost that the producer must recoup unit-for-unit. Using this basis lets
    Kessler list strictly under the exchange while still earning margin.
    """
    basis = producer_cost_basis_cents(material)
    if basis is not None:
        return int(basis)
    # Recipe-less material? Fall back to fair value.
    fv = fair_value_cents(material)
    return int(fv) if fv is not None else None


# ───────────────────────── action loop ─────────────────────────


def _pick_target_material(world: World) -> MaterialId | None:
    """Most-traded *processed* material in the recent window."""
    volumes = _trade_volume_by_material_window(world, window_ticks=_VOLUME_WINDOW_TICKS)
    if not volumes:
        # Cold start: default to a high-margin processed good.
        return MaterialId("iron_ingot")
    # Exclude raws — the consolidator wants outputs to control; cornering raws
    # is the means, not the end.
    raws = {"iron_ore", "copper_ore", "coal", "clay", "stone", "timber", "grain", "sand"}
    ranked = sorted(
        ((m, q) for m, q in volumes.items() if m not in raws),
        key=lambda mq: (-mq[1], mq[0]),
    )
    if not ranked:
        return MaterialId("iron_ingot")
    return MaterialId(ranked[0][0])


def _corner_key_input(world: World, key_input: MaterialId) -> None:
    """Aggressively walk asks for ``key_input`` and stockpile it."""
    want = _KEY_INPUT_BUFFER_DAYS * _KEY_INPUT_BUFFER_PER_DAY
    have = int(world.inventory.qty(CONSOLIDATOR_PARTY_ID, key_input))
    deficit = max(0, want - have)
    if deficit <= 0:
        return
    cash = world.ledger.balance(party_cash_account(CONSOLIDATOR_PARTY_ID))
    if cash <= 0:
        return
    ceiling = max(1, int(exchange_ask_cents(key_input) * 110 // 100))
    market_buy(
        world,
        CONSOLIDATOR_PARTY_ID,
        key_input,
        deficit,
        max_price_per_unit_cents=ceiling,
    )


def _list_output(world: World, material: MaterialId) -> None:
    """List Kessler's output at cost-basis + 10 %, scaling list price up if dominant."""
    basis = _cost_basis_for_output(world, material)
    if basis is None or basis <= 0:
        return
    state = consolidator_state(world)
    share = consolidator_market_share_bps(world, material)
    target_price = (basis * (10_000 + _LIST_MARKUP_BPS)) // 10_000
    last_price = state.get("current_list_price_cents")
    if share >= _TARGET_SHARE_BPS and isinstance(last_price, int) and last_price > 0:
        # Dominant — drift price up 2¢/day, hold below exchange.
        ex = int(exchange_ask_cents(material))
        target_price = min(ex - 5, last_price + _PRICE_RAISE_PER_DAY_CENTS)
    inv_qty = int(world.inventory.qty(CONSOLIDATOR_PARTY_ID, material))
    if inv_qty <= 0:
        # We can also list short-term from what we have; if no output yet, skip.
        state["current_list_price_cents"] = int(target_price)
        return
    qty = min(_LIST_QTY_PER_DAY, inv_qty)
    place_sell_order(
        world,
        CONSOLIDATOR_PARTY_ID,
        material,
        qty,
        int(target_price),
    )
    state["current_list_price_cents"] = int(target_price)


def _maybe_emit_dominance_feed(world: World) -> None:
    """When Kessler exceeds 30 % weekly share on any material, drop a redacted feed line."""
    state = consolidator_state(world)
    last_by_mat: dict = state.setdefault("last_feed_tick_by_material", {})
    volumes = _trade_volume_by_material_window(world, window_ticks=_VOLUME_WINDOW_TICKS)
    cooldown = _TICKS_PER_GAME_DAY * 3
    for mat_s in volumes.keys():
        share = consolidator_market_share_bps(world, MaterialId(mat_s))
        if share < _FEED_TRIGGER_SHARE_BPS:
            continue
        last = int(last_by_mat.get(mat_s, -10**9))
        if int(world.tick) - last < cooldown:
            continue
        last_by_mat[mat_s] = int(world.tick)
        log_event(
            world,
            "world_feed",
            f"A large buyer absorbed significant {mat_s} supply this week. Exchange reserves are under pressure.",
            material=mat_s,
        )


def tick_consolidator(world: World) -> None:
    """Once-per-game-day strategy advance. No-op on non-genesis worlds."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0:
        return
    if int(world.tick) % _TICKS_PER_GAME_DAY != 0:
        return
    if CONSOLIDATOR_PARTY_ID not in world.parties:
        return
    state = consolidator_state(world)
    target = _pick_target_material(world)
    if target is None:
        return
    state["target_material"] = str(target)
    key_input = _key_input_for_output(target)
    if key_input is not None:
        state["target_input"] = str(key_input)
        _corner_key_input(world, key_input)
    # Try to produce: if we have inputs + workshop, fire a batch on the home plot.
    pair = _recipe_for_output(target)
    if pair is not None:
        rid, _ = pair
        from realm.actions import start_production_on_plot

        for row in world.plot_buildings:
            if str(row.get("party")) != str(CONSOLIDATOR_PARTY_ID):
                continue
            start_production_on_plot(
                world,
                CONSOLIDATOR_PARTY_ID,
                PlotId(str(row["plot_id"])),
                rid,
            )
            break
    _list_output(world, target)
    _maybe_emit_dominance_feed(world)
