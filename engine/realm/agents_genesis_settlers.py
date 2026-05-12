"""Genesis settlers — claim, survey, build workshops, extract, buy power, sell competitively."""

from __future__ import annotations

from realm.actions import SURVEY_COST_CENTS, claim_plot, start_production_on_plot, survey_plot
from realm.buildings import BUILDINGS, build_on_plot
from realm.ids import MaterialId, PartyId, PlotId
from realm.ledger import party_cash_account
from realm.markets import (
    best_resting_ask_cents,
    cancel_party_asks_for_material,
    market_buy,
    place_sell_order,
    sell_into_bids,
)
from realm.production import plot_has_active_production
from realm.recipe_sites import recipe_allowed_on_terrain, subsurface_allows_recipe, terrain_allows_workshop
from realm.recipes import RECIPES
from realm.storage_caps import party_inventory_unit_total, party_storage_cap_units
from realm.terrain import Terrain
from realm.world import World

_TURNKEY_CENTS: dict[str, int] = {
    "strip_mine": int(BUILDINGS["strip_mine"]["turnkey_total_cents"]),
    "timber_yard": int(BUILDINGS["timber_yard"]["turnkey_total_cents"]),
    "grain_row": int(BUILDINGS["grain_row"]["turnkey_total_cents"]),
}

# When no asks exist yet, list near seed exchange anchors (genesis_exchange listings).
_FALLBACK_LIST_CENTS: dict[str, int] = {
    "coal": 58,
    "timber": 90,
    "grain": 120,
    "electricity": 50,
    "stone": 44,
    "clay": 36,
    "iron_ore": 72,
    "copper_ore": 70,
}


def _plots_manhattan_order(world: World) -> list[PlotId]:
    if not world.plots:
        return []
    xs = [p.x for p in world.plots.values()]
    ys = [p.y for p in world.plots.values()]
    cx = (min(xs) + max(xs)) // 2
    cy = (min(ys) + max(ys)) // 2
    ordered = sorted(
        world.plots.values(),
        key=lambda p: (abs(p.x - cx) + abs(p.y - cy), p.x, p.y),
    )
    return [p.plot_id for p in ordered]


def _first_owned_plot(world: World, party: PartyId) -> PlotId | None:
    for pid, pl in world.plots.items():
        if pl.owner == party:
            return pid
    return None


def _party_salience_jitter(party: PartyId) -> float:
    """Deterministic micro-jitter per party (no Python ``hash`` — not stable across processes)."""
    s = str(party)
    acc = 0
    for i, ch in enumerate(s[-10:]):
        acc += (i + 3) * ord(ch)
    return (acc % 7919) / 791_900.0


def _settler_workshop_counts(world: World) -> dict[str, int]:
    out: dict[str, int] = {}
    for b in world.plot_buildings:
        par = str(b.get("party", ""))
        if not par.startswith("settler_"):
            continue
        bid = str(b.get("building_id", ""))
        if bid:
            out[bid] = out.get(bid, 0) + 1
    return out


def _pick_settler_line(world: World, party: PartyId, plot) -> tuple[str, str] | None:
    """Weighted line choice — avoids global herd on ``mine_coal`` when subsurface is similar."""
    rng = world.rng(f"gen:settler_line2:{party}:{plot.plot_id}")
    counts = _settler_workshop_counts(world)
    n_strip = int(counts.get("strip_mine", 0))
    n_yard = int(counts.get("timber_yard", 0))
    n_row = int(counts.get("grain_row", 0))
    sal = _party_salience_jitter(party)

    # Terrain pivots: plains/forest can carry food & fiber when strip-mines crowd the ledger.
    if plot.terrain == Terrain.PLAINS and n_strip >= 9:
        p_gr = min(0.86, 0.26 + (n_strip - 9) * 0.03)
        if recipe_allowed_on_terrain(plot.terrain, "grow_grain") and rng.random() < p_gr:
            return ("grow_grain", "grain_row")
    if plot.terrain == Terrain.FOREST and n_strip >= 8:
        p_ch = min(0.86, 0.24 + (n_strip - 8) * 0.03)
        if recipe_allowed_on_terrain(plot.terrain, "chop_timber") and rng.random() < p_ch:
            return ("chop_timber", "timber_yard")

    # Late claimers see a crowded strip-mine field — push primary-sector diversity.
    if n_strip >= 8:
        p_divert = min(0.92, 0.14 + (n_strip - 8) * 0.026)
        early: list[tuple[str, str, float]] = []
        if recipe_allowed_on_terrain(plot.terrain, "chop_timber"):
            early.append(("chop_timber", "timber_yard", 0.62 + sal))
        if recipe_allowed_on_terrain(plot.terrain, "grow_grain"):
            early.append(("grow_grain", "grain_row", 0.58 + sal))
        if early and rng.random() < p_divert:
            wts = [x[2] for x in early]
            pick = rng.choices(early, weights=wts, k=1)[0]
            return (pick[0], pick[1])

    opts: list[tuple[str, str, float]] = []

    for rid, fld in (
        ("mine_coal", "coal_grade"),
        ("mine_iron_ore", "iron_ore_grade"),
        ("mine_copper_ore", "copper_ore_grade"),
        ("dig_clay", "clay_grade"),
    ):
        recipe = RECIPES.get(rid)
        if recipe is None:
            continue
        if not recipe_allowed_on_terrain(plot.terrain, rid):
            continue
        if not subsurface_allows_recipe(plot, recipe):
            continue
        g = float(getattr(plot.subsurface, fld, 0.0))
        w = g + sal
        if rid == "mine_coal":
            w -= min(1.05, n_strip * 0.024)
        if w > 0.035:
            opts.append((rid, "strip_mine", w))

    if recipe_allowed_on_terrain(plot.terrain, "mine_stone"):
        w = 0.34 + sal - min(0.28, n_strip * 0.005)
        opts.append(("mine_stone", "strip_mine", max(0.06, w)))

    if recipe_allowed_on_terrain(plot.terrain, "chop_timber"):
        w = 0.42 + sal + 0.08 * max(0.0, (n_yard + 6) - n_strip * 0.22)
        opts.append(("chop_timber", "timber_yard", w))

    if recipe_allowed_on_terrain(plot.terrain, "grow_grain"):
        w = 0.38 + sal + 0.07 * max(0.0, (n_row + 4) - n_strip * 0.2)
        opts.append(("grow_grain", "grain_row", w))

    strip_non_coal = [(a, b, c) for a, b, c in opts if b == "strip_mine" and a != "mine_coal"]
    if n_strip >= 10 and strip_non_coal:
        p_nc = min(0.88, 0.2 + (n_strip - 10) * 0.026)
        if rng.random() < p_nc:
            wts_nc = [max(0.02, t[2]) for t in strip_non_coal]
            pick_nc = rng.choices(strip_non_coal, weights=wts_nc, k=1)[0]
            return (pick_nc[0], pick_nc[1])

    if not opts:
        return None
    opts.sort(key=lambda t: -t[2])
    top = opts[: min(6, len(opts))]
    weights = [max(0.02, t[2]) for t in top]
    pick = rng.choices(top, weights=weights, k=1)[0]
    return (pick[0], pick[1])


