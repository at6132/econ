"""Dynamic land market — scarce plots, location premiums, island dominance."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from typing import Any

from realm.actions._shared import ActionResult
from realm.agents.settler_identity import get_settler_personality
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import MoneyErr, party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.corporations.company import company_cash_account, company_for_party
from realm.events.event_log import log_event
from realm.production import plot_has_active_production
from realm.world import Plot, World
from realm.world.geo import manhattan

__all__ = [
    "PlotListing",
    "DOMINANCE_SHARE_THRESHOLD",
    "DOMINANCE_TOLL_BPS",
    "HIGH_SOCIAL_RADIUS",
    "MIN_BUYER_CASH_CENTS",
    "PURCHASE_CASH_BUFFER_CENTS",
    "PURCHASE_VALUE_PREMIUM",
    "list_plot_for_sale",
    "tick_plot_purchases",
    "tick_location_premium",
    "tick_island_dominance",
    "tick_plot_abandonment",
    "island_dominance_toll_cents",
    "apply_island_dominance_toll",
    "dominant_entity_cash_account",
    "location_score_for_plot",
    "listing_valuation_cents",
]

_TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY
_TICKS_PER_GAME_MONTH = 30 * TICKS_PER_GAME_DAY

MIN_BUYER_CASH_CENTS = 200_000
PURCHASE_CASH_BUFFER_CENTS = 50_000
HIGH_SOCIAL_RADIUS = 4
LISTING_SCAN_RADIUS_TILES = 5
PURCHASE_VALUE_PREMIUM = 1.1
DOMINANCE_SHARE_THRESHOLD = 0.60
DOMINANCE_TOLL_BPS = 500  # 5%
ABANDONMENT_MIN_IDLE_DAYS = 30
ABANDONMENT_MAX_OWNER_CASH_CENTS = 50_000
ABANDONMENT_LIST_FRACTION = 0.5

_GRADE_SUFFIX = "_grade"


@dataclass(frozen=True, slots=True)
class PlotListing:
    plot_id: PlotId
    seller_party: PartyId
    ask_cents: int
    listed_at_tick: int


def _listings_store(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault("plot_listings", {})
    if not isinstance(raw, dict):
        world.scenario_state["plot_listings"] = {}
        raw = world.scenario_state["plot_listings"]
    return raw


def listing_to_dict(row: PlotListing) -> dict[str, Any]:
    return {
        "plot_id": str(row.plot_id),
        "seller_party": str(row.seller_party),
        "ask_cents": int(row.ask_cents),
        "listed_at_tick": int(row.listed_at_tick),
    }


def listing_from_dict(d: dict[str, Any]) -> PlotListing:
    return PlotListing(
        plot_id=PlotId(str(d["plot_id"])),
        seller_party=PartyId(str(d["seller_party"])),
        ask_cents=int(d["ask_cents"]),
        listed_at_tick=int(d["listed_at_tick"]),
    )


def _plot_has_buildings(world: World, plot_id: PlotId) -> bool:
    key = str(plot_id)
    if world.plot_placed_buildings.get(key):
        return True
    return any(str(b.get("plot_id")) == key for b in world.plot_buildings)


def _max_subsurface_grade(plot: Plot) -> float:
    best = 0.0
    for fld in dataclass_fields(plot.subsurface):
        if not fld.name.endswith(_GRADE_SUFFIX):
            continue
        best = max(best, float(getattr(plot.subsurface, fld.name, 0.0)))
    return best


def _road_endpoint_plot_ids(world: World) -> set[str]:
    from realm.infrastructure.road_connectivity import get_road_endpoint_plots

    return set(get_road_endpoint_plots(world))


def _min_manhattan_to_plot_set(world: World, plot: Plot, targets: set[str]) -> float:
    if not targets:
        return 9999.0
    best = 9999.0
    for pid_s in targets:
        d = float(manhattan(world, plot.plot_id, PlotId(pid_s)))
        best = min(best, d)
    return best


def _dock_plot_ids(world: World) -> set[str]:
    out: set[str] = set()
    for b in world.plot_buildings:
        if str(b.get("building_id")) != "dock":
            continue
        if int(b.get("completes_at_tick", 0)) > int(world.tick):
            continue
        out.add(str(b.get("plot_id")))
    return out


def proximity_to_road(world: World, plot: Plot) -> float:
    from realm.infrastructure.road_connectivity import is_road_accessible

    if is_road_accessible(world, plot.plot_id):
        return 1.0
    endpoints = _road_endpoint_plot_ids(world)
    if str(plot.plot_id) in endpoints:
        return 1.0
    dist = _min_manhattan_to_plot_set(world, plot, endpoints)
    return max(0.0, 1.0 - dist / 10.0)


def proximity_to_town(world: World, plot: Plot) -> float:
    from realm.world.plot_geom_cache import cached_min_town_distance

    dist = cached_min_town_distance(world, plot)
    return max(0.0, 1.0 - dist / 20.0)


def dock_proximity(world: World, plot: Plot) -> float:
    from realm.production.recipe_sites import plot_is_coastal
    from realm.world.plot_geom_cache import cached_waterfront_build_cells

    if _dock_plot_ids(world) & {str(plot.plot_id)}:
        return 1.0
    if plot_is_coastal(world, plot) or cached_waterfront_build_cells(world, plot):
        return 0.85
    docks = _dock_plot_ids(world)
    if not docks:
        return 0.0
    dist = _min_manhattan_to_plot_set(world, plot, docks)
    return max(0.0, 1.0 - dist / 15.0)


def island_centrality(world: World, plot: Plot) -> float:
    from realm.world.islands import plot_island_id

    isl = plot_island_id(world, plot.plot_id)
    if isl is None:
        return 0.5
    islands_map = world.scenario_state.get("plot_islands") or {}
    coords: list[tuple[int, int]] = []
    for pid_s, pid_isl in islands_map.items():
        if int(pid_isl) != int(isl):
            continue
        p = world.plots.get(PlotId(pid_s))
        if p is None or p.terrain.value.startswith("water"):
            continue
        coords.append((int(p.x), int(p.y)))
    if len(coords) <= 1:
        return 1.0
    cx = sum(x for x, _ in coords) / len(coords)
    cy = sum(y for _, y in coords) / len(coords)
    dist = abs(plot.x - cx) + abs(plot.y - cy)
    max_dist = max(abs(x - cx) + abs(y - cy) for x, y in coords)
    if max_dist <= 0:
        return 1.0
    return max(0.0, 1.0 - float(dist / max_dist))


def location_score_for_plot(world: World, plot_id: PlotId) -> float:
    plot = world.plots.get(plot_id)
    if plot is None:
        return 0.0
    road = proximity_to_road(world, plot)
    town = proximity_to_town(world, plot)
    dock = dock_proximity(world, plot)
    center = island_centrality(world, plot)
    return road * 0.4 + town * 0.3 + dock * 0.2 + center * 0.1


def tick_location_premium(world: World) -> None:
    """Recompute per-plot location scores (bootstrap + road/town builds)."""
    scores: dict[str, float] = {}
    for pid in world.plots:
        plot = world.plots[pid]
        if plot.terrain.value.startswith("water"):
            continue
        scores[str(pid)] = round(location_score_for_plot(world, pid), 4)
    world.scenario_state["plot_location_scores"] = scores


def listing_valuation_cents(world: World, plot_id: PlotId) -> int:
    plot = world.plots.get(plot_id)
    if plot is None:
        return 0
    subsurface = _max_subsurface_grade(plot)
    road = proximity_to_road(world, plot)
    town = proximity_to_town(world, plot)
    return int(subsurface * 80_000 + road * 20_000 + town * 15_000)


def list_plot_for_sale(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    ask_cents: int,
) -> ActionResult:
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "no such plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    if plot_has_active_production(world, plot_id):
        return {"ok": False, "reason": "active production on plot"}
    if ask_cents <= 0:
        return {"ok": False, "reason": "ask must be positive"}
    store = _listings_store(world)
    listing = PlotListing(
        plot_id=plot_id,
        seller_party=party,
        ask_cents=int(ask_cents),
        listed_at_tick=int(world.tick),
    )
    store[str(plot_id)] = listing_to_dict(listing)
    log_event(
        world,
        "plot_listed",
        f"{party} listed {plot_id} for ${ask_cents / 100:,.2f}",
        party=str(party),
        plot_id=str(plot_id),
        ask_cents=int(ask_cents),
    )
    return {"ok": True}


def _settler_owned_plot_ids(world: World, party: PartyId) -> list[PlotId]:
    return sorted(
        (p.plot_id for p in world.plots.values() if p.owner == party),
        key=str,
    )


def _within_scan_radius(world: World, buyer: PartyId, plot_id: PlotId) -> bool:
    for owned in _settler_owned_plot_ids(world, buyer):
        if manhattan(world, owned, plot_id) <= LISTING_SCAN_RADIUS_TILES:
            return True
    return False


def _execute_plot_sale(
    world: World,
    listing: PlotListing,
    buyer: PartyId,
) -> bool:
    plot = world.plots.get(listing.plot_id)
    if plot is None or plot.owner != listing.seller_party:
        _listings_store(world).pop(str(listing.plot_id), None)
        return False
    ask = int(listing.ask_cents)
    buyer_acct = party_cash_account(buyer)
    seller_acct = party_cash_account(listing.seller_party)
    tr = world.ledger.transfer(debit=buyer_acct, credit=seller_acct, amount_cents=ask)
    if isinstance(tr, MoneyErr):
        return False
    plot.owner = buyer
    _listings_store(world).pop(str(listing.plot_id), None)
    from realm.world.plot_geom_cache import invalidate_plot_geom_caches

    invalidate_plot_geom_caches()
    log_event(
        world,
        "plot_sold",
        f"{listing.plot_id} sold from {listing.seller_party} to {buyer} for ${ask / 100:,.2f}",
        party=str(buyer),
        seller=str(listing.seller_party),
        plot_id=str(listing.plot_id),
        price_cents=ask,
    )
    log_event(
        world,
        "world_feed",
        f"Land deal: {buyer} acquired plot {listing.plot_id} for ${ask / 100:,.0f}.",
        feed_source="plot_sold",
        buyer=str(buyer),
        seller=str(listing.seller_party),
        plot_id=str(listing.plot_id),
        price_cents=ask,
    )
    return True


def tick_plot_purchases(world: World) -> None:
    """Weekly: cash-rich settlers buy nearby listings that look underpriced."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_WEEK != 0:
        return
    store = _listings_store(world)
    if not store:
        return
    listings = [
        listing_from_dict(row)
        for row in store.values()
        if isinstance(row, dict)
    ]
    listings.sort(key=lambda x: (x.listed_at_tick, str(x.plot_id)))
    settlers = sorted(
        (p for p in world.parties if str(p).startswith("settler_")),
        key=str,
    )
    for buyer in settlers:
        cash = int(world.ledger.balance(party_cash_account(buyer)))
        if cash <= MIN_BUYER_CASH_CENTS:
            continue
        personality = get_settler_personality(world, buyer)
        if personality is None or int(personality.social_radius) < HIGH_SOCIAL_RADIUS:
            continue
        for listing in list(listings):
            if str(listing.plot_id) not in store:
                continue
            if listing.seller_party == buyer:
                continue
            if not _within_scan_radius(world, buyer, listing.plot_id):
                continue
            value = listing_valuation_cents(world, listing.plot_id)
            ask = int(listing.ask_cents)
            if value <= int(ask * PURCHASE_VALUE_PREMIUM):
                continue
            if cash - ask < PURCHASE_CASH_BUFFER_CENTS:
                continue
            if _execute_plot_sale(world, listing, buyer):
                cash -= ask
                listings = [
                    listing_from_dict(row)
                    for row in store.values()
                    if isinstance(row, dict)
                ]


