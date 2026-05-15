"""Phase 7D — stores: the consumer economy.

A store is a plot with a ``store`` building. Its owner stocks it from
their own inventory (``stock_store``), sets retail prices
(``set_store_price``), and earns revenue when laborers in the same town
buy food and fuel each game-day (``tick_laborer_spending``).

This module replaces the artificial ``pop_hub`` demand layer with real
consumer demand. Money only moves through transfers: laborer cash → store
owner cash. The store's inventory is real matter that came from somewhere
(production, market purchase, or shipment). Conservation holds.

Need → eligible materials:

- ``food``  → grain, bread, fish
- ``fuel``  → coal, electricity
- ``shelter`` is met by the residence building (Phase 7C), not by a store.

Each unit of food restores ``FOOD_PER_UNIT`` of the food need; each unit
of fuel restores ``FUEL_PER_UNIT`` of the fuel need. Laborers visit at
most one store per need per game-day, buy enough to push the need to
1.0 (capped by what the store has + what the laborer can afford), and
prefer the cheapest store in town.
"""

from __future__ import annotations

from typing import Final

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.world import World


# ───────────────────────── tunables ─────────────────────────


STORE_BUILDING_ID: Final[str] = "store"

FOOD_MATERIALS: Final[tuple[MaterialId, ...]] = (
    MaterialId("grain"),
    MaterialId("bread"),
    MaterialId("fish"),
)
FUEL_MATERIALS: Final[tuple[MaterialId, ...]] = (
    MaterialId("coal"),
    MaterialId("electricity"),
)

NEED_MATERIALS: Final[dict[str, tuple[MaterialId, ...]]] = {
    "food": FOOD_MATERIALS,
    "fuel": FUEL_MATERIALS,
}

FOOD_PER_UNIT: Final[float] = 0.20
"""How much one unit of food restores on the food need."""

FUEL_PER_UNIT: Final[float] = 0.30
"""How much one unit of fuel restores on the fuel need."""

NEED_RESTORATION_PER_UNIT: Final[dict[str, float]] = {
    "food": FOOD_PER_UNIT,
    "fuel": FUEL_PER_UNIT,
}

SPENDING_TRIGGER_NEED: Final[float] = 0.70
"""A laborer visits a store for a need when their level drops below this."""

NEED_TARGET_AFTER_PURCHASE: Final[float] = 1.00
"""Laborers buy enough units to push the need to (at most) this level."""

NPC_STORE_MARKUP_BPS: Final[int] = 14_000
"""NPC seeded stores sell at ~40% margin so players can profitably undercut."""

# Genesis training-wheels retail (¢/unit) — subsistence-priced so a laborer on
# the $200 bootstrap stake can buy several meals before wages land.
GENESIS_STORE_RETAIL_CENTS: Final[dict[str, int]] = {
    "grain": 60,
    "bread": 70,
    "fish": 80,
    "coal": 90,
    "electricity": 120,
}

NPC_STORE_GRAIN_QTY: Final[int] = 250
NPC_STORE_COAL_QTY: Final[int] = 200
"""Initial stock per NPC store. Enough to feed a town for a few days but not
so much that laborers never need new entrants — designed to compress."""

NPC_STOREKEEPER_STARTING_CASH_CENTS: Final[int] = 20_000 * 100
"""Phase 7F: starting cash for the settlement storekeeper NPC so they can
restock their stores via real B2B buy orders (including across islands)."""


__all__ = [
    "STORE_BUILDING_ID",
    "FOOD_MATERIALS",
    "FUEL_MATERIALS",
    "NEED_MATERIALS",
    "NEED_RESTORATION_PER_UNIT",
    "SPENDING_TRIGGER_NEED",
    "NEED_TARGET_AFTER_PURCHASE",
    "NPC_STORE_MARKUP_BPS",
    "stock_store",
    "set_store_price",
    "withdraw_store_stock",
    "tick_laborer_spending",
    "stores_for_town",
    "store_inventory_qty",
    "store_price_cents",
    "is_store_plot",
    "seed_genesis_npc_stores",
]


# ───────────────────────── store state ─────────────────────────


def is_store_plot(world: World, plot_id: PlotId) -> bool:
    """True when this plot has at least one completed ``store`` building."""
    now = int(world.tick)
    for b in world.plot_buildings:
        if str(b.get("plot_id")) != str(plot_id):
            continue
        if str(b.get("building_id")) != STORE_BUILDING_ID:
            continue
        if int(b.get("completes_at_tick", 0)) > now:
            continue
        return True
    return False


