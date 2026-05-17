"""Plot valuation, NPC demand, and scenario_state sale listings."""

from __future__ import annotations

from realm.core.ids import PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.events.event_log import log_event
from realm.world.world import World

BASE_PLOT_VALUE_CENTS: int = 50_000

MINERAL_VALUE_WEIGHTS: dict[str, int] = {
    "iron_ore_grade": 80_000,
    "coal_grade": 60_000,
    "copper_ore_grade": 100_000,
    "platinum_ore_grade": 500_000,
    "phosphate_grade": 40_000,
    "clay_grade": 20_000,
    "au_grade": 800_000,
    "nd_grade": 600_000,
    "u_grade": 400_000,
}


def compute_plot_value(world: World, plot_id: PlotId) -> int:
    plot = world.plots.get(plot_id)
    if plot is None:
        return 0
    terr = plot.terrain.value
    if terr.startswith("water"):
        return 0

    value = BASE_PLOT_VALUE_CENTS
    min_town_dist = _min_town_distance(world, plot)
    if min_town_dist < 5:
        value = int(value * 3.5)
    elif min_town_dist < 10:
        value = int(value * 2.0)
    elif min_town_dist < 20:
        value = int(value * 1.4)

    from realm.production.recipe_sites import plot_is_coastal

    if plot_is_coastal(world, plot):
        value = int(value * 1.5)

    sub = plot.subsurface
    for grade_attr, weight in MINERAL_VALUE_WEIGHTS.items():
        grade = float(getattr(sub, grade_attr, 0.0))
        value += int(grade * weight)

    demand = float(
        (world.scenario_state.get("plot_demand_scores") or {}).get(str(plot_id), 0.0)
    )
    value = int(value * (1.0 + demand * 0.5))
    return value


def _min_town_distance(world: World, plot: object) -> float:
    min_d = 9999.0
    px = int(getattr(plot, "x", 0))
    py = int(getattr(plot, "y", 0))
    for town in world.towns.values():
        cx = int(getattr(town, "center_x", 0))
        cy = int(getattr(town, "center_y", 0))
        d = abs(px - cx) + abs(py - cy)
        min_d = min(min_d, float(d))
    return min_d


def tick_npc_plot_demand(world: World) -> None:
    if world.tick % 10_080 != 0:
        return

    demand_scores: dict[str, float] = {}
    npc_bids: dict[str, list[dict[str, object]]] = {}

    for party in world.parties:
        if not str(party).startswith("settler_"):
            continue
        pref = _npc_plot_preference(world, party)
        if pref is None:
            continue
        best_plot, best_score = _find_best_unclaimed_plot(world, pref)
        if best_plot is None or best_score < 0.1:
            continue
        fair_value = compute_plot_value(world, best_plot)
        wtp = int(fair_value * float(pref["wtp_multiplier"]))
        pid_s = str(best_plot)
        demand_scores[pid_s] = demand_scores.get(pid_s, 0.0) + best_score
        npc_bids.setdefault(pid_s, []).append(
            {"party": str(party), "bid_cents": wtp}
        )

    world.scenario_state["plot_demand_scores"] = demand_scores
    world.scenario_state["plot_npc_bids"] = npc_bids


def _npc_plot_preference(world: World, party: PartyId) -> dict[str, object] | None:
    buildings: list[object] = []
    for pid_s, iids in world.plot_placed_buildings.items():
        plot = world.plots.get(PlotId(pid_s))
        if plot is None or plot.owner != party:
            continue
        for iid in iids:
            pb = world.placed_buildings.get(iid)
            if pb is not None:
                buildings.append(pb)

    if not buildings:
        return {"preferred_terrain": None, "preferred_mineral": None, "wtp_multiplier": 0.8}

    bp_ids = {getattr(b, "blueprint_id", "") for b in buildings}
    if "strip_mine" in bp_ids or "foundry" in bp_ids:
        return {
            "preferred_terrain": ["mountain", "hills"],
            "preferred_mineral": "iron_ore_grade",
            "wtp_multiplier": 1.2,
        }
    if "grain_row" in bp_ids or "gristmill" in bp_ids:
        return {
            "preferred_terrain": ["plains", "valley", "tropical"],
            "preferred_mineral": "phosphate_grade",
            "wtp_multiplier": 1.1,
        }
    if "dock" in bp_ids:
        return {
            "preferred_terrain": ["coastal"],
            "preferred_mineral": None,
            "wtp_multiplier": 1.3,
        }
    return {"preferred_terrain": None, "preferred_mineral": None, "wtp_multiplier": 0.9}