def _list_price_cents(world: World, material: MaterialId) -> int:
    ba = best_resting_ask_cents(world, material)
    if ba is not None:
        return max(4, ba - 1)
    return max(4, _FALLBACK_LIST_CENTS.get(str(material), 40))


def _ensure_workshop(world: World, party: PartyId, plot_id: PlotId, building_id: str) -> bool:
    for b in world.plot_buildings:
        if b.get("party") != str(party) or b.get("plot_id") != str(plot_id):
            continue
        if b.get("building_id") == building_id:
            return True
    need = _TURNKEY_CENTS.get(building_id)
    if need is None:
        return False
    cash = world.ledger.balance(party_cash_account(party))
    if cash < need + 25_000:  # keep a labor + small-buy buffer
        return False
    r = build_on_plot(world, party, plot_id, building_id, "turnkey")
    return bool(r.get("ok"))


def _stock_room(world: World, party: PartyId) -> int:
    cap = party_storage_cap_units(world, party)
    return cap - party_inventory_unit_total(world, party)


def _ensure_recipe_inputs(world: World, party: PartyId, recipe_id: str) -> None:
    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        return
    room = _stock_room(world, party)
    if room < 4:
        return
    for mid, need in recipe.inputs.items():
        have = world.inventory.qty(party, mid)
        if have >= need:
            continue
        deficit = need - have
        clip = min(deficit + 8, room, 24)
        market_buy(world, party, mid, clip)


def _settler_sell_material(world: World, party: PartyId, mid: MaterialId, max_units: int) -> None:
    if max_units <= 0:
        return
    sell_into_bids(world, party, mid, max_units)
    q = world.inventory.qty(party, mid)
    if q <= 0:
        return
    cancel_party_asks_for_material(world, party, mid)
    px = _list_price_cents(world, mid)
    place_sell_order(world, party, mid, min(q, max_units), px)


def _tick_one_settler(world: World, party: PartyId, scan: list[PlotId]) -> None:
    owned = _first_owned_plot(world, party)
    if owned is None:
        for pid in scan:
            plot = world.plots[pid]
            if plot.owner is None:
                claim_plot(world, party, pid)
                break
        return

    plot = world.plots[owned]
    if not plot.surveyed:
        cash = world.ledger.balance(party_cash_account(party))
        if cash >= SURVEY_COST_CENTS:
            survey_plot(world, party, owned)
        return

    line = _pick_settler_line(world, party, plot)
    if line is None:
        return
    recipe_id, building_id = line
    if not _ensure_workshop(world, party, owned, building_id):
        return

    if plot_has_active_production(world, owned):
        recipe = RECIPES.get(recipe_id)
        if recipe:
            for out_m, _oq in recipe.outputs.items():
                hq = world.inventory.qty(party, out_m)
                if hq >= 3:
                    _settler_sell_material(world, party, out_m, min(hq - 1, 24))
        return

    _ensure_recipe_inputs(world, party, recipe_id)
    start_production_on_plot(world, party, owned, recipe_id)

    recipe = RECIPES.get(recipe_id)
    if recipe:
        for out_m in recipe.outputs:
            hq = world.inventory.qty(party, out_m)
            if hq >= 2:
                _settler_sell_material(world, party, out_m, min(hq, 20))


def tick_settler_business(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    scan = _plots_manhattan_order(world)
    dry_scan = [pid for pid in scan if terrain_allows_workshop(world.plots[pid].terrain)]
    settlers = sorted((p for p in world.parties if str(p).startswith("settler_")), key=str)
    for party in settlers:
        _tick_one_settler(world, party, dry_scan)