def store_owner(world: World, plot_id: PlotId) -> PartyId | None:
    plot = world.plots.get(plot_id)
    return plot.owner if plot is not None else None


def store_inventory_qty(world: World, plot_id: PlotId, material: MaterialId) -> int:
    return int(
        world.store_inventories.get(str(plot_id), {}).get(str(material), 0)
    )


def store_price_cents(world: World, plot_id: PlotId, material: MaterialId) -> int | None:
    price_map = world.store_prices.get(str(plot_id), {})
    v = price_map.get(str(material))
    return int(v) if v is not None else None


# ───────────────────────── store catchment ─────────────────────────


def stores_for_town(world: World, town_id: str) -> list[PlotId]:
    """Active store plots in this town."""
    t = world.towns.get(town_id)
    if t is None:
        return []
    out: list[PlotId] = []
    for pid in t.store_plots:
        if is_store_plot(world, pid):
            out.append(pid)
    return out


def _register_store_with_town(world: World, plot_id: PlotId) -> None:
    """Idempotent: attach this store's plot to its town's ``store_plots``.

    Picks the nearest town to ``plot_id`` (by Chebyshev distance to any
    residential plot) within ``TOWN_PROXIMITY_TILES``. Stores outside any
    town's catchment are not registered (laborers in towns can't reach
    them).
    """
    from realm.population.towns import TOWN_PROXIMITY_TILES

    plot = world.plots.get(plot_id)
    if plot is None:
        return
    best: tuple[int, str] | None = None
    for tid, t in world.towns.items():
        for rp in t.residential_plots:
            rplot = world.plots.get(rp)
            if rplot is None:
                continue
            d = max(abs(plot.x - rplot.x), abs(plot.y - rplot.y))
            if d <= TOWN_PROXIMITY_TILES:
                cand = (d, tid)
                if best is None or cand < best:
                    best = cand
                break
    if best is None:
        return
    t = world.towns[best[1]]
    if plot_id not in t.store_plots:
        t.store_plots.append(plot_id)


# ───────────────────────── owner actions ─────────────────────────


def stock_store(
    world: World, party: PartyId, plot_id: PlotId, material: MaterialId, qty: int
) -> dict:
    """Transfer ``qty`` units of ``material`` from ``party`` into the store on ``plot_id``.

    Returns ``{"ok": True, "qty": int}`` on success, otherwise
    ``{"ok": False, "reason": "..."}``.
    """
    if qty <= 0:
        return {"ok": False, "reason": "qty must be positive"}
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    if not is_store_plot(world, plot_id):
        return {"ok": False, "reason": "no store on plot"}
    rm = world.inventory.remove(party, material, int(qty))
    if isinstance(rm, MatterErr):
        return {"ok": False, "reason": rm.reason}
    inv = world.store_inventories.setdefault(str(plot_id), {})
    inv[str(material)] = int(inv.get(str(material), 0)) + int(qty)
    _register_store_with_town(world, plot_id)
    log_event(
        world,
        "store_stock",
        f"{party} stocked {qty} {material} at store {plot_id}",
        party=str(party),
        plot_id=str(plot_id),
        material=str(material),
        qty=int(qty),
    )
    return {"ok": True, "qty": int(qty)}


def withdraw_store_stock(
    world: World, party: PartyId, plot_id: PlotId, material: MaterialId, qty: int
) -> dict:
    """Pull goods back out of the store into the owner's inventory."""
    if qty <= 0:
        return {"ok": False, "reason": "qty must be positive"}
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    inv = world.store_inventories.setdefault(str(plot_id), {})
    cur = int(inv.get(str(material), 0))
    if cur < qty:
        return {"ok": False, "reason": f"insufficient store stock (have {cur}, need {qty})"}
    inv[str(material)] = cur - int(qty)
    ad = world.inventory.add(party, material, int(qty))
    if isinstance(ad, MatterErr):
        # Restore the store row and bail.
        inv[str(material)] = cur
        return {"ok": False, "reason": ad.reason}
    log_event(
        world,
        "store_withdraw",
        f"{party} withdrew {qty} {material} from store {plot_id}",
        party=str(party),
        plot_id=str(plot_id),
        material=str(material),
        qty=int(qty),
    )
    return {"ok": True, "qty": int(qty)}


