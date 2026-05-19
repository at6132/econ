"""
Settler archetypes — five personality types that shape decision-making.

Archetypes are assigned at genesis from the settler's party_id hash.
They never change. They influence (not override) the existing decision logic
by adjusting weights in _recipe_rank_score and directing capital allocation.
"""

from __future__ import annotations

import zlib
from enum import Enum

from realm.core.ids import PartyId, PlotId
from realm.events.event_log import log_event
from realm.world import World


class Archetype(str, Enum):
    MINER = "miner"
    PROCESSOR = "processor"
    MERCHANT = "merchant"
    LANDLORD = "landlord"
    RESEARCHER = "researcher"


_WEIGHTS: list[tuple[Archetype, int]] = [
    (Archetype.MINER, 30),
    (Archetype.PROCESSOR, 25),
    (Archetype.MERCHANT, 20),
    (Archetype.LANDLORD, 15),
    (Archetype.RESEARCHER, 10),
]
_CUMULATIVE: list[tuple[Archetype, int]] = []
_acc = 0
for _arch, _w in _WEIGHTS:
    _acc += _w
    _CUMULATIVE.append((_arch, _acc))


def get_archetype(party: PartyId) -> Archetype:
    """Deterministic archetype from party_id. Same party = same archetype always."""
    h = zlib.crc32(str(party).encode("utf-8")) % 100
    for arch, threshold in _CUMULATIVE:
        if h < threshold:
            return arch
    return Archetype.MINER


ARCHETYPE_RECIPE_BONUS: dict[Archetype, set[str]] = {
    Archetype.MINER: {
        "mine_coal",
        "mine_iron_ore",
        "mine_copper_ore",
        "mine_lead_ore",
        "mine_sulfur_ore",
        "mine_phosphate_ore",
        "dig_clay",
        "hand_mine_coal",
        "hand_dig_clay",
    },
    Archetype.PROCESSOR: {
        "smelt_iron",
        "smelt_pig_iron",
        "forge_pick_head",
        "forge_saw_blade",
        "mill_flour",
        "bake_bread",
        "fire_brick",
        "fire_clay_pot",
        "charcoal_burn",
        "glass_blow",
    },
    Archetype.MERCHANT: {
        "sell_grain",
        "sell_coal",
        "sell_lumber",
        "sell_medicine",
    },
    Archetype.LANDLORD: set(),
    Archetype.RESEARCHER: {
        "run_experiment",
        "assay_mineral",
        "deep_assay",
    },
}

ARCHETYPE_RECIPE_AVOID: dict[Archetype, set[str]] = {
    Archetype.MINER: {"run_experiment", "bake_bread"},
    Archetype.PROCESSOR: {"mine_coal", "mine_iron_ore"},
    Archetype.MERCHANT: {"run_experiment", "smelt_iron"},
    Archetype.LANDLORD: set(),
    Archetype.RESEARCHER: {"mine_coal", "mine_iron_ore"},
}

ARCHETYPE_PREFERRED_BUILDINGS: dict[Archetype, list[str]] = {
    Archetype.MINER: ["strip_mine", "power_shed", "assay_lab"],
    Archetype.PROCESSOR: ["foundry", "wood_shop", "gristmill", "power_shed"],
    Archetype.MERCHANT: ["store", "waystation"],
    Archetype.LANDLORD: ["residence", "store"],
    Archetype.RESEARCHER: ["laboratory", "assay_lab", "power_shed"],
}

ARCHETYPE_EXPANSION_THRESHOLD: dict[Archetype, int] = {
    Archetype.MINER: 250_000,
    Archetype.PROCESSOR: 400_000,
    Archetype.MERCHANT: 150_000,
    Archetype.LANDLORD: 200_000,
    Archetype.RESEARCHER: 500_000,
}


