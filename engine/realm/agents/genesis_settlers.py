"""Genesis settlers — claim, survey, build workshops, extract, buy inputs, process, sell competitively."""

from __future__ import annotations

import random
from collections import Counter, defaultdict

from realm.actions import SURVEY_COST_CENTS, claim_plot, start_production_on_plot, survey_plot
from realm.production.buildings import BUILDINGS, build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.economy.pricing import settler_ask_cents
from realm.economy.markets import (
    best_resting_bid_cents,
    cancel_party_asks_for_material,
    market_buy,
    place_sell_order,
    sell_into_bids,
)
from realm.agents.requote_dampener import (
    charge_cancel_fee,
    record_requote,
    should_requote,
)
from realm.infrastructure.plot_logistics import (
    ensure_inventory_from_stash,
    party_material_held,
    party_material_on_plot,
)
from realm.production import plot_has_active_production
from realm.production.recipe_workshops import recipe_ids_on_plot_for_owner
from realm.production.recipe_sites import recipe_allowed_on_terrain, subsurface_allows_recipe, terrain_allows_workshop
from realm.production.recipes import RECIPES
from realm.production.storage_caps import party_inventory_unit_total, party_storage_cap_units
from realm.core.time_scale import legacy_scaled
from realm.world.terrain import Terrain
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
_TIER2_WORKSHOPS = frozenset(
    {"assay_lab", "blast_furnace", "chemical_works", "forge_press", "machine_shop", "tool_workshop"}
)

# Daily probability that a settler with an ``assay_lab`` advances one stage on their richest
# Tier-2 mineral. Real-time-equivalent: a 1% chance per game-day (deterministic RNG, never
# random.random()). Rolled once per game-day per settler in ``_settler_probabilistic_discovery``.
SETTLER_DISCOVERY_PROB_PER_GAME_DAY: float = 0.01

