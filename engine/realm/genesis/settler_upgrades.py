"""Settler vertical integration — weekly margin-analysis upgrade triggers.

Sprint 2 — Phase B.

Once per game-week, each settler reviews the margin they're earning on their
primary line vs. the margin they'd earn one production step further down the
chain (vertical integration). When the downstream margin is sufficiently
better and the settler has the cash buffer, they kick off a turnkey build of
the upgrade workshop.

Upgrade paths (extract → process):
    strip_mine + iron_ore     → foundry      → iron_ingot (smelt_iron)
    strip_mine + coal         → power_shed   → electricity (coal_generator)
    timber_yard               → wood_shop    → lumber     (sawmill)
    grain_row                 → gristmill    → flour      (mill_flour)

Triggers when ``vertical_margin > current_margin * 2.5`` and
``cash >= turnkey_total_cents * 1.5``. No special-case scripting — if the
margin math doesn't fire, the upgrade doesn't fire (per Sprint 2 design rule).

Buffer buying (Phase B.4): when a settler's input price for ``material`` has
risen by ``SETTLER_BUFFER_BUY_PRICE_RISE_BPS`` (20%) over the last 7 days
*and* they have an active workshop that consumes that material, they buy
``SETTLER_BUFFER_BUY_DAYS_FORWARD`` (3) game-days of forward consumption in
a single sweep.
"""

from __future__ import annotations

from typing import Any

from realm.production.buildings import BUILDINGS, build_on_plot
from realm.events.event_log import log_event
from realm.economy.pricing import exchange_ask_cents
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.economy.markets import market_buy
from realm.production.recipes import RECIPES
from realm.genesis.settler_cost_basis import (
    SETTLER_BUFFER_BUY_DAYS_FORWARD,
    SETTLER_BUFFER_BUY_PRICE_RISE_BPS,
    record_settler_buy,
    settler_input_avg_paid_cents,
    settler_input_price_change_bps_7d,
    settler_output_basis_cents,
)
from realm.world import World


__all__ = [
    "tick_settler_margin_review",
    "VERTICAL_TRIGGER_RATIO_BPS",
    "VERTICAL_CASH_BUFFER_BPS",
]


VERTICAL_TRIGGER_RATIO_BPS: int = 25_000  # vertical must beat current by 2.5×
VERTICAL_CASH_BUFFER_BPS: int = 15_000  # cash ≥ turnkey × 1.5

_TICKS_PER_GAME_DAY: int = 1440
_REVIEW_INTERVAL_TICKS: int = 7 * _TICKS_PER_GAME_DAY


# (upstream_building, upstream_material, downstream_building, downstream_recipe,
#  downstream_output)
_UPGRADE_PATHS: list[tuple[str, str, str, str, str]] = [
    ("strip_mine", "iron_ore", "foundry", "smelt_iron", "iron_ingot"),
    ("strip_mine", "coal", "power_shed", "coal_generator", "electricity"),
    ("timber_yard", "timber", "wood_shop", "sawmill", "lumber"),
    ("grain_row", "grain", "gristmill", "mill_flour", "flour"),
]


# ───────────────────────── helpers ─────────────────────────


def _party_owns_building(world: World, party: PartyId, building_id: str) -> bool:
    target = str(building_id)
    for row in world.plot_buildings:
        if str(row.get("party")) != str(party):
            continue
        if str(row.get("building_id")) == target:
            return True
    return False


def _party_owns_plot_for_building(
    world: World, party: PartyId, building_id: str
) -> PlotId | None:
    """A plot owned by ``party`` that already has ``building_id`` on it (for upgrade siting)."""
    target = str(building_id)
    for row in world.plot_buildings:
        if str(row.get("party")) != str(party):
            continue
        if str(row.get("building_id")) == target:
            return PlotId(str(row.get("plot_id")))
    return None


def _market_unit_price(world: World, material: MaterialId) -> int:
    """Best deterministic estimate of what 1 unit of ``material`` clears at right now."""
    return int(exchange_ask_cents(material, world=world))


