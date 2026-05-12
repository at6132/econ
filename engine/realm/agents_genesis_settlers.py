"""Genesis settlers — claim, survey, build workshops, extract, buy inputs, process, sell competitively."""

from __future__ import annotations

import random
from collections import Counter

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
from realm.plot_logistics import (
    ensure_inventory_from_stash,
    party_material_held,
    party_material_on_plot,
)
from realm.production import plot_has_active_production
from realm.recipe_workshops import recipe_ids_on_plot_for_owner
from realm.recipe_sites import recipe_allowed_on_terrain, subsurface_allows_recipe, terrain_allows_workshop
from realm.recipes import RECIPES
from realm.storage_caps import party_inventory_unit_total, party_storage_cap_units
from realm.time_scale import legacy_scaled
from realm.terrain import Terrain
from realm.world import ActiveProduction, World

_TURNKEY_CENTS: dict[str, int] = {
    bid: int(spec["turnkey_total_cents"])
    for bid, spec in BUILDINGS.items()
    if str(spec.get("kind")) == "contracted" and "turnkey_total_cents" in spec
}

_PRIMARY_WORKSHOPS = frozenset({"strip_mine", "timber_yard", "grain_row"})
_SECONDARY_WORKSHOPS = frozenset(
    {"power_shed", "wood_shop", "gristmill", "kiln_shed", "foundry", "stone_works"}
)

# Long / brittle chains for Phase-1 settler AI — rest stay eligible if terrain + workshop match.
_SETTLER_EXCLUDE_RECIPES = frozenset(
    {
        "steel_alloy",
        "wire_draw",
        "build_ladder",
        "glass_blow",
        "lime_burn",
        "mortar_mix",
    }
)

_PRIMARY_RECIPES = frozenset(
    {
        "mine_coal",
        "mine_iron_ore",
        "mine_copper_ore",
        "dig_clay",
        "mine_stone",
        "chop_timber",
        "grow_grain",
    }
)

