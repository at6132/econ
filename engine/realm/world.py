"""World state: plots, time, Frontier scenario bootstrap."""

from __future__ import annotations

from dataclasses import dataclass, field
from realm.ids import PartyId, PlotId
from realm.inventory import Inventory
from realm.ledger import Ledger, MoneyErr, party_cash_account, system_reserve_account
from realm.inventory import MatterErr
from realm.materials import MaterialId
from realm.recipes import recipe_public_list
from realm.rng import make_rng
from realm.terrain import Terrain


@dataclass
class ActiveProduction:
    run_id: str
    party: PartyId
    plot_id: PlotId
    recipe_id: str
    ticks_remaining: int


@dataclass(frozen=True, slots=True)
class SubsurfaceRoll:
    """Hidden composition until surveyed (Phase 1 stub — rolled at gen, not visible to UI)."""

    iron_ore_grade: float  # 0..1
    copper_ore_grade: float
    clay_grade: float
    coal_grade: float


@dataclass
class Plot:
    plot_id: PlotId
    x: int
    y: int
    terrain: Terrain
    owner: PartyId | None
    subsurface: SubsurfaceRoll
    surveyed: bool = False


@dataclass
class World:
    """Authoritative world blob — mutate only through actions / tick pipeline."""

    seed: int
    tick: int
    plots: dict[PlotId, Plot]
    ledger: Ledger
    inventory: Inventory
    parties: set[PartyId] = field(default_factory=set)
    active_production: list[ActiveProduction] = field(default_factory=list)
    next_production_seq: int = 0

    def rng(self, purpose: str):
        return make_rng(self.tick, purpose)


def generate_plots(*, seed: int, width: int, height: int) -> dict[PlotId, Plot]:
    """Grid of width x height plots; terrain + subsurface from deterministic RNG."""
    plots: dict[PlotId, Plot] = {}
    for y in range(height):
        for x in range(width):
            pid = PlotId(f"p-{x}-{y}")
            rng = make_rng(seed, f"gen:{pid}")
            terrain_roll = rng.random()
            if terrain_roll < 0.08:
                terrain = Terrain.WATER_DEEP if rng.random() < 0.5 else Terrain.WATER_SHALLOW
            elif terrain_roll < 0.22:
                terrain = Terrain.FOREST
            elif terrain_roll < 0.35:
                terrain = Terrain.MOUNTAIN
            elif terrain_roll < 0.5:
                terrain = Terrain.PLAINS
            elif terrain_roll < 0.65:
                terrain = Terrain.DESERT
            elif terrain_roll < 0.8:
                terrain = Terrain.SWAMP
            else:
                terrain = Terrain.TUNDRA
            subsurface = SubsurfaceRoll(
                iron_ore_grade=rng.random(),
                copper_ore_grade=rng.random(),
                clay_grade=rng.random(),
                coal_grade=rng.random(),
            )
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=terrain,
                owner=None,
                subsurface=subsurface,
            )
    return plots


def bootstrap_frontier(
    *,
    seed: int,
    grid_width: int = 8,
    grid_height: int = 5,
    starting_cash_cents: int = 1_000_000,  # $10,000.00
    system_reserve_cents: int = 100_000_000_000,  # $1B — unallocated pool
) -> World:
    """
    Frontier scenario: one human player party + plots + funded economy.

    Phase 1: single human party `player` — AI parties added with agents module.
    """
    human = PartyId("player")
    plots = generate_plots(seed=seed, width=grid_width, height=grid_height)
    ledger = Ledger()
    inv = Inventory()
    world = World(
        seed=seed,
        tick=0,
        plots=plots,
        ledger=ledger,
        inventory=inv,
        parties={human},
    )
    res = world.ledger.seed_system_reserve(system_reserve_cents)
    if isinstance(res, MoneyErr):
        raise ValueError(res.reason)
    pcash = party_cash_account(human)
    world.ledger.ensure_account(pcash)
    tr = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=pcash,
        amount_cents=starting_cash_cents,
    )
    if isinstance(tr, MoneyErr):
        raise ValueError(tr.reason)
    # Frontier starter stock so production loop is testable without cheats
    _starter = (
        (MaterialId("timber"), 12),
        (MaterialId("coal"), 12),
        (MaterialId("electricity"), 8),
        (MaterialId("iron_ore"), 6),
        (MaterialId("copper_ore"), 6),
        (MaterialId("clay"), 10),
        (MaterialId("grain"), 8),
    )
    for mid, qty in _starter:
        ad = inv.add(human, mid, qty)
        if isinstance(ad, MatterErr):
            raise ValueError(ad.reason)
    return world


def world_public_dict(world: World) -> dict:
    """JSON-serializable view for API (hides unsurveyed subsurface)."""
    plots_out: list[dict] = []
    for p in world.plots.values():
        entry: dict = {
            "id": p.plot_id,
            "x": p.x,
            "y": p.y,
            "terrain": p.terrain.value,
            "owner": p.owner,
            "surveyed": p.surveyed,
        }
        if p.surveyed:
            entry["subsurface"] = {
                "iron_ore_grade": p.subsurface.iron_ore_grade,
                "copper_ore_grade": p.subsurface.copper_ore_grade,
                "clay_grade": p.subsurface.clay_grade,
                "coal_grade": p.subsurface.coal_grade,
            }
        plots_out.append(entry)
    balances = {str(k): v for k, v in world.ledger.snapshot().items()}
    inv = {
        str(party): {str(m): q for m, q in mats.items()}
        for party, mats in world.inventory.snapshot().items()
    }
    return {
        "seed": world.seed,
        "tick": world.tick,
        "plots": plots_out,
        "balances_cents": balances,
        "inventory": inv,
        "parties": [str(x) for x in world.parties],
        "recipes": recipe_public_list(),
        "active_production": [
            {
                "run_id": a.run_id,
                "party": str(a.party),
                "plot_id": str(a.plot_id),
                "recipe_id": a.recipe_id,
                "ticks_remaining": a.ticks_remaining,
            }
            for a in world.active_production
        ],
    }