def _ownership_entity_key(world: World, party: PartyId) -> str:
    company = company_for_party(world, party)
    if company is not None:
        return f"company:{company.company_id}"
    return f"party:{party}"


def _plot_is_productive(world: World, plot_id: PlotId) -> bool:
    key = str(plot_id)
    for iid in world.plot_placed_buildings.get(key, []):
        pb = world.placed_buildings.get(iid)
        if pb is not None and str(getattr(pb, "blueprint_id", "")) != "residence":
            return True
    for b in world.plot_buildings:
        if str(b.get("plot_id")) != key:
            continue
        if int(b.get("completes_at_tick", 0)) > int(world.tick):
            continue
        if str(b.get("building_id")) != "residence":
            return True
    return False


def _dominant_cash_account(world: World, entity_key: str):
    if entity_key.startswith("company:"):
        return company_cash_account(entity_key.split(":", 1)[1])
    return party_cash_account(PartyId(entity_key.split(":", 1)[1]))


def _dominant_label(world: World, entity_key: str) -> str:
    if entity_key.startswith("company:"):
        cid = entity_key.split(":", 1)[1]
        from realm.corporations.company import get_company

        co = get_company(world, cid)
        return co.name if co is not None else cid
    return entity_key.split(":", 1)[1]


def tick_island_dominance(world: World) -> None:
    """Weekly: flag islands where one entity controls >60% of productive plots."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_WEEK != 0:
        return
    islands_map = world.scenario_state.get("plot_islands") or {}
    if not islands_map:
        return
    dominance: dict[str, dict[str, Any]] = {}
    prev = world.scenario_state.get("island_dominance") or {}
    for isl in sorted({int(v) for v in islands_map.values()}):
        counts: dict[str, int] = {}
        total = 0
        for pid_s, pid_isl in islands_map.items():
            if int(pid_isl) != int(isl):
                continue
            plot = world.plots.get(PlotId(pid_s))
            if plot is None or plot.owner is None:
                continue
            if not _plot_is_productive(world, PlotId(pid_s)):
                continue
            key = _ownership_entity_key(world, plot.owner)
            counts[key] = counts.get(key, 0) + 1
            total += 1
        if total <= 0:
            continue
        leader_key = max(counts, key=lambda k: (counts[k], k))
        share = counts[leader_key] / total
        if share <= DOMINANCE_SHARE_THRESHOLD:
            continue
        dominance[str(isl)] = {
            "entity_key": leader_key,
            "share": round(share, 4),
            "productive_plots": int(counts[leader_key]),
            "total_productive": int(total),
            "declared_tick": int(world.tick),
        }
        prev_row = prev.get(str(isl)) if isinstance(prev, dict) else None
        prev_entity = (
            str(prev_row.get("entity_key"))
            if isinstance(prev_row, dict)
            else None
        )
        if prev_entity != leader_key:
            label = _dominant_label(world, leader_key)
            log_event(
                world,
                "world_feed",
                f"Island {isl}: {label} now controls {int(share * 100)}% of productive land "
                f"({counts[leader_key]}/{total} plots). Inter-island exports face a 5% levy.",
                feed_source="island_dominance",
                island_id=int(isl),
                entity_key=leader_key,
                share=round(share, 4),
            )
    world.scenario_state["island_dominance"] = dominance


def tick_plot_abandonment(world: World) -> None:
    """Monthly: broke idle landowners are forced to list at half claim cost."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_MONTH != 0:
        return
    from realm.world.world import claim_cost_cents_for_plot

    idle_ticks = ABANDONMENT_MIN_IDLE_DAYS * TICKS_PER_GAME_DAY
    store = _listings_store(world)
    for plot in sorted(world.plots.values(), key=lambda p: str(p.plot_id)):
        owner = plot.owner
        if owner is None or not str(owner).startswith("settler_"):
            continue
        pid = plot.plot_id
        if str(pid) in store:
            continue
        if plot_has_active_production(world, pid) or _plot_has_buildings(world, pid):
            continue
        if world.scenario_id == "genesis":
            if any(
                pl.owner == owner and _plot_has_buildings(world, pl.plot_id)
                for pl in world.plots.values()
            ):
                continue
        cash = int(world.ledger.balance(party_cash_account(owner)))
        if cash >= ABANDONMENT_MAX_OWNER_CASH_CENTS:
            continue
        gst = world.scenario_state.get("genesis") or {}
        broke_ticks = gst.get("broke_ticks") or {}
        first_broke = int(broke_ticks.get(str(owner), int(world.tick)))
        if int(world.tick) - first_broke < idle_ticks:
            continue
        ask = max(
            1,
            int(claim_cost_cents_for_plot(world, pid) * ABANDONMENT_LIST_FRACTION),
        )
        listing = PlotListing(
            plot_id=pid,
            seller_party=owner,
            ask_cents=ask,
            listed_at_tick=int(world.tick),
        )
        store[str(pid)] = listing_to_dict(listing)
        log_event(
            world,
            "plot_listed",
            f"{owner} forced to list idle {pid} at ${ask / 100:,.2f} (economic pressure)",
            party=str(owner),
            plot_id=str(pid),
            ask_cents=ask,
            forced=True,
        )