def maybe_create_discovery_blueprint(
    world: World,
    party: PartyId,
    discovered_recipe_id: str,
) -> None:
    """RESEARCHER settlers register a licensable blueprint for a discovered recipe."""
    if get_archetype(party) != Archetype.RESEARCHER:
        return

    from realm.actions.blueprint_actions import create_blueprint
    from realm.agents.market_oracle import get_oracle
    from realm.production.recipes import RECIPES

    rec = RECIPES.get(discovered_recipe_id)
    if rec is None:
        return

    for bp in world.blueprints.values():
        if (
            discovered_recipe_id in bp.enabled_recipe_ids
            and bp.creator_party == str(party)
        ):
            return

    n_inputs = len(rec.inputs)
    footprint_w = min(6, max(2, n_inputs + 1))
    footprint_h = min(5, max(2, n_inputs))

    oracle = get_oracle(world)
    daily_output_value = sum(
        oracle.best_ask.get(str(mat), 100) * int(qty) for mat, qty in rec.outputs.items()
    )
    license_fee = max(500, int(daily_output_value * 0.05))

    bp_name = f"{rec.display_name} Workshop"

    r = create_blueprint(
        world=world,
        creator=party,
        name=bp_name,
        description=f"Enables {discovered_recipe_id}. Discovered by {party}.",
        footprint_w=footprint_w,
        footprint_h=footprint_h,
        construction_materials={str(m): int(q) for m, q in rec.inputs.items()},
        construction_labor_cents=rec.labor_cents * 10,
        construction_ticks=720,
        enabled_recipe_ids=[discovered_recipe_id],
        maintenance_interval_ticks=14_400,
        maintenance_materials={},
        maintenance_grace_ticks=1440,
        is_public=True,
        license_fee_cents=license_fee,
        category="custom",
        terrain_requirements=[],
        requires_coastal=False,
        requires_power=False,
    )
    if r.get("ok"):
        log_event(
            world,
            "researcher_blueprint_created",
            f"{party} created blueprint '{bp_name}' from discovery, "
            f"license fee: {license_fee}c",
            party=str(party),
            blueprint_id=r.get("blueprint_id"),
            recipe_id=discovered_recipe_id,
        )


_STARTER_BENCH_PAIRS: list[tuple[str, str]] = [
    ("iron_ore", "coal"),
    ("copper_ore", "coal"),
    ("clay", "coal"),
    ("timber", "coal"),
    ("sand", "coal"),
    ("iron_ore", "copper_ore"),
    ("clay", "sand"),
    ("grain", "clay"),
    ("limestone", "clay"),
]


def tick_researcher_experiments(world: World) -> None:
    """Once per game-week, RESEARCHER settlers with labs run bench reactions."""
    if int(world.tick) % 10_080 != 0:
        return

    from realm.actions.science_actions import run_laboratory_bench

    researchers = [
        p
        for p in world.parties
        if str(p).startswith("settler_") and get_archetype(p) == Archetype.RESEARCHER
    ]

    for party in researchers:
        lab_plot = _find_lab_plot(world, party)
        if lab_plot is None:
            continue
        pair = _pick_bench_materials(world, party)
        if pair is None:
            continue
        mat_a, mat_b = pair
        run_laboratory_bench(world, party, lab_plot, mat_a, mat_b)


def _find_lab_plot(world: World, party: PartyId) -> PlotId | None:
    for b in world.plot_buildings:
        if str(b.get("party")) != str(party):
            continue
        if str(b.get("building_id")) != "laboratory":
            continue
        if int(b.get("completes_at_tick", 0)) > int(world.tick):
            continue
        return PlotId(str(b.get("plot_id", "")))
    return None


def _pick_bench_materials(world: World, party: PartyId) -> tuple[str, str] | None:
    from realm.core.ids import MaterialId
    from realm.science.chemistry import try_reaction

    book = world.party_recipe_books.get(str(party), set())
    for mat_a, mat_b in _STARTER_BENCH_PAIRS:
        key = f"{mat_a}+{mat_b}"
        if key in book:
            continue
        if try_reaction(mat_a, mat_b) is None:
            continue
        if world.inventory.qty(party, MaterialId(mat_a)) < 1:
            continue
        if world.inventory.qty(party, MaterialId(mat_b)) < 1:
            continue
        return (mat_a, mat_b)
    return None