# When non-empty, a settler with the listed grade ≥ value can decide to build an assay_lab.
_TIER2_GRADE_FIELDS: tuple[tuple[str, str], ...] = (
    ("sulfur_grade", "sulfur_ore"),
    ("saltpeter_grade", "saltpeter_ore"),
    ("tin_grade", "tin_ore"),
    ("lead_grade", "lead_ore"),
    ("phosphate_grade", "phosphate_ore"),
    ("silica_grade", "raw_silica"),
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

# Claim → survey → build → … can span many logical steps; chain several per tick until blocked.
SETTLER_PIPELINE_BURST = 16


_plot_scan_cache: dict[int, tuple[list[PlotId], list[PlotId]]] = {}
_owned_plots_cache: dict[tuple[int, int], dict[PartyId, tuple[PlotId, ...]]] = {}
_plot_cache_gen: dict[int, int] = {}

SETTLER_TICK_STRIDE: int = 8


def invalidate_settler_plot_caches() -> None:
    """Call when plot ownership or the plots map changes (e.g. claim_plot)."""
    _plot_scan_cache.clear()
    _owned_plots_cache.clear()
    pid_keys = list(_plot_cache_gen.keys())
    for pid in pid_keys:
        _plot_cache_gen[pid] = int(_plot_cache_gen.get(pid, 0)) + 1


def _owned_plots_by_party(world: World) -> dict[PartyId, tuple[PlotId, ...]]:
    """Single pass over the map — cached until a plot is claimed."""
    plots_id = id(world.plots)
    gen = int(_plot_cache_gen.get(plots_id, 0))
    cache_key = (plots_id, gen)
    cached = _owned_plots_cache.get(cache_key)
    if cached is not None:
        return cached
    buckets: defaultdict[PartyId, list[PlotId]] = defaultdict(list)
    for pl in world.plots.values():
        o = pl.owner
        if o is not None:
            buckets[o].append(pl.plot_id)
    result = {p: tuple(sorted(ids, key=str)) for p, ids in buckets.items()}
    if len(_owned_plots_cache) > 6:
        _owned_plots_cache.clear()
    _owned_plots_cache[cache_key] = result
    return result


def _plot_scan_bundle(world: World) -> tuple[list[PlotId], list[PlotId]]:
    cache_key = id(world.plots)
    cached = _plot_scan_cache.get(cache_key)
    if cached is not None:
        return cached
    if not world.plots:
        bundle: tuple[list[PlotId], list[PlotId]] = ([], [])
    else:
        xs = [p.x for p in world.plots.values()]
        ys = [p.y for p in world.plots.values()]
        cx = (min(xs) + max(xs)) // 2
        cy = (min(ys) + max(ys)) // 2
        ordered = sorted(
            world.plots.values(),
            key=lambda p: (abs(p.x - cx) + abs(p.y - cy), p.x, p.y),
        )
        order = [p.plot_id for p in ordered]
        dry = [
            pid
            for pid in order
            if terrain_allows_workshop(world.plots[pid].terrain)
        ]
        bundle = (order, dry)
    if len(_plot_scan_cache) > 3:
        _plot_scan_cache.clear()
    _plot_scan_cache[cache_key] = bundle
    return bundle


def _plots_manhattan_order(world: World) -> list[PlotId]:
    order, _ = _plot_scan_bundle(world)
    return order


def _world_dimensions(world: World) -> tuple[int, int]:
    # Cached for the lifetime of one tick: 16k-plot Genesis tick used to call
    # this 15k+ times via _settler_home_anchor (~3 s per tick wasted).
    if not world.plots:
        return (1, 1)
    from realm.world.runtime_cache import bucket

    cache = bucket(world).get("_world_dims_cache")
    if isinstance(cache, dict) and int(cache.get("tick", -1)) == int(world.tick):
        return (int(cache["w"]), int(cache["h"]))
    max_x = 0
    max_y = 0
    for p in world.plots.values():
        if p.x > max_x:
            max_x = p.x
        if p.y > max_y:
            max_y = p.y
    dims = (max_x + 1, max_y + 1)
    bucket(world)["_world_dims_cache"] = {
        "tick": int(world.tick),
        "w": dims[0],
        "h": dims[1],
    }
    return dims


def _settler_home_anchor(world: World, party: PartyId) -> tuple[int, int]:
    """Deterministic per-party "preferred starting region" — one of four quadrant anchors.

    Without this, every settler would walk the same Manhattan-from-grid-center scan order
    and pile onto whichever quadrant happens to sit closest to the grid centre. On the
    Genesis four-islands map that would mean every settler claims the same island and the
    other three landmasses stay frontier forever, which defeats the regional supply /
    demand asymmetry the geography is meant to create. Hashing the party id into one of
    four quadrant-corner anchors spreads settlers across all four quadrants while keeping
    determinism (Law 9) intact.
    """
    w, h = _world_dimensions(world)
    anchors = (
        (w // 4, h // 4),
        (3 * w // 4, h // 4),
        (w // 4, 3 * h // 4),
        (3 * w // 4, 3 * h // 4),
    )
    s = str(party)
    acc = 0
    for ch in s:
        acc = (acc * 131 + ord(ch)) & 0xFFFFFFFF
    return anchors[acc % 4]


def _scan_from_anchor(world: World, dry_scan: list[PlotId], anchor: tuple[int, int]) -> list[PlotId]:
    """Re-sort ``dry_scan`` by Manhattan distance from ``anchor`` (stable tie-break).

    Cached per (tick, anchor) — there are only 4 anchors at runtime but each
    settler called this without the cache (~28 s / tick on Genesis).
    """
    from realm.world.runtime_cache import bucket

    cache = bucket(world).get("_scan_from_anchor_cache")
    if not isinstance(cache, dict) or int(cache.get("tick", -1)) != int(world.tick):
        cache = {"tick": int(world.tick)}
        bucket(world)["_scan_from_anchor_cache"] = cache
    key = f"{int(anchor[0])},{int(anchor[1])}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    ax, ay = anchor
    plots = world.plots
    ordered = sorted(
        dry_scan,
        key=lambda pid: (
            abs(plots[pid].x - ax) + abs(plots[pid].y - ay),
            plots[pid].x,
            plots[pid].y,
        ),
    )
    cache[key] = ordered
    return ordered


def _first_owned_plot(world: World, party: PartyId) -> PlotId | None:
    """O(plots) scan. Hot path callers should prefer ``owned_by_party[party][0]``
    from the per-tick index built at the top of ``tick_settler_business``;
    this remains for paths where that index isn't threaded yet."""
    for pid, pl in world.plots.items():
        if pl.owner == party:
            return pid
    return None


def _first_owned_plot_indexed(
    owned_by_party: dict[PartyId, tuple[PlotId, ...]], party: PartyId
) -> PlotId | None:
    """O(1) lookup against the per-tick owned-plots index."""
    ids = owned_by_party.get(party)
    return ids[0] if ids else None


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


def _settler_richest_tier2_on_plot(plot) -> tuple[str, float] | None:
    """Returns ``(mineral_id, grade)`` for the highest Tier-2 grade on this plot, or None if all <0.3."""
    best: tuple[str, float] | None = None
    for field, mineral in _TIER2_GRADE_FIELDS:
        g = float(getattr(plot.subsurface, field, 0.0))
        if g < 0.3:
            continue
        if best is None or g > best[1]:
            best = (mineral, g)
    return best


def _settler_assay_lab_plot(world: World, party: PartyId) -> PlotId | None:
    """The settler's first plot containing an operational assay_lab they own (or None)."""
    from realm.production.decay import building_effective_for_bonuses
    from realm.core.time_scale import building_operational

    for b in world.plot_buildings:
        if b.get("party") != str(party) or b.get("building_id") != "assay_lab":
            continue
        if not building_operational(b, at_tick=world.tick):
            continue
        if not building_effective_for_bonuses(b):
            continue
        return PlotId(str(b.get("plot_id", "")))
    return None


def _settler_probabilistic_discovery(world: World, party: PartyId) -> None:
    """One deterministic 1%/game-day roll: if it hits, advance the party's richest Tier-2 mineral one stage.

    Settlers without an assay_lab cannot benefit (matches the design — research needs a lab,
    but settlers self-research at a glacial pace so half the economy isn't permanently locked out
    of Tier-2 industry).
    """
    from realm.actions.assay_actions import (
        ASSAY_MAX_STAGE,
        ASSAY_MINERAL_RECIPE_UNLOCKS,
        ASSAY_STAGE_HINTS,
        get_assay_stage,
        _set_assay_stage,
    )
    from realm.events.event_log import log_event
    from realm.core.time_scale import TICKS_PER_GAME_DAY

    if world.tick % TICKS_PER_GAME_DAY != 0:
        return
    lab_plot = _settler_assay_lab_plot(world, party)
    if lab_plot is None:
        return
    plot = world.plots.get(lab_plot)
    if plot is None:
        return
    richest = _settler_richest_tier2_on_plot(plot)
    if richest is None:
        return
    mineral_id, _grade = richest
    mid = MaterialId(mineral_id)
    rng = world.rng(f"settler_discovery:{party}:{world.tick}")
    if rng.random() >= SETTLER_DISCOVERY_PROB_PER_GAME_DAY:
        return
    current = get_assay_stage(world, party, mid)
    if current >= ASSAY_MAX_STAGE:
        return
    new_stage = min(ASSAY_MAX_STAGE, current + 1)
    _set_assay_stage(world, party, mid, new_stage)
    log_event(
        world,
        "assay_stage",
        f"{party} (settler self-research) advanced {mineral_id} to stage {new_stage}/{ASSAY_MAX_STAGE}",
        party=str(party),
        mineral=mineral_id,
        stage=new_stage,
        source="settler_self_research",
    )
    if new_stage >= ASSAY_MAX_STAGE:
        from realm.production.recipes import RECIPES
        from realm.world import ensure_party_recipe_book

        unlocked = [
            rid
            for rid in ASSAY_MINERAL_RECIPE_UNLOCKS.get(mineral_id, ())
            if rid in RECIPES
        ]
        book = ensure_party_recipe_book(world, party)
        new_for_party = [rid for rid in unlocked if rid not in book]
        for rid in new_for_party:
            book.add(rid)
        log_event(
            world,
            "recipe_discovered",
            f"{party} (settler self-research) unlocked {len(new_for_party)} recipe(s) for {mineral_id}",
            party=str(party),
            mineral=mineral_id,
            recipes=",".join(new_for_party),
            recipe_count=len(new_for_party),
            source="settler_self_research",
        )
        log_event(
            world,
            "world_feed",
            f"DISCOVERY: {mineral_id} chain unlocked — {len(new_for_party)} new recipes available "
            f"({party}).",
            feed_source="recipe_discovery",
            party=str(party),
            mineral=mineral_id,
            recipe_count=len(new_for_party),
        )
        from realm.agents.settler_archetypes import maybe_create_discovery_blueprint

        for rid in new_for_party:
            maybe_create_discovery_blueprint(world, party, rid)


def _settler_has_book_recipe(world: World, party: PartyId, recipe_id: str) -> bool:
    return recipe_id in world.party_recipe_books.get(str(party), set())


def _settler_has_any_tier2_discovery(world: World, party: PartyId) -> bool:
    """Any Tier-2 recipe in the party's book counts as a discovery."""
    from realm.production.recipes import RECIPES

    tier2_ids = {rid for rid, r in RECIPES.items() if r.requires_discovery}
    book = world.party_recipe_books.get(str(party), set())
    return bool(book & tier2_ids)


def _settler_can_afford_tier2_build(
    world: World, party: PartyId, building_id: str, *, max_cash_share_bps: int = 6000
) -> bool:
    """Cash gate: settler will never spend more than ``max_cash_share_bps`` (60%) of cash on one build."""
    need = _TURNKEY_CENTS.get(building_id, 0)
    if need <= 0:
        return False
    cash = world.ledger.balance(party_cash_account(party))
    cap = cash * max_cash_share_bps // 10_000
    return cash >= need + 5_000 and need <= cap


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
        return False
    if not _settler_acquire_turnkey_materials(world, party, chosen):
        return
    build_on_plot(world, party, plot_id, chosen, "turnkey")


def _maybe_build_tier2_workshop(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    plot,
) -> bool:
    """Once Tier-1 is settled and the settler has cash to spare, consider a Tier-2 workshop.

    Priority order (first match wins):
      1. ``assay_lab`` — any Tier-2 grade ≥ 0.3 on this plot, no lab yet on any of the party's plots.
      2. ``blast_furnace`` — iron_ore_grade ≥ 0.5 AND coal_grade ≥ 0.3 on this plot.
      3. ``chemical_works`` — party has ≥1 Tier-2 recipe in their book.
      4. ``forge_press`` / ``tool_workshop`` — party has steel_ingot stock (income proxy).

    All builds are turnkey and limited to ≤60% of cash. Returns True if anything was built.
    """
    if world.tick < legacy_scaled(60):
        return False

    def _already_has(bid: str) -> bool:
        return any(
            b.get("party") == str(party) and b.get("building_id") == bid
            for b in world.plot_buildings
        )

    if not _already_has("assay_lab") and _settler_richest_tier2_on_plot(plot) is not None:
        if _settler_can_afford_tier2_build(world, party, "assay_lab"):
            if _settler_acquire_turnkey_materials(world, party, "assay_lab"):
                r = build_on_plot(world, party, plot_id, "assay_lab", "turnkey")
                if r.get("ok"):
                    return True

    if (
        not _already_has("blast_furnace")
        and float(plot.subsurface.iron_ore_grade) >= 0.5
        and float(plot.subsurface.coal_grade) >= 0.3
        and recipe_allowed_on_terrain(plot.terrain, "smelt_pig_iron")
        and _settler_can_afford_tier2_build(world, party, "blast_furnace")
    ):
        if _settler_acquire_turnkey_materials(world, party, "blast_furnace"):
            r = build_on_plot(world, party, plot_id, "blast_furnace", "turnkey")
            if r.get("ok"):
                return True

    if (
        not _already_has("chemical_works")
        and _settler_has_any_tier2_discovery(world, party)
        and recipe_allowed_on_terrain(plot.terrain, "refine_sulfur")
        and _settler_can_afford_tier2_build(world, party, "chemical_works")
    ):
        if _settler_acquire_turnkey_materials(world, party, "chemical_works"):
            r = build_on_plot(world, party, plot_id, "chemical_works", "turnkey")
            if r.get("ok"):
                return True

    steel = world.inventory.qty(party, MaterialId("steel_ingot"))
    if (
        steel >= 1
        and not _already_has("forge_press")
        and recipe_allowed_on_terrain(plot.terrain, "forge_pick_head")
        and _settler_can_afford_tier2_build(world, party, "forge_press")
    ):
        if _settler_acquire_turnkey_materials(world, party, "forge_press"):
            r = build_on_plot(world, party, plot_id, "forge_press", "turnkey")
            if r.get("ok"):
                return True

    if (
        not _already_has("tool_workshop")
        and recipe_allowed_on_terrain(plot.terrain, "assemble_mining_pick")
        and _settler_can_afford_tier2_build(world, party, "tool_workshop")
    ):
        if _settler_acquire_turnkey_materials(world, party, "tool_workshop"):
            r = build_on_plot(world, party, plot_id, "tool_workshop", "turnkey")
            if r.get("ok"):
                return True

    return False


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


def _list_price_cents(
    world: World, material: MaterialId, *, party: PartyId | None = None
) -> int:
    """
    Settler ask: cost-basis + margin, capped below the clearinghouse spread.

    Sprint 2 — Phase B: when ``party`` is supplied **and** that party has a
    recorded ``output_basis`` for ``material``, use the per-settler basis
    directly (``basis × 1.35``). This is what gives vertically-integrated
    settlers — who paid 0¢ for their own coal — a structurally lower ask
    than peers who buy inputs from the exchange.

    Falls back to the static ``settler_ask_cents`` (fair-value × markup) when
    no per-party basis is available yet (first listings, new materials, etc.).

    A final cap keeps the ask strictly below the exchange's ask so price-time
    priority still routes hub demand to settlers when they exist.
    """
    bid = best_resting_bid_cents(world, material)
    if party is not None:
        from realm.genesis.settler_cost_basis import settler_listing_price_cents

        basis_px = settler_listing_price_cents(world, party, material)
        if basis_px is not None:
            from realm.economy.pricing import exchange_ask_cents

            ex = exchange_ask_cents(material, world=world)
            ceiling = max(4, ex - 2)
            floor = 4
            if bid is not None and int(bid) >= floor:
                # Lift any real bid above floor; but never above the exchange ceiling.
                return max(floor, min(ceiling, max(basis_px, int(bid) + 1)))
            # No supportive bid: list at basis_px but never *above* exchange ceiling.
            return max(floor, min(ceiling, basis_px))
    return settler_ask_cents(world, material, best_resting_bid=bid)


def _settler_market_buy(
    world: World, party: PartyId, material: MaterialId, qty: int
) -> dict:
    """Wrap ``market_buy`` so every settler purchase feeds the cost-basis tracker."""
    from realm.genesis.settler_cost_basis import record_settler_buy

    r = market_buy(world, party, material, qty)
    if r.get("ok"):
        record_settler_buy(
            world, party, material, int(r.get("filled", 0)), int(r.get("spent_cents", 0))
        )
    return r


def _settler_acquire_turnkey_materials(world: World, party: PartyId, building_id: str) -> bool:
    """Buy missing ``self_materials`` from the book before ``turnkey`` build (Genesis settlers)."""
    spec = BUILDINGS.get(building_id)
    if not spec or str(spec.get("kind")) != "contracted":
        return True
    for mid_s, qty in (spec.get("self_materials") or {}).items():
        mid = MaterialId(mid_s)
        need = int(qty) - int(world.inventory.qty(party, mid))
        if need <= 0:
            continue
        r = _settler_market_buy(world, party, mid, need)
        filled = int(r.get("filled", 0))
        if not r.get("ok") or filled < need:
            return False
    return True


def _ensure_settler_boot_tools(world: World, party: PartyId, primary_recipe: str | None) -> None:
    """One-time mining pick (+ spade for clay line) so Tier-0 extraction can run while saving for builds."""
    if not str(party).startswith("settler_"):
        return
    gst = world.scenario_state.setdefault("genesis", {})
    key = "settler_tool_init"
    done: set[str] = {str(x) for x in gst.setdefault(key, [])}
    if str(party) in done:
        return
    ok = True
    if world.inventory.qty(party, MaterialId("mining_pick")) < 1:
        r = _settler_market_buy(world, party, MaterialId("mining_pick"), 1)
        ok = bool(r.get("ok") and int(r.get("filled", 0)) >= 1)
    if ok and primary_recipe == "dig_clay" and world.inventory.qty(party, MaterialId("spade")) < 1:
        r2 = _settler_market_buy(world, party, MaterialId("spade"), 1)
        ok = bool(r2.get("ok") and int(r2.get("filled", 0)) >= 1)
    if ok:
        done.add(str(party))
        gst[key] = sorted(done)


def _settler_try_hand_extraction(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    plot,
    *,
    prefer_recipe: str | None,
) -> bool:
    """Slow Tier-0 income while workshop materials are still being sourced."""
    if plot_has_active_production(world, plot_id):
        return False
    if _has_primary_on_plot(world, party, plot_id):
        return False
    candidates: list[str] = []
    if prefer_recipe == "mine_coal" and world.inventory.qty(party, MaterialId("mining_pick")) >= 1:
        candidates.append("hand_mine_coal")
    if prefer_recipe == "dig_clay" and world.inventory.qty(party, MaterialId("spade")) >= 1:
        candidates.append("hand_dig_clay")
    if world.inventory.qty(party, MaterialId("mining_pick")) >= 1:
        candidates.append("hand_mine_coal")
    if world.inventory.qty(party, MaterialId("pick_axe")) >= 1:
        candidates.append("hand_chop")
    if world.inventory.qty(party, MaterialId("spade")) >= 1:
        candidates.append("hand_dig_clay")
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    for rid in ordered:
        rec = RECIPES.get(rid)
        if rec is None:
            continue
        if not recipe_allowed_on_terrain(plot.terrain, rid):
            continue
        if not subsurface_allows_recipe(plot, rec):
            continue
        if world.ledger.balance(party_cash_account(party)) < rec.labor_cents:
            continue
        r = start_production_on_plot(world, party, plot_id, rid)
        if r.get("ok") and r.get("started", True):
            return True
    return False


def _workshop_cash_buffer(building_id: str) -> int:
    if building_id == "foundry":
        return 120_000
    if building_id in _SECONDARY_WORKSHOPS:
        return 58_000
    return 25_000


_WORKSHOP_BUILDING_IDS = _PRIMARY_WORKSHOPS | _SECONDARY_WORKSHOPS | _TIER2_WORKSHOPS


def _maybe_post_settler_job_opening(world: World, party: PartyId, plot_id: PlotId) -> None:
    """Post one wage job when a settler workshop is operational (Phase 7E hook)."""
    if world.scenario_id != "genesis" or not str(party).startswith("settler_"):
        return
    now = int(world.tick)
    has_workshop = any(
        b.get("party") == str(party)
        and b.get("plot_id") == str(plot_id)
        and int(b.get("completes_at_tick", 0)) <= now
        and str(b.get("building_id", "")) in _WORKSHOP_BUILDING_IDS
        for b in world.plot_buildings
    )
    if not has_workshop:
        return
    for op in world.job_openings:
        if op.employer == party and op.plot_id == plot_id and op.filled_by is None:
            return
    from realm.population.employment import (
        DEFAULT_WAGE_PER_GAME_DAY_CENTS,
        post_job_opening,
    )

    wage_reserve = DEFAULT_WAGE_PER_GAME_DAY_CENTS * 7
    if world.ledger.balance(party_cash_account(party)) < wage_reserve:
        return
    post_job_opening(
        world,
        party,
        plot_id,
        skill_min=0,
        wage_per_day_cents=DEFAULT_WAGE_PER_GAME_DAY_CENTS,
    )


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
    if not _settler_acquire_turnkey_materials(world, party, building_id):
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
        _settler_market_buy(world, party, mid, clip)


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
    from realm.agents.market_oracle import get_oracle
    from realm.agents.settler_archetypes import (
        ARCHETYPE_RECIPE_AVOID,
        ARCHETYPE_RECIPE_BONUS,
        get_archetype,
    )

    rec = RECIPES.get(recipe_id)
    if rec is None:
        return -1e9
    oracle = get_oracle(world)
    archetype = get_archetype(party)
    nw = _workshop_type_count_on_plot(world, party, plot_id)
    prim = recipe_id in _PRIMARY_RECIPES
    miss = 0
    for m, q in rec.inputs.items():
        short = party_material_on_plot(world, party, plot_id, m) - q
        if short < 0:
            miss -= short
    labor_ok = 1.0 if world.ledger.balance(party_cash_account(party)) >= rec.labor_cents else -50.0
    bonus = 3.8 if (nw >= 2 and not prim) else (1.6 if prim else 2.4)

    margin = oracle.recipe_margins.get(recipe_id, 0.0)
    margin_bonus = 0.0
    if margin > 0.20:
        margin_bonus = 2.5
    elif margin > 0.05:
        margin_bonus = 1.0
    elif margin < -0.20:
        margin_bonus = -3.0
    elif margin < 0:
        margin_bonus = -1.0
    for out_mat in rec.outputs:
        if str(out_mat) in oracle.scarce:
            margin_bonus += 1.5
    for out_mat in rec.outputs:
        if str(out_mat) in oracle.flooded:
            margin_bonus -= 2.0
    if rec.outputs:
        out_depth = min(oracle.bid_depth.get(str(m), 0) for m in rec.outputs)
        if out_depth > 50:
            margin_bonus += 0.5
        elif out_depth < 5:
            margin_bonus -= 0.5

    arch_bonus = 0.0
    if recipe_id in ARCHETYPE_RECIPE_BONUS.get(archetype, set()):
        arch_bonus = 2.0
    if recipe_id in ARCHETYPE_RECIPE_AVOID.get(archetype, set()):
        arch_bonus = -2.5

    return (
        bonus
        + labor_ok
        - miss * 0.38
        + margin_bonus
        + arch_bonus
        + rng.random() * 0.06
    )


def _pick_recipe_to_start(
    world: World,
    party: PartyId,
    plot,
    plot_id: PlotId,
    *,
    prefer_recipe_id: str | None = None,
) -> str | None:
    eligible = [
        r
        for r in recipe_ids_on_plot_for_owner(world, plot)
        if r not in _SETTLER_EXCLUDE_RECIPES
    ]
    if not eligible:
        return None
    if prefer_recipe_id and prefer_recipe_id in eligible:
        rid = prefer_recipe_id
        _ensure_recipe_inputs(world, party, rid, staging_plot_id=plot_id)
        if _recipe_inputs_satisfied(world, party, rid, plot_id):
            rec = RECIPES[rid]
            if world.ledger.balance(party_cash_account(party)) >= rec.labor_cents:
                return rid
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


def _liquidate_settler_stockpiles(
    world: World,
    party: PartyId,
    owned_plot_ids: tuple[PlotId, ...],
) -> None:
    """Push chronic surpluses into bids + relist so cash recycles (integration with the book)."""
    if not str(party).startswith("settler_"):
        return
    for mid_s in _STOCKPILE_MATS:
        mid = MaterialId(mid_s)
        q = party_material_held(world, party, mid, owned_plot_ids=owned_plot_ids)
        if q >= 20:
            _settler_sell_material(
                world, party, mid, min(q - 3, 40), owned_plot_ids=owned_plot_ids
            )


def _settler_sell_material(
    world: World,
    party: PartyId,
    mid: MaterialId,
    max_units: int,
    *,
    owned_plot_ids: tuple[PlotId, ...],
) -> None:
    if max_units <= 0:
        return
    total = party_material_held(world, party, mid, owned_plot_ids=owned_plot_ids)
    if total <= 0:
        return
    ensure_inventory_from_stash(world, party, mid, min(max_units, total))
    sell_into_bids(world, party, mid, max_units)
    q = world.inventory.qty(party, mid)
    if q <= 0:
        return
    px = _list_price_cents(world, mid, party=party)
    if not should_requote(world, party, mid, "ask", px):
        return
    cancels = cancel_party_asks_for_material(world, party, mid)
    charge_cancel_fee(world, party, cancels)
    res = place_sell_order(world, party, mid, min(q, max_units), px)
    if res.get("ok"):
        record_requote(world, party, mid, "ask", px)


_TICKS_PER_GAME_DAY = 1440


def _settler_maintain_buildings(world: World, party: PartyId) -> None:
    """Buy maintenance materials from the exchange and call ``maintain_building`` for
    any of this settler's buildings whose ``due_at_tick`` is within ~1 game-day.

    Settlers prioritise maintenance over new construction — degraded plants destroy
    margin faster than a missed expansion.
    """
    from realm.production.decay import maintain_building, maintenance_schedule_for

    threshold = int(world.tick) + _TICKS_PER_GAME_DAY
    for row in list(world.plot_buildings):
        if row.get("party") != str(party):
            continue
        iid = str(row.get("instance_id") or "")
        if not iid:
            continue
        rec = world.building_maintenance.get(iid)
        if rec is None:
            continue
        if int(rec.get("efficiency_pct", 100)) == 0:
            # Stopped buildings still want fresh materials so we can revive them.
            pass
        elif int(rec.get("due_at_tick", 0)) > threshold:
            continue
        bid = str(row.get("building_id", ""))
        sched = maintenance_schedule_for(bid)
        if sched is None:
            continue
        mats = sched.get("materials") or {}
        # Acquire any missing material from the exchange.
        for mid_s, qty in mats.items():
            mid = MaterialId(mid_s)
            need = int(qty) - int(world.inventory.qty(party, mid))
            if need <= 0:
                continue
            _settler_market_buy(world, party, mid, need)
        # If we still lack materials, skip — try again next tick.
        ok = all(
            world.inventory.qty(party, MaterialId(m)) >= int(q)
            for m, q in mats.items()
        )
        if not ok:
            continue
        maintain_building(world, party, iid)


def _settler_pipeline_step(
    world: World,
    party: PartyId,
    scan: list[PlotId],
    owned_by_party: dict[PartyId, tuple[PlotId, ...]],
    *,
    allow_secondary: bool,
    preferred_line: tuple[str, str] | None = None,
) -> bool:
    """One settler micro-step; return True if we should try another step this same tick."""
    owned_plot_ids = owned_by_party.get(party, ())
    owned = owned_plot_ids[0] if owned_plot_ids else None
    if owned is None:
        # Per-party preferred starting region — see ``_settler_home_anchor`` docstring.
        party_scan = _scan_from_anchor(world, scan, _settler_home_anchor(world, party))
        for pid in party_scan:
            plot = world.plots[pid]
            if plot.owner is None:
                result = claim_plot(world, party, pid)
                if result.get("ok"):
                    owned_by_party[party] = owned_plot_ids + (pid,)
                return True
        return False

    plot = world.plots[owned]
    if not plot.surveyed:
        cash = world.ledger.balance(party_cash_account(party))
        if cash >= SURVEY_COST_CENTS:
            survey_plot(world, party, owned)
            return True
        return False

    if preferred_line is not None:
        line = preferred_line
    else:
        line = _pick_settler_line(world, party, plot)
    if line is None:
        return False
    _recipe_id, building_id = line
    _ensure_settler_boot_tools(world, party, _recipe_id)
    if not _ensure_workshop(world, party, owned, building_id):
        _settler_try_hand_extraction(world, party, owned, plot, prefer_recipe=_recipe_id)
        return False

    if allow_secondary:
        rng_sec = world.rng(f"gen:secondary:{party}:{world.tick}")
        _maybe_build_secondary_workshop(world, party, owned, plot, rng=rng_sec)
        if _has_secondary_on_plot(world, party, owned):
            _maybe_build_tier2_workshop(world, party, owned, plot)

    _settler_probabilistic_discovery(world, party)
    _settler_maintain_buildings(world, party)
    _liquidate_settler_stockpiles(world, party, owned_plot_ids)

    from realm.infrastructure.npc_self_roads import try_party_self_roads

    if try_party_self_roads(
        world,
        party,
        owned_plot_ids,
        buy_material=_settler_market_buy,
        max_attempts=1,
    ):
        return True

    if plot_has_active_production(world, owned):
        run = _active_run(world, party, owned)
        recipe = RECIPES.get(run.recipe_id) if run else None
        if recipe:
            for out_m in recipe.outputs:
                hq = party_material_held(world, party, out_m, owned_plot_ids=owned_plot_ids)
                if hq >= 1:
                    _settler_sell_material(
                        world,
                        party,
                        out_m,
                        min(hq, 30),
                        owned_plot_ids=owned_plot_ids,
                    )
        return False

    chosen_rid = _pick_recipe_to_start(
        world, party, plot, owned, prefer_recipe_id=_recipe_id
    )
    if not chosen_rid:
        return False
    _ensure_recipe_inputs(world, party, chosen_rid, staging_plot_id=owned)
    r = start_production_on_plot(world, party, owned, chosen_rid)
    if not r.get("ok") or not r.get("started", True):
        return False

    recipe = RECIPES.get(chosen_rid)
    if recipe:
        for out_m in recipe.outputs:
            hq = party_material_held(world, party, out_m, owned_plot_ids=owned_plot_ids)
            if hq >= 1:
                _settler_sell_material(
                    world, party, out_m, min(hq, 24), owned_plot_ids=owned_plot_ids
                )
    return True


def _tick_one_settler(
    world: World,
    party: PartyId,
    scan: list[PlotId],
    owned_by_party: dict[PartyId, tuple[PlotId, ...]],
) -> None:
    """Lock primary business line after survey so burst steps do not re-roll a conflicting workshop."""
    locked_line: tuple[str, str] | None = None
    for burst_i in range(SETTLER_PIPELINE_BURST):
        # owned_by_party is authoritative for this tick — _settler_pipeline_step
        # mutates it in place when a claim lands, so no rescan is needed here.
        owned_ids = owned_by_party.get(party, ())
        owned = owned_ids[0] if owned_ids else None
        if owned is not None:
            pl = world.plots[owned]
            if pl.surveyed and locked_line is None:
                locked_line = _pick_settler_line(world, party, pl)
        progressed = _settler_pipeline_step(
            world,
            party,
            scan,
            owned_by_party,
            allow_secondary=(burst_i == 0),
            preferred_line=locked_line,
        )
        if not progressed:
            break
    owned_ids = owned_by_party.get(party, ())
    if owned_ids:
        _maybe_post_settler_job_opening(world, party, owned_ids[0])


def tick_settler_business(world: World) -> None:
    if world.scenario_id != "genesis":
        return
    owned_by_party = _owned_plots_by_party(world)
    _, dry_scan = _plot_scan_bundle(world)
    settlers = sorted((p for p in world.parties if str(p).startswith("settler_")), key=str)
    tick_slot = int(world.tick) % SETTLER_TICK_STRIDE
    slice_settlers = [
        s for i, s in enumerate(settlers) if i % SETTLER_TICK_STRIDE == tick_slot
    ]
    rng = world.rng(f"gen:settler_order:{world.tick}")
    order = slice_settlers.copy()
    rng.shuffle(order)
    for party in order:
        _tick_one_settler(world, party, dry_scan, owned_by_party)
