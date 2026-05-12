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
from realm.recipe_sites import recipe_allowed_on_terrain, subsurface_allows_recipe
from realm.recipes import RECIPES
from realm.storage_caps import party_inventory_unit_total, party_storage_cap_units
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


def _pick_settler_line(world: World, plot) -> tuple[str, str] | None:
    """Return (recipe_id, building_id) for this surveyed plot, or None."""
    rng = world.rng(f"gen:settler_line:{plot.plot_id}")
    candidates: list[tuple[float, str]] = []
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
        candidates.append((g + rng.random() * 1e-6, rid))
    if candidates:
        candidates.sort(key=lambda t: -t[0])
        return (candidates[0][1], "strip_mine")
    if recipe_allowed_on_terrain(plot.terrain, "mine_stone"):
        return ("mine_stone", "strip_mine")
    if recipe_allowed_on_terrain(plot.terrain, "chop_timber"):
        return ("chop_timber", "timber_yard")
    if recipe_allowed_on_terrain(plot.terrain, "grow_grain"):
        return ("grow_grain", "grain_row")
    return None


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

    line = _pick_settler_line(world, plot)
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
    settlers = sorted((p for p in world.parties if str(p).startswith("settler_")), key=str)
    for party in settlers:
        _tick_one_settler(world, party, scan)