def dominant_entity_cash_account(world: World, entity_key: str):
    return _dominant_cash_account(world, entity_key)


def island_dominance_toll_cents(
    world: World, from_plot_id: PlotId, goods_value_cents: int
) -> tuple[str | None, int]:
    """5% levy on inter-island exports from a dominant island (if any)."""
    from realm.world.islands import plot_island_id

    if goods_value_cents <= 0:
        return None, 0
    isl = plot_island_id(world, from_plot_id)
    if isl is None:
        return None, 0
    row = (world.scenario_state.get("island_dominance") or {}).get(str(isl))
    if not isinstance(row, dict):
        return None, 0
    entity_key = str(row.get("entity_key", ""))
    if not entity_key:
        return None, 0
    toll = max(1, int(goods_value_cents) * DOMINANCE_TOLL_BPS // 10_000)
    return entity_key, toll


def apply_island_dominance_toll(
    world: World,
    shipper: PartyId,
    from_plot_id: PlotId,
    goods_value_cents: int,
) -> tuple[int, str | None]:
    """Debit shipper and credit the dominant entity. Returns (toll_paid, entity_key)."""
    entity_key, toll = island_dominance_toll_cents(world, from_plot_id, goods_value_cents)
    if entity_key is None or toll <= 0:
        return 0, None
    credit_acct = _dominant_cash_account(world, entity_key)
    shipper_acct = party_cash_account(shipper)
    world.ledger.ensure_account(credit_acct)
    tr = world.ledger.transfer(debit=shipper_acct, credit=credit_acct, amount_cents=toll)
    if isinstance(tr, MoneyErr):
        return 0, None
    isl_raw = (world.scenario_state.get("plot_islands") or {}).get(str(from_plot_id))
    log_event(
        world,
        "island_dominance_toll",
        f"{shipper} paid ${toll / 100:,.2f} dominance levy on export from island {isl_raw}",
        party=str(shipper),
        entity_key=entity_key,
        island_id=int(isl_raw) if isl_raw is not None else None,
        toll_cents=toll,
        goods_value_cents=int(goods_value_cents),
    )
    return toll, entity_key