def _find_best_unclaimed_plot(
    world: World, pref: dict[str, object]
) -> tuple[PlotId | None, float]:
    best_id: PlotId | None = None
    best_score = 0.0
    preferred_terrains = pref.get("preferred_terrain") or []
    preferred_mineral = pref.get("preferred_mineral")
    for pid, plot in world.plots.items():
        if plot.owner is not None:
            continue
        if plot.terrain.value.startswith("water"):
            continue
        score = 0.0
        if preferred_terrains and plot.terrain.value in preferred_terrains:
            score += 1.0
        elif not preferred_terrains:
            score += 0.5
        if preferred_mineral:
            grade = float(getattr(plot.subsurface, str(preferred_mineral), 0.0))
            score += grade * 2.0
        if score > best_score:
            best_score = score
            best_id = pid
    return best_id, best_score


def list_plot_for_sale_market(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    ask_price_cents: int | None = None,
) -> dict[str, object]:
    plot = world.plots.get(plot_id)
    if plot is None or plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    lease = (world.scenario_state.get("plot_lease_rights") or {}).get(str(plot_id))
    if lease and int(lease.get("expires_tick", 0)) > world.tick:
        return {
            "ok": False,
            "reason": "plot is currently leased — wait for lease to expire or negotiate early termination",
        }
    fair_value = compute_plot_value(world, plot_id)
    ask = int(ask_price_cents if ask_price_cents is not None else fair_value)
    listings = world.scenario_state.setdefault("plots_for_sale", {})
    listings[str(plot_id)] = {
        "seller": str(party),
        "ask_price_cents": ask,
        "fair_value_cents": fair_value,
        "listed_at_tick": world.tick,
        "npc_bids": (world.scenario_state.get("plot_npc_bids") or {}).get(
            str(plot_id), []
        ),
    }
    log_event(
        world,
        "plot_listed_for_sale",
        f"{party} listed plot {plot_id} for sale at ${ask / 100:,.2f} (fair value: ${fair_value / 100:,.2f})",
        party=str(party),
        plot_id=str(plot_id),
        ask_cents=ask,
        fair_cents=fair_value,
    )
    npc_bids = listings[str(plot_id)].get("npc_bids") or []
    top_npc = max((int(b["bid_cents"]) for b in npc_bids), default=0)
    return {
        "ok": True,
        "ask_price_cents": ask,
        "fair_value_cents": fair_value,
        "npc_top_bid": top_npc,
    }


def buy_plot_market(world: World, buyer: PartyId, plot_id: PlotId) -> dict[str, object]:
    listing = (world.scenario_state.get("plots_for_sale") or {}).get(str(plot_id))
    if not listing:
        return {"ok": False, "reason": "plot not listed for sale"}
    ask = int(listing["ask_price_cents"])
    seller = PartyId(str(listing["seller"]))
    bc = party_cash_account(buyer)
    sc = party_cash_account(seller)
    if world.ledger.balance(bc) < ask:
        return {"ok": False, "reason": f"need ${ask / 100:,.2f} to buy this plot"}
    from realm.core.ledger import MoneyErr

    tr = world.ledger.transfer(debit=bc, credit=sc, amount_cents=ask)
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    plot = world.plots[plot_id]
    plot.owner = buyer
    del world.scenario_state["plots_for_sale"][str(plot_id)]
    log_event(
        world,
        "plot_sold",
        f"Plot {plot_id} sold from {seller} to {buyer} for ${ask / 100:,.2f}",
        party=str(buyer),
        seller=str(seller),
        plot_id=str(plot_id),
        price=ask,
    )
    return {"ok": True, "price_paid_cents": ask}


def plot_market_summary(world: World, plot_id: PlotId) -> dict[str, object]:
    fair = compute_plot_value(world, plot_id)
    listing = (world.scenario_state.get("plots_for_sale") or {}).get(str(plot_id))
    npc_bids = (world.scenario_state.get("plot_npc_bids") or {}).get(str(plot_id), [])
    top_npc = max((int(b["bid_cents"]) for b in npc_bids), default=0)
    return {
        "fair_value_cents": fair,
        "listed_for_sale": listing is not None,
        "ask_price_cents": int(listing["ask_price_cents"]) if listing else None,
        "top_npc_bid_cents": top_npc,
    }
