"""Shared economic intelligence for any party — oracle, margins, liquidity, expansion.

Scenario-agnostic: genesis settlers, frontier NPCs, consolidators, and later LLM
agents all read the same signals. No ``scenario_id`` checks here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Final

from realm.agents.market_oracle import get_oracle
from realm.agents.settler_identity import SettlerPersonality, get_settler_personality
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.economy.pricing import exchange_ask_cents, fair_value_cents
from realm.production.recipe_sites import recipe_allowed_on_terrain, subsurface_allows_recipe
from realm.production.recipes import RECIPES, Recipe

if TYPE_CHECKING:
    from realm.world import World

# Domain ontology — material complementarity for supply chains (not scenario rules).
MATERIAL_COMPLEMENTS: Final[dict[str, frozenset[str]]] = {
    "coal": frozenset({"iron_ingot", "steel_ingot", "iron_ore", "charcoal", "lumber"}),
    "iron_ore": frozenset({"coal", "iron_ingot", "steel_ingot"}),
    "iron_ingot": frozenset({"coal", "lumber", "iron_ore"}),
    "steel_ingot": frozenset({"coal", "iron_ingot"}),
    "lumber": frozenset({"iron_ingot", "brick", "flour", "coal"}),
    "flour": frozenset({"coal", "lumber", "grain"}),
    "grain": frozenset({"coal", "lumber", "flour"}),
    "timber": frozenset({"lumber", "coal", "iron_ingot"}),
    "brick": frozenset({"lumber", "coal"}),
    "charcoal": frozenset({"iron_ingot", "steel_ingot"}),
}

BUILDING_OUTPUT_MATERIAL: Final[dict[str, str]] = {
    "strip_mine": "coal",
    "timber_yard": "timber",
    "grain_row": "grain",
    "stone_works": "stone",
    "foundry": "iron_ingot",
    "gristmill": "flour",
    "wood_shop": "lumber",
    "kiln_shed": "brick",
    "blast_furnace": "iron_ingot",
    "forge_press": "steel_ingot",
}

_MINING_GRADE_FIELDS: Final[tuple[str, ...]] = (
    "coal_grade",
    "iron_ore_grade",
    "copper_ore_grade",
    "clay_grade",
)

_DEFAULT_PERSONALITY = SettlerPersonality(
    risk_tolerance=0.5,
    specialization_loyalty=0.5,
    social_radius=2,
    patience=0.5,
    greed_index=0.5,
)


def party_personality(world: World, party: PartyId) -> SettlerPersonality:
    return get_settler_personality(world, party) or _DEFAULT_PERSONALITY


def normalize_output_material(line: str) -> str:
    if not line:
        return ""
    if line in MATERIAL_COMPLEMENTS:
        return line
    return BUILDING_OUTPUT_MATERIAL.get(line, line)


def materials_complementary(line_a: str, line_b: str) -> bool:
    mat_a = normalize_output_material(line_a)
    mat_b = normalize_output_material(line_b)
    if not mat_a or not mat_b or mat_a == mat_b:
        return False
    comp_a = MATERIAL_COMPLEMENTS.get(mat_a, frozenset())
    comp_b = MATERIAL_COMPLEMENTS.get(mat_b, frozenset())
    return mat_b in comp_a or mat_a in comp_b or bool(comp_a & {mat_b}) or bool(comp_b & {mat_a})


def recipe_margin(world: World, recipe_id: str) -> float:
    oracle = get_oracle(world)
    return float(oracle.recipe_margins.get(recipe_id, 0.0))


def plot_mining_headroom(plot) -> float:
    ss = plot.subsurface
    return max(float(getattr(ss, f, 0.0)) for f in _MINING_GRADE_FIELDS)


def subsurface_quality_for_recipe(plot, recipe: Recipe) -> float:
    if not recipe.requires_subsurface:
        return 1.0
    grades: list[float] = []
    for field, minimum in recipe.requires_subsurface:
        g = float(getattr(plot.subsurface, field, 0.0))
        if minimum <= 0:
            grades.append(g)
        else:
            grades.append(g / float(minimum))
    return min(grades) if grades else 1.0


def score_production_line(
    world: World,
    party: PartyId,
    plot,
    recipe_id: str,
    *,
    loyalty_to: str | None = None,
) -> float:
    """Expected attractiveness of a (recipe, workshop) line on this plot."""
    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        return -1e9
    if not recipe_allowed_on_terrain(plot.terrain, recipe_id):
        return -1e9
    if not subsurface_allows_recipe(plot, recipe):
        return -1e9

    personality = party_personality(world, party)
    margin = recipe_margin(world, recipe_id)
    score = margin * 8.0 + subsurface_quality_for_recipe(plot, recipe) * 2.0

    oracle = get_oracle(world)
    for out_mat in recipe.outputs:
        mid = str(out_mat)
        if mid in oracle.scarce:
            score += 1.8
        if mid in oracle.flooded:
            score -= 2.2
        depth = int(oracle.bid_depth.get(mid, 0))
        if depth <= 0:
            score -= 6.0
        elif depth < 5:
            score += 0.8
        elif depth > 50:
            score -= 0.3

    if loyalty_to and recipe_id == loyalty_to:
        score *= 0.55 + personality.specialization_loyalty * 1.45
    elif loyalty_to and recipe_id != loyalty_to:
        score *= 1.0 + (1.0 - personality.specialization_loyalty) * 0.35

    return score


def score_owned_plot(
    world: World,
    party: PartyId,
    plot_id: PlotId,
    *,
    recipe_startable: Callable[..., bool],
) -> float:
    """Rank owned plots for where to run the next production batch."""
    plot = world.plots.get(plot_id)
    if plot is None or not plot.surveyed:
        return -1e9

    best_line = -1e18
    from realm.production.recipe_workshops import recipe_ids_on_plot_for_owner

    for rid in recipe_ids_on_plot_for_owner(world, plot):
        if not recipe_startable(world, party, plot, plot_id, rid):
            continue
        line_score = score_production_line(world, party, plot, rid)
        if line_score > best_line:
            best_line = line_score

    if best_line <= -1e17:
        best_line = plot_mining_headroom(plot)

    from realm.production import plot_has_active_production

    if plot_has_active_production(world, plot_id):
        best_line += 2.5
    return best_line


def score_unclaimed_plot(world: World, plot) -> float:
    """Attractiveness of claiming an unowned plot (expansion / first claim)."""
    from realm.production.recipe_sites import terrain_allows_workshop

    if plot.owner is not None or not terrain_allows_workshop(plot.terrain):
        return -1e9

    score = plot_mining_headroom(plot) * 4.0
    oracle = get_oracle(world)
    for rid in ("grow_grain", "chop_timber", "mine_coal", "mine_iron_ore"):
        if not recipe_allowed_on_terrain(plot.terrain, rid):
            continue
        score += max(0.0, recipe_margin(world, rid)) * 3.0
        recipe = RECIPES.get(rid)
        if recipe is not None and subsurface_allows_recipe(plot, recipe):
            score += subsurface_quality_for_recipe(plot, recipe)
    for mid in ("coal", "grain", "timber", "iron_ore"):
        if mid in oracle.scarce:
            score += 0.4
    return score


def should_abandon_current_line(
    world: World,
    party: PartyId,
    plot,
    plot_id: PlotId,
    current_recipe_id: str,
    *,
    recipe_startable: Callable[..., bool],
    held_by_material: dict[str, int] | None = None,
) -> bool:
    """True when staying on the current line is dominated by alternatives on-site."""
    current_score = score_production_line(
        world, party, plot, current_recipe_id, loyalty_to=current_recipe_id
    )
    if not recipe_startable(world, party, plot, plot_id, current_recipe_id):
        current_score = -1e9

    rec = RECIPES.get(current_recipe_id)
    if rec is not None and held_by_material is not None:
        for out_mat in rec.outputs:
            held = int(held_by_material.get(str(out_mat), 0))
            if held >= 8 and output_bid_depth(world, MaterialId(str(out_mat))) <= 0:
                return True

    best_alt = current_score
    from realm.production.recipe_workshops import recipe_ids_on_plot_for_owner

    for rid in recipe_ids_on_plot_for_owner(world, plot):
        if rid == current_recipe_id:
            continue
        if not recipe_startable(world, party, plot, plot_id, rid):
            continue
        alt = score_production_line(world, party, plot, rid)
        if alt > best_alt:
            best_alt = alt

    personality = party_personality(world, party)
    switch_threshold = 1.5 + personality.specialization_loyalty * 2.5
    return best_alt > current_score + switch_threshold


def expansion_worthwhile(
    world: World,
    party: PartyId,
    home_plot_id: PlotId,
    candidate_plot_id: PlotId,
    claim_cost_cents: int,
) -> bool:
    """NPV-style gate: is a second plot worth claim + survey cost?"""
    home = world.plots.get(home_plot_id)
    candidate = world.plots.get(candidate_plot_id)
    if home is None or candidate is None:
        return False

    home_score = score_unclaimed_plot(world, home) if home.surveyed else 0.0
    cand_score = score_unclaimed_plot(world, candidate)
    if cand_score <= home_score + 0.5:
        return False

    cash = world.ledger.balance(party_cash_account(party))
    personality = party_personality(world, party)
    survey_buffer = 50_000
    overhead = int(claim_cost_cents) + survey_buffer
    risk_premium = int((1.2 - personality.risk_tolerance) * 80_000)
    return cash >= overhead + risk_premium


def party_has_completed_dock(world: World, party: PartyId) -> bool:
    tick = int(world.tick)
    for row in world.plot_buildings:
        if str(row.get("party")) != str(party):
            continue
        if str(row.get("building_id")) != "dock":
            continue
        if int(row.get("completes_at_tick", 0) or 0) <= tick:
            return True
    return False


def bulk_export_units_held(world: World, party: PartyId) -> int:
    from realm.infrastructure.plot_logistics import owned_plot_ids_sorted, party_material_held

    oids = tuple(owned_plot_ids_sorted(world, party))
    total = 0
    for mid_s in _LIQUID_STAPLE_MATS:
        total += int(party_material_held(world, party, MaterialId(mid_s), owned_plot_ids=oids))
    return total


def needs_export_dock(world: World, party: PartyId) -> bool:
    """True when bulk export inventory warrants a coastal dock the party lacks."""
    if party_has_completed_dock(world, party):
        return False
    held = bulk_export_units_held(world, party)
    if held < 10:
        return False
    if held >= 20:
        return True
    return cash_urgency(world, party) >= 0.3


def score_plot_for_export_hub(world: World, plot) -> float:
    """Claim scoring when the party needs a coastal export terminal."""
    from realm.production.recipe_sites import plot_is_coastal, terrain_allows_workshop

    base = score_unclaimed_plot(world, plot)
    if plot.owner is not None or not terrain_allows_workshop(plot.terrain):
        return base
    if plot_is_coastal(world, plot):
        return base + 5.0
    return base - 2.0


def expansion_for_export_dock(
    world: World,
    party: PartyId,
    candidate_plot_id: PlotId,
    claim_cost_cents: int,
    *,
    survey_cost_cents: int = 5_000,
    dock_turnkey_cents: int = 185_000,
) -> bool:
    """Coastal second plot to host a dock when inland mines cannot DDP ship."""
    if not needs_export_dock(world, party):
        return False
    plot = world.plots.get(candidate_plot_id)
    if plot is None:
        return False
    from realm.production.recipe_sites import plot_is_coastal

    if not plot_is_coastal(world, plot):
        return False
    cash = world.ledger.balance(party_cash_account(party))
    reserve = claim_cost_cents + survey_cost_cents + dock_turnkey_cents + 25_000
    return cash >= reserve


def recommended_sell_delivery_terms(world: World, party: PartyId, from_plot: PlotId) -> str:
    """FOB when the party cannot realistically honor seller-paid DDP from this plot."""
    from realm.economy.market_delivery import DELIVERY_DDP, DELIVERY_FOB

    plot = world.plots.get(from_plot)
    if plot is None or plot.owner != party:
        return DELIVERY_FOB
    tick = int(world.tick)
    dock_on_plot = any(
        str(b.get("party")) == str(party)
        and str(b.get("plot_id")) == str(from_plot)
        and str(b.get("building_id")) == "dock"
        and int(b.get("completes_at_tick", 0) or 0) <= tick
        for b in world.plot_buildings
    )
    if not dock_on_plot:
        return DELIVERY_FOB
    has_vessel = int(world.inventory.qty(party, MaterialId("vessel"))) >= 1
    has_small = int(world.inventory.qty(party, MaterialId("small_vessel"))) >= 1
    if not has_vessel and not has_small:
        return DELIVERY_FOB
    return DELIVERY_DDP


def operating_float_target_cents(world: World, party: PartyId) -> int:
    """Working capital target — enough for several labor cycles plus volatility buffer."""
    personality = party_personality(world, party)
    sample_labor = sorted(
        int(r.labor_cents)
        for rid, r in RECIPES.items()
        if rid in ("mine_coal", "grow_grain", "chop_timber", "mine_stone", "hand_mine_coal")
    )
    typical = sample_labor[len(sample_labor) // 2] if sample_labor else 600
    cycles = 4 + int(personality.patience * 3)
    buffer = int((1.0 - personality.patience) * 60_00) + int(personality.risk_tolerance * 40_00)
    return typical * cycles + buffer


def liquidity_reserve_cents(world: World, party: PartyId) -> int:
    """Cash buffer a producer keeps for labor + input volatility."""
    return operating_float_target_cents(world, party)


def needs_float_recovery(world: World, party: PartyId) -> bool:
    cash = world.ledger.balance(party_cash_account(party))
    return cash < operating_float_target_cents(world, party)


def max_affordable_labor_cents(world: World, party: PartyId) -> int:
    cash = world.ledger.balance(party_cash_account(party))
    reserve = min(operating_float_target_cents(world, party), 50_00)
    return max(0, cash - max(0, reserve // 4))


def can_afford_recipe_labor(world: World, party: PartyId, recipe_id: str) -> bool:
    rec = RECIPES.get(recipe_id)
    if rec is None:
        return False
    return world.ledger.balance(party_cash_account(party)) >= int(rec.labor_cents)


def _cash_only_urgency(world: World, party: PartyId) -> float:
    """Urgency from ledger cash — used where inventory pricing must not recurse."""
    cash = world.ledger.balance(party_cash_account(party))
    reserve = liquidity_reserve_cents(world, party)
    if cash >= reserve:
        return 0.0
    if reserve <= 0:
        return 1.0
    return min(1.0, (reserve - cash) / float(reserve))


def cash_urgency(world: World, party: PartyId) -> float:
    """0 = comfortable; 1 = must raise cash immediately (ledger cash only)."""
    return _cash_only_urgency(world, party)


def stockpile_liquidate_threshold(world: World, party: PartyId, *, default: int = 4) -> int:
    urgency = cash_urgency(world, party)
    if urgency >= 0.85:
        return 1
    if urgency >= 0.5:
        return 2
    return default


def listing_price_cents(
    world: World,
    party: PartyId,
    material: MaterialId,
    *,
    basis_price: int | None,
    best_bid: int | None,
) -> int:
    """Ask price from margin intent; undercuts when cash-urgent."""
    personality = party_personality(world, party)
    urgency = cash_urgency(world, party)
    ex = int(exchange_ask_cents(material, world=world))
    fair = int(fair_value_cents(material) or ex or 4)
    floor = 4

    if basis_price is not None and basis_price > 0:
        target = basis_price
    else:
        target = max(floor, int(fair * (108 + int(personality.greed_index * 20)) // 100))

    if urgency >= 0.85:
        if best_bid is not None and int(best_bid) >= floor:
            return max(floor, int(best_bid))
        return max(floor, min(target, int(ex * 92 // 100), fair))

    if urgency >= 0.5:
        ceiling = max(floor, int(ex * 96 // 100))
        if best_bid is not None:
            return max(floor, min(ceiling, max(target, int(best_bid) + 1)))
        return max(floor, min(ceiling, target))

    ceiling = max(floor, ex - 2)
    if best_bid is not None and int(best_bid) >= floor:
        return max(floor, min(ceiling, max(target, int(best_bid) + 1)))
    return max(floor, min(ceiling, target))


def tender_bid_threshold_bps(world: World, party: PartyId) -> int:
    personality = party_personality(world, party)
    # Lower bar when greedy / risk-tolerant — still must beat basis.
    base = 12_000
    adj = int((personality.greed_index - 0.5) * 2000)
    return max(10_500, min(14_500, base + adj))


def tender_bid_margin_bps(world: World, party: PartyId) -> int:
    personality = party_personality(world, party)
    base = 11_500
    adj = int((personality.greed_index - 0.5) * 1500)
    return max(10_000, min(13_500, base + adj))


def implied_basis_for_material(world: World, party: PartyId, material: MaterialId) -> int | None:
    from realm.genesis.settler_cost_basis import settler_output_basis_cents

    recorded = settler_output_basis_cents(world, party, material)
    if recorded is not None and recorded > 0:
        return int(recorded)
    oracle = get_oracle(world)
    bid = oracle.best_bid.get(str(material))
    ask = oracle.best_ask.get(str(material))
    fair = fair_value_cents(material)
    ref = bid or ask or fair or exchange_ask_cents(material, world=world)
    if ref <= 0:
        return None
    personality = party_personality(world, party)
    discount_bps = 8500 + int(personality.risk_tolerance * 1000)
    return max(4, (int(ref) * discount_bps) // 10_000)


def output_bid_depth(world: World, material: MaterialId) -> int:
    oracle = get_oracle(world)
    return int(oracle.bid_depth.get(str(material), 0))


def fire_sale_price_cents(world: World, party: PartyId, material: MaterialId) -> int:
    """Price to clear inventory when the book has no bids — undercut the market."""
    oracle = get_oracle(world)
    mid = str(material)
    fair = int(fair_value_cents(material) or 0)
    ex = int(exchange_ask_cents(material, world=world) or fair or 4)
    bid = oracle.best_bid.get(mid)
    if bid is not None and int(bid) > 0:
        return max(4, int(bid))
    book_ask = oracle.best_ask.get(mid)
    if book_ask is not None and int(book_ask) > 0:
        return max(4, int(book_ask) - 1)
    urgency = _cash_only_urgency(world, party)
    if urgency >= 0.85:
        discount = 0.70
    elif urgency >= 0.5:
        discount = 0.78
    else:
        discount = 0.88
    return max(4, min(int(fair * discount) if fair > 0 else ex - 4, ex - 2))


_LIQUID_STAPLE_MATS: Final[tuple[str, ...]] = (
    "coal",
    "grain",
    "timber",
    "lumber",
    "iron_ore",
    "iron_ingot",
    "brick",
    "stone",
    "flour",
    "clay",
    "charcoal",
)


def owned_plot_ids_for_party(world: World, party: PartyId) -> tuple[PlotId, ...]:
    from realm.infrastructure.plot_logistics import owned_plot_ids_sorted

    return tuple(owned_plot_ids_sorted(world, party))


def sellable_inventory_value_cents(
    world: World,
    party: PartyId,
    *,
    owned_plot_ids: tuple[PlotId, ...] | None = None,
) -> int:
    """Haircut fire-sale value of staple stock — balance-sheet liquidity, not cash."""
    from realm.infrastructure.plot_logistics import party_material_held

    oids = owned_plot_ids if owned_plot_ids is not None else owned_plot_ids_for_party(world, party)
    total = 0
    for mid_s in _LIQUID_STAPLE_MATS:
        mid = MaterialId(mid_s)
        qty = int(party_material_held(world, party, mid, owned_plot_ids=oids))
        if qty <= 0:
            continue
        qty = min(qty, 48)
        px = fire_sale_price_cents(world, party, mid)
        total += (qty * px * 65) // 100
    return total


def liquid_working_capital_cents(
    world: World,
    party: PartyId,
    *,
    owned_plot_ids: tuple[PlotId, ...] | None = None,
) -> int:
    """Cash plus conservative liquidation value of sellable inventory."""
    cash = world.ledger.balance(party_cash_account(party))
    return cash + sellable_inventory_value_cents(
        world, party, owned_plot_ids=owned_plot_ids
    )


def evaluate_staple_purchase(
    world: World,
    buyer: PartyId,
    material: MaterialId,
    *,
    target_stock: int,
    current_stock: int,
) -> tuple[int, int] | None:
    """Returns (max_price_per_unit_cents, qty) when restocking is economically sensible."""
    deficit = int(target_stock) - int(current_stock)
    oracle = get_oracle(world)
    mid = str(material)
    fair = int(fair_value_cents(material) or 0)
    ref = oracle.best_bid.get(mid) or oracle.best_ask.get(mid) or fair
    if ref is None or int(ref) <= 0:
        ref = exchange_ask_cents(material, world=world)
    ref = int(ref)

    best_ask = oracle.best_ask.get(mid)
    bargain_ceiling = max(4, (fair * 82 // 100) if fair > 0 else (ref * 82 // 100))
    if deficit <= 0 and best_ask is not None and int(best_ask) <= bargain_ceiling:
        ask = int(best_ask)
        if fair > 0 and ask <= fair * 50 // 100:
            deficit = max(8, min(24, target_stock))
        else:
            deficit = max(2, min(8, max(2, target_stock // 4)))

    if deficit <= 0:
        return None

    personality = party_personality(world, buyer)
    markup_bps = 10_500 if mid in oracle.scarce else 10_200
    markup_bps += int((personality.risk_tolerance - 0.5) * 800)
    ceiling = max(4, (ref * markup_bps) // 10_000)
    if best_ask is not None:
        ceiling = max(ceiling, int(best_ask))

    qty = min(deficit, max(2, target_stock // 3))
    min_cash = max(300, ceiling * qty)
    cash = world.ledger.balance(party_cash_account(buyer))
    if cash < min_cash:
        return None
    if cash < ceiling * qty:
        qty = max(1, cash // max(1, ceiling))
    if qty <= 0:
        return None
    return ceiling, qty


def partnership_combined_cash_floor(world: World, party_a: PartyId, party_b: PartyId) -> int:
    """Minimum pooled cash for partnership — scales with risk, not scenario."""
    pa = party_personality(world, party_a)
    pb = party_personality(world, party_b)
    combined_risk = (pa.risk_tolerance + pb.risk_tolerance) / 2.0
    base = 120_000 if combined_risk >= 0.55 else 180_000
    return int(base * (0.85 + combined_risk * 0.25))


def partnership_proposer_min_cash(world: World, party: PartyId) -> int:
    personality = party_personality(world, party)
    return int(60_000 + (1.0 - personality.risk_tolerance) * 60_000)