_FALLBACK_LIST_CENTS: dict[str, int] = {
    "coal": 58,
    "timber": 90,
    "grain": 120,
    "electricity": 50,
    "stone": 44,
    "clay": 36,
    "iron_ore": 72,
    "copper_ore": 70,
    "flour": 95,
    "bread": 140,
    "brick": 110,
    "lumber": 125,
    "rope": 85,
    "iron_ingot": 420,
    "copper_ingot": 380,
    "charcoal": 70,
    "sand": 55,
    "limestone": 48,
    "slag": 25,
    "pottery": 90,
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


def _nearby_all_building_counts(world: World, x: int, y: int, radius: int) -> Counter[str]:
    c: Counter[str] = Counter()
    for b in world.plot_buildings:
        pid = PlotId(str(b.get("plot_id", "")))
        pl = world.plots.get(pid)
        if pl is None:
            continue
        if abs(pl.x - x) + abs(pl.y - y) > radius:
            continue
        bid = str(b.get("building_id", ""))
        if bid:
            c[bid] += 1
    return c


def _has_primary_on_plot(world: World, party: PartyId, plot_id: PlotId) -> bool:
    return any(
        b.get("party") == str(party)
        and b.get("plot_id") == str(plot_id)
        and str(b.get("building_id")) in _PRIMARY_WORKSHOPS
        for b in world.plot_buildings
    )


def _has_secondary_on_plot(world: World, party: PartyId, plot_id: PlotId) -> bool:
    return any(
        b.get("party") == str(party)
        and b.get("plot_id") == str(plot_id)
        and str(b.get("building_id")) in _SECONDARY_WORKSHOPS
        for b in world.plot_buildings
    )


def _workshop_type_count_on_plot(world: World, party: PartyId, plot_id: PlotId) -> int:
    seen: set[str] = set()
    for b in world.plot_buildings:
        if b.get("party") != str(party) or b.get("plot_id") != str(plot_id):
            continue
        bid = str(b.get("building_id", ""))
        if bid:
            seen.add(bid)
    return len(seen)


def _settler_has_strip_mine_on_plot(world: World, party: PartyId, plot_id: PlotId) -> bool:
    return any(
        b.get("party") == str(party)
        and b.get("plot_id") == str(plot_id)
        and str(b.get("building_id")) == "strip_mine"
        for b in world.plot_buildings
    )


def _maybe_build_secondary_workshop(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    plot,
    *,
    rng: random.Random,
) -> None:
    """One add-on workshop per plot — chosen from regional scarcity + terrain/subsurface."""
    if world.tick < legacy_scaled(12):
        return
    if _has_secondary_on_plot(world, party, plot_id):
        return
    if not _has_primary_on_plot(world, party, plot_id):
        return

    cx, cy = plot.x, plot.y
    near = _nearby_all_building_counts(world, cx, cy, 9)
    targets = {
        "gristmill": 3,
        "wood_shop": 4,
        "power_shed": 3,
        "kiln_shed": 2,
        "stone_works": 3,
        "foundry": 2,
    }

    def gap(bid: str) -> float:
        return float(targets[bid]) - float(near.get(bid, 0))

    candidates: list[tuple[str, float]] = []

    if recipe_allowed_on_terrain(plot.terrain, "coal_generator"):
        candidates.append(("power_shed", gap("power_shed") + rng.random() * 0.12))

    if recipe_allowed_on_terrain(plot.terrain, "sawmill"):
        candidates.append(("wood_shop", gap("wood_shop") + rng.random() * 0.12))

    if recipe_allowed_on_terrain(plot.terrain, "mill_flour"):
        candidates.append(("gristmill", gap("gristmill") + rng.random() * 0.12))

    if recipe_allowed_on_terrain(plot.terrain, "kiln_brick"):
        if float(plot.subsurface.clay_grade) >= 0.22 or _settler_has_strip_mine_on_plot(
            world, party, plot_id
        ):
            candidates.append(("kiln_shed", gap("kiln_shed") + 0.18 + rng.random() * 0.1))

    if recipe_allowed_on_terrain(plot.terrain, "mine_stone"):
        candidates.append(("stone_works", gap("stone_works") + rng.random() * 0.1))

    if plot.terrain == Terrain.MOUNTAIN and float(plot.subsurface.iron_ore_grade) >= 0.28:
        if recipe_allowed_on_terrain(plot.terrain, "smelt_iron"):
            candidates.append(("foundry", gap("foundry") + 0.22 + rng.random() * 0.08))

    if not candidates:
        return

    candidates.sort(key=lambda t: -t[1])
    chosen = candidates[0][0]
    need = _TURNKEY_CENTS.get(chosen, 0)
    if need <= 0:
        return
    extra = 120_000 if chosen == "foundry" else 58_000
    cash = world.ledger.balance(party_cash_account(party))
    if cash < need + extra:
        return
    build_on_plot(world, party, plot_id, chosen, "turnkey")


def _pick_settler_line(world: World, party: PartyId, plot) -> tuple[str, str] | None:
    """Weighted primary line — ``mine_stone`` uses ``stone_works`` (not strip_mine)."""
    rng = world.rng(f"gen:settler_line2:{party}:{plot.plot_id}")
    counts = _settler_workshop_counts(world)
    n_strip = int(counts.get("strip_mine", 0))
    n_yard = int(counts.get("timber_yard", 0))
    n_row = int(counts.get("grain_row", 0))
    sal = _party_salience_jitter(party)

    if plot.terrain == Terrain.PLAINS and n_strip >= 9:
        p_gr = min(0.86, 0.26 + (n_strip - 9) * 0.03)
        if recipe_allowed_on_terrain(plot.terrain, "grow_grain") and rng.random() < p_gr:
            return ("grow_grain", "grain_row")
    if plot.terrain == Terrain.FOREST and n_strip >= 8:
        p_ch = min(0.86, 0.24 + (n_strip - 8) * 0.03)
        if recipe_allowed_on_terrain(plot.terrain, "chop_timber") and rng.random() < p_ch:
            return ("chop_timber", "timber_yard")

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
        opts.append(("mine_stone", "stone_works", max(0.06, w)))

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


def _workshop_cash_buffer(building_id: str) -> int:
    if building_id == "foundry":
        return 120_000
    if building_id in _SECONDARY_WORKSHOPS:
        return 58_000
    return 25_000


def _ensure_workshop(world: World, party: PartyId, plot_id: PlotId, building_id: str) -> bool:
    for b in world.plot_buildings:
        if b.get("party") != str(party) or b.get("plot_id") != str(plot_id):
            continue
        if b.get("building_id") == building_id:
            return True
    need = _TURNKEY_CENTS.get(building_id)
    if need is None:
        return False
    buf = _workshop_cash_buffer(building_id)
    cash = world.ledger.balance(party_cash_account(party))
    if cash < need + buf:
        return False
    r = build_on_plot(world, party, plot_id, building_id, "turnkey")
    return bool(r.get("ok"))


def _stock_room(world: World, party: PartyId) -> int:
    cap = party_storage_cap_units(world, party)
    return cap - party_inventory_unit_total(world, party)


def _ensure_recipe_inputs(world: World, party: PartyId, recipe_id: str, *, staging_plot_id: PlotId) -> None:
    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        return
    room = _stock_room(world, party)
    if room < 4:
        return
    for mid, need in recipe.inputs.items():
        have = party_material_on_plot(world, party, staging_plot_id, mid)
        if have >= need:
            continue
        deficit = need - have
        clip = min(deficit + 14, room, 56)
        market_buy(world, party, mid, clip)


def _recipe_inputs_satisfied(world: World, party: PartyId, recipe_id: str, plot_id: PlotId) -> bool:
    rec = RECIPES.get(recipe_id)
    if rec is None:
        return False
    return all(party_material_on_plot(world, party, plot_id, m) >= q for m, q in rec.inputs.items())


def _recipe_rank_score(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    recipe_id: str,
    *,
    rng: random.Random,
) -> float:
    rec = RECIPES.get(recipe_id)
    if rec is None:
        return -1e9
    nw = _workshop_type_count_on_plot(world, party, plot_id)
    prim = recipe_id in _PRIMARY_RECIPES
    miss = 0
    for m, q in rec.inputs.items():
        short = party_material_on_plot(world, party, plot_id, m) - q
        if short < 0:
            miss -= short
    labor_ok = 1.0 if world.ledger.balance(party_cash_account(party)) >= rec.labor_cents else -50.0
    bonus = 3.8 if (nw >= 2 and not prim) else (1.6 if prim else 2.4)
    return bonus + labor_ok - miss * 0.38 + rng.random() * 0.06


def _pick_recipe_to_start(world: World, party: PartyId, plot, plot_id: PlotId) -> str | None:
    eligible = [
        r
        for r in recipe_ids_on_plot_for_owner(world, plot)
        if r not in _SETTLER_EXCLUDE_RECIPES
    ]
    if not eligible:
        return None
    rng = world.rng(f"gen:recipe_pick:{party}:{plot.plot_id}:{world.tick}")
    ranked = sorted(
        eligible,
        key=lambda rid: -_recipe_rank_score(world, party, plot_id, rid, rng=rng),
    )
    for rid in ranked[:14]:
        _ensure_recipe_inputs(world, party, rid, staging_plot_id=plot_id)
        if not _recipe_inputs_satisfied(world, party, rid, plot_id):
            continue
        rec = RECIPES[rid]
        if world.ledger.balance(party_cash_account(party)) < rec.labor_cents:
            continue
        return rid
    return None


def _active_run(world: World, party: PartyId, plot_id: PlotId) -> ActiveProduction | None:
    for run in world.active_production:
        if run.party == party and run.plot_id == plot_id:
            return run
    return None


_STOCKPILE_MATS: tuple[str, ...] = (
    "rope",
    "slag",
    "brick",
    "charcoal",
    "pottery",
    "lumber",
    "flour",
    "bread",
    "sand",
    "stone",
    "clay",
    "iron_ore",
    "copper_ore",
    "glass",
    "mortar",
)


def _liquidate_settler_stockpiles(world: World, party: PartyId) -> None:
    """Push chronic surpluses into bids + relist so cash recycles (integration with the book)."""
    if not str(party).startswith("settler_"):
        return
    for mid_s in _STOCKPILE_MATS:
        mid = MaterialId(mid_s)
        q = party_material_held(world, party, mid)
        if q >= 20:
            _settler_sell_material(world, party, mid, min(q - 3, 40))


def _settler_sell_material(world: World, party: PartyId, mid: MaterialId, max_units: int) -> None:
    if max_units <= 0:
        return
    total = party_material_held(world, party, mid)
    if total <= 0:
        return
    ensure_inventory_from_stash(world, party, mid, min(max_units, total))
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
    _recipe_id, building_id = line
    if not _ensure_workshop(world, party, owned, building_id):
        return

    rng_sec = world.rng(f"gen:secondary:{party}:{world.tick}")
    _maybe_build_secondary_workshop(world, party, owned, plot, rng=rng_sec)

    _liquidate_settler_stockpiles(world, party)

    if plot_has_active_production(world, owned):
        run = _active_run(world, party, owned)
        recipe = RECIPES.get(run.recipe_id) if run else None
        if recipe:
            for out_m in recipe.outputs:
                hq = party_material_held(world, party, out_m)
                if hq >= 2:
                    _settler_sell_material(world, party, out_m, min(hq - 1, 30))
        return

    chosen_rid = _pick_recipe_to_start(world, party, plot, owned)
    if not chosen_rid:
        return
    _ensure_recipe_inputs(world, party, chosen_rid, staging_plot_id=owned)
    start_production_on_plot(world, party, owned, chosen_rid)

    recipe = RECIPES.get(chosen_rid)
    if recipe:
        for out_m in recipe.outputs:
            hq = party_material_held(world, party, out_m)
            if hq >= 2:
                _settler_sell_material(world, party, out_m, min(hq, 24))


def tick_settler_business(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    scan = _plots_manhattan_order(world)
    dry_scan = [pid for pid in scan if terrain_allows_workshop(world.plots[pid].terrain)]
    settlers = sorted((p for p in world.parties if str(p).startswith("settler_")), key=str)
    for party in settlers:
        _tick_one_settler(world, party, dry_scan)
