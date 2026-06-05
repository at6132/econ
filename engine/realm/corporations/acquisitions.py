"""Hostile and opportunistic acquisitions — buyouts of distressed settlers."""

from __future__ import annotations

from typing import Any

from realm.actions._shared import ActionResult
from realm.agents.settler_identity import (
    _party_hash,
    get_settler_personality,
    get_settler_world_model,
)
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.corporations.company import company_for_party
from realm.economy.markets import cancel_all_party_resting_orders
from realm.events.event_log import log_event
from realm.infrastructure.plot_logistics import remove_plot_output
from realm.world import World

_TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY
GREED_THRESHOLD = 0.6
DISTRESSED_CASH_CENTS = 80_000
BUYOUT_PREMIUM_BPS = 12_000  # 1.2× liquidation value paid to target
ACQUIRER_MIN_LIQUIDATION_RATIO_BPS = 13_000  # acquirer cash > 1.3× liquidation


def _acquisitions_store(world: World) -> dict[str, Any]:
    raw = world.scenario_state.setdefault("corporations", {})
    if not isinstance(raw, dict):
        world.scenario_state["corporations"] = {}
        raw = world.scenario_state["corporations"]
    queue = raw.setdefault("buyout_queue", [])
    if not isinstance(queue, list):
        raw["buyout_queue"] = []
        queue = raw["buyout_queue"]
    return raw


def _display_name(world: World, party: PartyId) -> str:
    return world.party_display_names.get(str(party), str(party))


def liquidation_value_cents(world: World, target: PartyId) -> int:
    from realm.world import claim_cost_cents_for_plot

    total = 0
    for plot in world.plots.values():
        if plot.owner != target:
            continue
        total += int(claim_cost_cents_for_plot(world, plot.plot_id))
    ps = str(target)
    for pb in world.placed_buildings.values():
        if pb.built_by == ps:
            total += int(pb.book_value_cents)
    for row in world.plot_buildings:
        if str(row.get("party", "")) != ps:
            continue
        iid = str(row.get("instance_id", ""))
        if iid and iid in world.placed_buildings:
            continue
        total += int(row.get("book_value_cents", 0) or row.get("original_cost_cents", 0))
    return total


def _transfer_party_assets(world: World, *, from_party: PartyId, to_party: PartyId) -> None:
    for mat, qty in list(world.inventory.stock_for_party(from_party).items()):
        if qty <= 0:
            continue
        rm = world.inventory.remove(from_party, mat, qty, quality="any")
        if isinstance(rm, MatterErr):
            continue
        ad = world.inventory.add(to_party, mat, qty)
        if isinstance(ad, MatterErr):
            world.inventory.add(from_party, mat, qty)

    for pid_str, bucket in list(world.plot_output_stock.items()):
        plot = world.plots.get(PlotId(pid_str))
        if plot is None or plot.owner != from_party:
            continue
        for ms, q in list(bucket.items()):
            qn = int(q)
            if qn <= 0:
                continue
            rm = remove_plot_output(world, from_party, PlotId(pid_str), MaterialId(ms), qn)
            if isinstance(rm, MatterErr):
                continue
            ad = world.inventory.add(to_party, MaterialId(ms), qn)
            if isinstance(ad, MatterErr):
                world.inventory.add(from_party, MaterialId(ms), qn)


def _reassign_party_assets(world: World, *, from_party: PartyId, to_party: PartyId) -> None:
    ps_from = str(from_party)
    ps_to = str(to_party)
    for plot in world.plots.values():
        if plot.owner == from_party:
            plot.owner = to_party
    for row in world.plot_buildings:
        if str(row.get("party", "")) == ps_from:
            row["party"] = ps_to
    for pb in world.placed_buildings.values():
        if pb.built_by == ps_from:
            pb.built_by = ps_to
    for job in world.active_production:
        if job.party == from_party:
            job.party = to_party
    for ship in world.in_transit:
        if ship.party == from_party:
            ship.party = to_party
    for hire in world.stub_hires:
        if hire.get("employer") == ps_from:
            hire["employer"] = ps_to
        if hire.get("employee") == ps_from:
            hire["employee"] = ps_to


def _retire_party_after_buyout(world: World, party: PartyId) -> None:
    """Retire without liquidating inventory or releasing plots (already transferred)."""
    cash = party_cash_account(party)
    bal = world.ledger.balance(cash)
    if bal > 0:
        tr = world.ledger.transfer(
            debit=cash,
            credit=system_reserve_account(),
            amount_cents=bal,
        )
        if isinstance(tr, MoneyErr):
            pass
    world.parties.discard(party)
    world.reputation.pop(str(party), None)
    world.party_display_names.pop(str(party), None)
    world.llm_agents.pop(str(party), None)
    pref = f"{party}|"
    world.market_seller_registered = {k for k in world.market_seller_registered if not k.startswith(pref)}
    st = world.scenario_state.setdefault("genesis", {})
    if isinstance(st, dict):
        bt = st.setdefault("broke_ticks", {})
        if isinstance(bt, dict):
            bt.pop(str(party), None)
    ident = world.scenario_state.get("settler_identities", {})
    if isinstance(ident, dict):
        ident.pop(str(party), None)
    world.contracts = [
        c
        for c in world.contracts
        if PartyId(str(c.get("supplier", ""))) != party and PartyId(str(c.get("buyer", ""))) != party
    ]
    log_event(
        world,
        "genesis_party_retire",
        f"{party} left the economy (acquisition)",
        party=str(party),
        reason="acquisition",
    )