def _recipe_per_unit_input_cost(
    world: World, party: PartyId, recipe_id: str, output_material: MaterialId
) -> tuple[int, int] | None:
    """Per-unit input cost & per-unit labor for ``recipe_id`` producing ``output_material``.

    Inputs the settler is currently buying use ``settler_input_avg_paid``; if no
    history exists, fall back to the current exchange ask. Returns
    ``(input_cents_per_output_unit, labor_cents_per_output_unit)`` or ``None``
    if the recipe doesn't actually produce ``output_material``.
    """
    rec = RECIPES.get(recipe_id)
    if rec is None:
        return None
    out_qty = int(rec.outputs.get(output_material, 0))
    if out_qty <= 0:
        return None
    in_cents = 0
    for inp, in_qty in rec.inputs.items():
        unit = settler_input_avg_paid_cents(world, party, inp)
        if unit is None:
            unit = _market_unit_price(world, inp)
        in_cents += int(unit) * int(in_qty)
    labor_per_unit = (int(getattr(rec, "labor_cents", 0)) + out_qty - 1) // out_qty
    return ((in_cents + out_qty - 1) // out_qty, labor_per_unit)


# ───────────────────────── core review pass ─────────────────────────


def _maybe_trigger_upgrade(
    world: World, party: PartyId, path: tuple[str, str, str, str, str]
) -> bool:
    """Evaluate one upgrade path; build the downstream workshop if the math justifies it.

    Returns True if a build was kicked off this call (caller can stop further
    upgrade attempts this week — one big capex per week is plenty).
    """
    upstream_b, upstream_mat, downstream_b, downstream_recipe, downstream_out = path

    src_plot = _party_owns_plot_for_building(world, party, upstream_b)
    if src_plot is None:
        return False
    if _party_owns_building(world, party, downstream_b):
        return False  # already vertically integrated for this path

    upstream_mid = MaterialId(upstream_mat)
    downstream_mid = MaterialId(downstream_out)

    # ── current margin: settler sells upstream_mat at market.
    upstream_price = _market_unit_price(world, upstream_mid)
    upstream_basis = settler_output_basis_cents(world, party, upstream_mid)
    # A settler with no production history for the upstream input is treated as a
    # zero-cost producer (they'll start extracting once the workshop is online).
    if upstream_basis is None:
        upstream_basis = 0
    current_margin = max(0, upstream_price - upstream_basis)

    # ── vertical margin: settler keeps upstream_mat as zero-cost input, smelts/processes,
    #    sells downstream_mat at market. Use the *recipe* cost ignoring upstream input cost
    #    (because they would extract it themselves).
    rec = RECIPES.get(downstream_recipe)
    if rec is None:
        return False
    downstream_price = _market_unit_price(world, downstream_mid)
    rec_out_qty = int(rec.outputs.get(downstream_mid, 0))
    if rec_out_qty <= 0:
        return False
    other_input_cents = 0
    for inp, in_qty in rec.inputs.items():
        if str(inp) == upstream_mat:
            continue  # would be free (self-supplied)
        unit = settler_input_avg_paid_cents(world, party, inp)
        if unit is None:
            unit = _market_unit_price(world, inp)
        other_input_cents += int(unit) * int(in_qty)
    labor_cents = int(getattr(rec, "labor_cents", 0))
    vertical_cost_per_out = (other_input_cents + labor_cents + rec_out_qty - 1) // rec_out_qty
    vertical_margin = max(0, downstream_price - vertical_cost_per_out)

    # ── decision gate.
    trigger = current_margin * VERTICAL_TRIGGER_RATIO_BPS // 10_000
    if vertical_margin <= max(1, trigger):
        return False
    spec = BUILDINGS.get(downstream_b) or {}
    turnkey = int(spec.get("turnkey_total_cents", 0))
    if turnkey <= 0:
        return False
    cash = int(world.ledger.balance(party_cash_account(party)))
    if cash * 10_000 < turnkey * VERTICAL_CASH_BUFFER_BPS:
        return False

    # ── attempt the build. We piggyback on the standard turnkey path: buy any
    # missing self_materials, then build_on_plot. ``_settler_acquire_turnkey_materials``
    # is private to the settler module — recreate it here to avoid a circular import.
    mats = spec.get("self_materials") or {}
    for mid_s, qty in mats.items():
        mid = MaterialId(mid_s)
        need = int(qty) - int(world.inventory.qty(party, mid))
        if need <= 0:
            continue
        r = market_buy(world, party, mid, need)
        if r.get("ok"):
            record_settler_buy(
                world,
                party,
                mid,
                int(r.get("filled", 0)),
                int(r.get("spent_cents", 0)),
            )
        if not r.get("ok") or int(r.get("filled", 0)) < need:
            return False  # insufficient market depth; try again next week
    built = build_on_plot(world, party, src_plot, downstream_b, build_mode="turnkey")
    if not built.get("ok"):
        return False
    log_event(
        world,
        "settler_vertical_upgrade",
        f"{party} initiated vertical upgrade {upstream_b}→{downstream_b} on {src_plot}",
        party=str(party),
        plot_id=str(src_plot),
        upstream_building=upstream_b,
        downstream_building=downstream_b,
        current_margin_cents=int(current_margin),
        vertical_margin_cents=int(vertical_margin),
    )
    return True


def _maybe_buffer_buy(world: World, party: PartyId) -> None:
    """Phase B.4 — when an input price rose ≥ 20% in 7 days, prebuy 3 days' worth.

    Only triggers for materials the settler is *already* buying from the market
    (so we have price history) **and** consumes via an active workshop. We
    estimate forward consumption from the recipe currently running (if any)
    or, as a default, from the recipe inputs of the upstream-paths above.
    """
    root = world.scenario_state.get("settler_cost_basis") or {}
    blob = root.get(str(party)) or {}
    avg_map = blob.get("input_avg_paid") or {}
    if not avg_map:
        return
    for mid_s in list(avg_map.keys()):
        change_bps = settler_input_price_change_bps_7d(world, party, MaterialId(mid_s))
        if change_bps is None:
            continue
        if int(change_bps) < SETTLER_BUFFER_BUY_PRICE_RISE_BPS:
            continue
        # Conservative forward-consumption estimate: 6 units per game-day (covers a
        # single workshop running once per ~4 hours).
        per_day = 6
        for run in world.active_production:
            if str(run.party) != str(party):
                continue
            rec = RECIPES.get(run.recipe_id)
            if rec is None:
                continue
            qty = int(rec.inputs.get(MaterialId(mid_s), 0))
            if qty <= 0:
                continue
            per_day = max(per_day, qty * 6)
            break
        target_qty = per_day * SETTLER_BUFFER_BUY_DAYS_FORWARD
        have = int(world.inventory.qty(party, MaterialId(mid_s)))
        deficit = target_qty - have
        if deficit <= 0:
            continue
        r = market_buy(world, party, MaterialId(mid_s), deficit)
        if r.get("ok"):
            record_settler_buy(
                world,
                party,
                MaterialId(mid_s),
                int(r.get("filled", 0)),
                int(r.get("spent_cents", 0)),
            )
            if int(r.get("filled", 0)) > 0:
                log_event(
                    world,
                    "settler_buffer_buy",
                    f"{party} buffered {r['filled']}×{mid_s} (price up {change_bps}bps in 7d)",
                    party=str(party),
                    material=str(mid_s),
                    filled=int(r.get("filled", 0)),
                    spent_cents=int(r.get("spent_cents", 0)),
                    price_change_bps_7d=int(change_bps),
                )


def tick_settler_margin_review(world: World) -> None:
    """Once per game-week, evaluate every settler's vertical-integration triggers
    and run buffer-buy logic for materials whose price is rising fast.

    Called from ``tick_genesis_agents`` (after the per-tick settler business
    pipeline, before the population-demand sweep). A no-op on non-week-boundary
    ticks so it doesn't blow up runtime cost.
    """
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0:
        return
    if int(world.tick) % _REVIEW_INTERVAL_TICKS != 0:
        return
    settlers = sorted(
        (p for p in world.parties if str(p).startswith("settler_")), key=str
    )
    for party in settlers:
        # One upgrade per settler per week — the first path whose math fires wins.
        for path in _UPGRADE_PATHS:
            if _maybe_trigger_upgrade(world, party, path):
                break
        _maybe_buffer_buy(world, party)