def set_store_price(
    world: World, party: PartyId, plot_id: PlotId, material: MaterialId, price_cents: int
) -> dict:
    """Set the retail price (in cents) for ``material`` at this store."""
    if price_cents < 0:
        return {"ok": False, "reason": "price must be non-negative"}
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    if not is_store_plot(world, plot_id):
        return {"ok": False, "reason": "no store on plot"}
    prices = world.store_prices.setdefault(str(plot_id), {})
    prices[str(material)] = int(price_cents)
    return {"ok": True, "price_cents": int(price_cents)}


# ───────────────────────── laborer spending ─────────────────────────


def _cheapest_store_for_need(
    world: World,
    town_id: str,
    need: str,
) -> tuple[PlotId, MaterialId, int] | None:
    """Find the cheapest available (store, material, unit_price) for a need.

    Returns ``None`` when nothing relevant is in stock anywhere in the town.
    """
    materials = NEED_MATERIALS.get(need, ())
    best: tuple[PlotId, MaterialId, int] | None = None
    for pid in stores_for_town(world, town_id):
        inv = world.store_inventories.get(str(pid), {})
        prices = world.store_prices.get(str(pid), {})
        for mid in materials:
            qty = int(inv.get(str(mid), 0))
            if qty <= 0:
                continue
            price = prices.get(str(mid))
            if price is None or int(price) <= 0:
                continue
            cand = (pid, mid, int(price))
            if best is None or int(price) < best[2]:
                best = cand
    return best


def _execute_purchase(
    world: World, laborer_id: str, plot_id: PlotId, material: MaterialId, units: int
) -> dict:
    """Move ``units`` of ``material`` from store to a phantom-consumed sink.

    Cash flow: laborer's ledger account is debited (units × store price),
    store owner's cash is credited the same total. Store inventory drops
    by ``units``; the laborer's need restoration is applied. Material is
    consumed (entering the laborer's "metabolism") — it disappears from
    the matter ledger, mirroring how production inputs are consumed.

    Conservation:

    - Money: laborer.cash -> store_owner.cash, exact transfer.
    - Matter: store_inventory -= units (consumed by laborer; not produced).
      The matter that disappears here is symmetric with matter consumed
      as a production input — needs are the laborer-side counterpart to
      industrial inputs. This keeps the total *circulating* material
      stock finite without dropping the floor out of the economy.

    Returns the spend amount + the units actually moved (caller decides
    whether to apply need restoration based on this).
    """
    from realm.population.laborers import laborer_cash_account

    lab = world.laborers.get(laborer_id)
    if lab is None:
        return {"ok": False, "reason": "unknown laborer", "spent": 0, "units": 0}
    inv = world.store_inventories.setdefault(str(plot_id), {})
    have = int(inv.get(str(material), 0))
    units = min(int(units), have)
    if units <= 0:
        return {"ok": False, "reason": "store empty", "spent": 0, "units": 0}
    prices = world.store_prices.get(str(plot_id), {})
    unit_price = int(prices.get(str(material), 0))
    if unit_price <= 0:
        return {"ok": False, "reason": "no price set", "spent": 0, "units": 0}
    owner = store_owner(world, plot_id)
    if owner is None:
        return {"ok": False, "reason": "no plot owner", "spent": 0, "units": 0}
    lab_acct = laborer_cash_account(laborer_id)
    bal = world.ledger.balance(lab_acct)
    affordable = bal // unit_price if unit_price > 0 else 0
    units = min(units, int(affordable))
    if units <= 0:
        return {"ok": False, "reason": "insufficient cash", "spent": 0, "units": 0}
    total = units * unit_price
    tr = world.ledger.transfer(
        debit=lab_acct,
        credit=party_cash_account(owner),
        amount_cents=int(total),
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason, "spent": 0, "units": 0}
    inv[str(material)] = have - units
    lab.cash_cents = world.ledger.balance(lab_acct)
    # Track per-store daily revenue for UI / analytics.
    rev = world.store_revenue_today.setdefault(str(plot_id), 0)
    world.store_revenue_today[str(plot_id)] = int(rev) + int(total)
    log_event(
        world,
        "store_purchase",
        f"{lab.display_name} bought {units} {material} at {plot_id} for ${total/100:.2f}",
        laborer_id=laborer_id,
        plot_id=str(plot_id),
        material=str(material),
        units=int(units),
        unit_price_cents=int(unit_price),
        total_cents=int(total),
        store_owner=str(owner),
    )
    if int(inv.get(str(material), 0)) == 0:
        log_event(
            world,
            "store_out_of_stock",
            f"Store {plot_id} ran out of {material}.",
            plot_id=str(plot_id),
            material=str(material),
            store_owner=str(owner),
        )
    return {"ok": True, "spent": int(total), "units": int(units)}