def execute_buyout(world: World, acquirer: PartyId, target: PartyId) -> ActionResult:
    if acquirer == target:
        return {"ok": False, "reason": "cannot acquire self"}
    if acquirer not in world.parties or target not in world.parties:
        return {"ok": False, "reason": "party missing"}
    if not str(acquirer).startswith("settler_") or not str(target).startswith("settler_"):
        return {"ok": False, "reason": "buyouts are settler-only"}

    liq = liquidation_value_cents(world, target)
    if liq <= 0:
        return {"ok": False, "reason": "no assets to acquire"}
    price = int(liq * BUYOUT_PREMIUM_BPS // 10_000)
    acquirer_cash = world.ledger.balance(party_cash_account(acquirer))
    if acquirer_cash < price:
        return {"ok": False, "reason": "insufficient acquirer cash"}

    cancel_all_party_resting_orders(world, target)
    _transfer_party_assets(world, from_party=target, to_party=acquirer)
    _reassign_party_assets(world, from_party=target, to_party=acquirer)

    tr = world.ledger.transfer(
        debit=party_cash_account(acquirer),
        credit=party_cash_account(target),
        amount_cents=price,
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}

    company = company_for_party(world, acquirer)
    if company is not None:
        new_plots = sorted(
            set(company.managed_plots)
            | {str(p.plot_id) for p in world.plots.values() if p.owner == acquirer}
        )
        from realm.corporations.company import Company, store_company

        updated = Company(
            company_id=company.company_id,
            name=company.name,
            founded_tick=company.founded_tick,
            founding_party=company.founding_party,
            share_registry=dict(company.share_registry),
            total_shares=company.total_shares,
            managed_plots=new_plots,
            cash_account=company.cash_account,
            hq_plot_id=company.hq_plot_id,
            era_unlocked=company.era_unlocked,
        )
        store_company(world, updated)

    _retire_party_after_buyout(world, target)

    log_event(
        world,
        "world_feed",
        f"{_display_name(world, acquirer)} acquired {_display_name(world, target)}'s operations for ${liq / 100:.0f}",
        feed_source="acquisition",
        acquirer=str(acquirer),
        target=str(target),
        liquidation_value_cents=liq,
    )
    from realm.agents.llm_voice import generate_settler_voice

    generate_settler_voice(
        world,
        acquirer,
        "acquisition_complete",
        {
            "party_display_name": _display_name(world, acquirer),
            "target_display_name": _display_name(world, target),
        },
    )
    return {"ok": True, "liquidation_value_cents": liq, "price_cents": price}


def evaluate_acquisition_targets(world: World, acquirer_party: PartyId) -> list[PartyId]:
    """Return target party ids queued for buyout this evaluation."""
    if acquirer_party not in world.parties:
        return []
    personality = get_settler_personality(world, acquirer_party)
    if personality is None or personality.greed_index <= GREED_THRESHOLD:
        return []

    acquirer_cash = world.ledger.balance(party_cash_account(acquirer_party))
    world_model = get_settler_world_model(world, acquirer_party)
    queued: list[PartyId] = []

    for other_s, intel in world_model.known_settlers.items():
        if other_s == str(acquirer_party):
            continue
        if not other_s.startswith("settler_"):
            continue
        target = PartyId(other_s)
        if target not in world.parties:
            continue
        tier = str(intel.get("estimated_cash_tier", ""))
        if tier != "low":
            continue
        direct_cash = world.ledger.balance(party_cash_account(target))
        if direct_cash >= DISTRESSED_CASH_CENTS:
            continue
        liq = liquidation_value_cents(world, target)
        if liq <= 0:
            continue
        threshold = int(liq * ACQUIRER_MIN_LIQUIDATION_RATIO_BPS // 10_000)
        if acquirer_cash <= threshold:
            continue
        queued.append(target)

    store = _acquisitions_store(world)
    q: list[dict[str, Any]] = store.get("buyout_queue", [])
    for target in queued:
        key = f"{acquirer_party}|{target}"
        if any(isinstance(r, dict) and r.get("key") == key for r in q):
            continue
        q.append({"key": key, "acquirer": str(acquirer_party), "target": str(target), "tick": int(world.tick)})
    store["buyout_queue"] = q
    return queued


def tick_acquisition_offers(world: World) -> None:
    """Weekly per-settler acquisition scan and queued buyout execution."""
    if world.scenario_id != "genesis":
        return
    slot = int(world.tick) % _TICKS_PER_GAME_WEEK
    for party in world.parties:
        ps = str(party)
        if not ps.startswith("settler_"):
            continue
        if _party_hash(party) % _TICKS_PER_GAME_WEEK != slot:
            continue
        evaluate_acquisition_targets(world, party)

    store = _acquisitions_store(world)
    queue = list(store.get("buyout_queue", []))
    remaining: list[dict[str, Any]] = []
    for row in queue:
        if not isinstance(row, dict):
            continue
        acquirer = PartyId(str(row.get("acquirer", "")))
        target = PartyId(str(row.get("target", "")))
        if acquirer not in world.parties or target not in world.parties:
            continue
        result = execute_buyout(world, acquirer, target)
        if not result["ok"]:
            remaining.append(row)
    store["buyout_queue"] = remaining