def tick_laborer_spending(world: World) -> dict[str, int]:
    """Drive one game-day of laborer→store consumption.

    Only fires at game-day boundaries (every ``TICKS_PER_GAME_DAY``).
    Idempotent within the same day. For each laborer with a home town:

    1. If ``food`` < trigger and a town store sells food: buy enough to
       push ``food`` back to 1.0 (cap by stock + cash).
    2. Same for ``fuel``.

    Returns a small counter dict (``purchases``, ``laborers_serviced``).
    """
    from realm.population.laborers import TICKS_PER_GAME_DAY

    stats = {"purchases": 0, "laborers_serviced": 0}
    if not world.laborers:
        return stats
    # Reset per-day store revenue at the day boundary.
    last_day = int(world.scenario_state.get("store_last_spend_tick", -1))
    now = int(world.tick)
    if last_day >= 0 and now - last_day < TICKS_PER_GAME_DAY:
        return stats
    world.scenario_state["store_last_spend_tick"] = now
    world.store_revenue_today.clear()
    from realm.events.world_events import (
        EPIDEMIC_MEDICINE_HEAL_AMOUNT,
        active_epidemic_for_town,
        consume_medicine_for_treatment,
    )

    for lid, lab in list(world.laborers.items()):
        if not lab.home_town:
            continue
        town = world.towns.get(lab.home_town)
        if town is None:
            continue
        any_purchase = False
        for need in ("food", "fuel"):
            level = float(lab.needs.get(need, 1.0))
            if level >= SPENDING_TRIGGER_NEED:
                continue
            offer = _cheapest_store_for_need(world, town.town_id, need)
            if offer is None:
                continue
            plot_id, material, _unit_price = offer
            per_unit = NEED_RESTORATION_PER_UNIT[need]
            deficit = max(0.0, NEED_TARGET_AFTER_PURCHASE - level)
            units_needed = int(deficit / per_unit) + (
                1 if (deficit % per_unit) > 1e-9 else 0
            )
            if units_needed <= 0:
                continue
            # Buy what cash allows (often 1 unit) rather than failing when the
            # ideal refill needs more than the laborer can afford.
            from realm.population.laborers import laborer_cash_account

            unit_px = store_price_cents(world, plot_id, material) or 0
            if unit_px > 0:
                affordable = world.ledger.balance(laborer_cash_account(lid)) // int(
                    unit_px
                )
                if affordable <= 0:
                    continue
                units_needed = min(units_needed, int(affordable))
            res = _execute_purchase(world, lid, plot_id, material, units_needed)
            if res.get("ok"):
                bought = int(res.get("units", 0))
                lab.needs[need] = min(
                    NEED_TARGET_AFTER_PURCHASE, level + bought * per_unit
                )
                stats["purchases"] += 1
                any_purchase = True
        # Phase 8C: if an epidemic is active in this town and a store sells
        # medicine, the laborer buys one unit to treat themselves. Price is
        # whatever the store owner set (5-10× normal during an outbreak,
        # which is the market signal apothecaries respond to).
        if active_epidemic_for_town(world, lab.home_town) is not None:
            med_offer = _cheapest_store_for_material(
                world, lab.home_town, MaterialId("medicine")
            )
            if med_offer is not None:
                plot_id, _price = med_offer
                res = _execute_purchase(world, lid, plot_id, MaterialId("medicine"), 1)
                if res.get("ok") and int(res.get("units", 0)) >= 1:
                    if consume_medicine_for_treatment(world, lab.home_town, lid):
                        lab.health = min(1.0, lab.health + EPIDEMIC_MEDICINE_HEAL_AMOUNT)
                    stats["purchases"] += 1
                    any_purchase = True
        if any_purchase:
            stats["laborers_serviced"] += 1
    return stats


def _cheapest_store_for_material(
    world: World, town_id: str, material: MaterialId
) -> tuple[PlotId, int] | None:
    """Return ``(plot_id, unit_price)`` for the cheapest in-stock listing of
    ``material`` in this town's stores."""
    cheapest: tuple[PlotId, int] | None = None
    for pid in stores_for_town(world, town_id):
        qty = store_inventory_qty(world, pid, material)
        if qty <= 0:
            continue
        price = store_price_cents(world, pid, material)
        if price is None or price <= 0:
            continue
        if cheapest is None or price < cheapest[1]:
            cheapest = (pid, int(price))
    return cheapest


# ───────────────────────── seeded NPC stores ─────────────────────────


def _baseline_unit_cost_cents(material: MaterialId) -> int:
    """Use the existing exchange baseline as the "cost" the NPC marks up over."""
    from realm.economy.pricing import _baseline_exchange_ask_cents

    try:
        return int(_baseline_exchange_ask_cents(material))
    except Exception:
        # Conservative fallback when genesis_pricing doesn't recognise the id.
        return 200


def _npc_retail_price(material: MaterialId) -> int:
    base = _baseline_unit_cost_cents(material)
    return max(1, (base * NPC_STORE_MARKUP_BPS) // 10_000)


def _genesis_store_retail_price(material: MaterialId) -> int:
    """Fixed subsistence retail for bootstrap NPC stores (not exchange markup)."""
    fixed = GENESIS_STORE_RETAIL_CENTS.get(str(material))
    if fixed is not None:
        return int(fixed)
    return _npc_retail_price(material)


def seed_genesis_npc_stores(world: World) -> list[PlotId]:
    """Seat one NPC-owned general store in each starting town.

    The store is stocked with grain + coal at the markup-baseline price.
    These are 'training-wheels' stores: priced ~40% above wholesale so
    players can profitably undercut. Returns the list of store plot ids.

    Storage is owned by a synthetic ``genesis_storekeeper`` party (one
    entity across all islands — it doesn't need to be an entrepreneur,
    it's a placeholder until players step in).
    """
    if not world.towns:
        return []
    from realm.core.ids import PartyId
    from realm.core.ledger import party_cash_account, system_reserve_account
    from realm.production.decay import BUILDING_CONDITION_FULL_BPS
    from realm.production.buildings import BUILDINGS

    storekeeper = PartyId("genesis_storekeeper")
    if storekeeper not in world.parties:
        world.parties.add(storekeeper)
        world.reputation[str(storekeeper)] = {"honored": 0, "breached": 0}
        world.party_display_names[str(storekeeper)] = "Settlement Storekeeper"
        sk_acct = party_cash_account(storekeeper)
        world.ledger.ensure_account(sk_acct)
        # Phase 7F: fund the storekeeper so they can post real B2B grain
        # buy orders when their store runs low (cross-island demand).
        tr = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=sk_acct,
            amount_cents=NPC_STOREKEEPER_STARTING_CASH_CENTS,
        )
        if isinstance(tr, MoneyErr):
            raise ValueError(tr.reason)

    plot_islands = world.scenario_state.get("plot_islands") or {}
    seeded: list[PlotId] = []
    for town in world.towns.values():
        # Pick the first unowned land plot near the town's center plot.
        center = world.plots.get(town.center_plot)
        if center is None:
            continue
        choice: PlotId | None = None
        # Prefer an unowned land plot adjacent to a residence.
        candidates = []
        for pid_s, isl in plot_islands.items():
            if int(isl) != int(town.island_id):
                continue
            p = world.plots.get(PlotId(pid_s))
            if p is None or p.owner is not None:
                continue
            # Distance from center.
            d = max(abs(p.x - center.x), abs(p.y - center.y))
            candidates.append((d, pid_s, p.x, p.y))
        candidates.sort()
        for _d, pid_s, _x, _y in candidates:
            choice = PlotId(pid_s)
            break
        if choice is None:
            continue
        plot = world.plots[choice]
        plot.owner = storekeeper
        # Directly insert a completed store (bootstrap seed, not in-game build).
        spec = BUILDINGS[STORE_BUILDING_ID]
        world.next_building_instance_seq += 1
        instance_id = f"b{world.next_building_instance_seq:06d}"
        world.plot_buildings.append(
            {
                "instance_id": instance_id,
                "condition_bps": BUILDING_CONDITION_FULL_BPS,
                "plot_id": str(choice),
                "party": str(storekeeper),
                "building_id": STORE_BUILDING_ID,
                "label": str(spec["label"]),
                "cost_cents": 0,
                "build_mode": "bootstrap",
                "completes_at_tick": 0,
            }
        )
        town.store_plots.append(choice)
        # Stock grain + coal directly (matter from system reserve mirrors
        # the way exchange inventory was seeded historically).
        for mid, qty in (
            (MaterialId("grain"), NPC_STORE_GRAIN_QTY),
            (MaterialId("coal"), NPC_STORE_COAL_QTY),
        ):
            ad = world.inventory.add(storekeeper, mid, qty)
            if isinstance(ad, MatterErr):
                continue
            stock_store(world, storekeeper, choice, mid, qty)
            set_store_price(world, storekeeper, choice, mid, _genesis_store_retail_price(mid))
        seeded.append(choice)
    return seeded
