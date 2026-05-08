"""World state: plots, time, Frontier scenario bootstrap."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from realm.ids import PartyId, PlotId
from realm.inventory import Inventory, MatterErr
from realm.ledger import Ledger, MoneyErr, party_cash_account, system_reserve_account
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


@dataclass
class InTransit:
    shipment_id: str
    party: PartyId
    material: MaterialId
    qty: int
    dest_plot_id: PlotId
    arrive_tick: int


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
    in_transit: list[InTransit] = field(default_factory=list)
    next_shipment_seq: int = 0
    market_asks_by_material: dict[str, list[Any]] = field(default_factory=dict)
    next_order_seq: int = 0
    reputation: dict[str, dict[str, int]] = field(default_factory=dict)
    contracts: list[dict] = field(default_factory=list)
    next_contract_seq: int = 0

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
        (MaterialId("grain"), 20),
    )
    for mid, qty in _starter:
        ad = inv.add(human, mid, qty)
        if isinstance(ad, MatterErr):
            raise ValueError(ad.reason)
    world.reputation[str(human)] = {"honored": 0, "breached": 0}
    vendor = PartyId("npc_grain_vendor")
    consumer = PartyId("t1_consumer")
    world.parties.add(vendor)
    world.parties.add(consumer)
    world.reputation[str(vendor)] = {"honored": 0, "breached": 0}
    world.reputation[str(consumer)] = {"honored": 0, "breached": 0}
    tr_g = inv.transfer(material=MaterialId("grain"), qty=10, from_party=human, to_party=vendor)
    if isinstance(tr_g, MatterErr):
        raise ValueError(tr_g.reason)
    cc = party_cash_account(consumer)
    world.ledger.ensure_account(cc)
    tr_c = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=cc,
        amount_cents=25_000,
    )
    if isinstance(tr_c, MoneyErr):
        raise ValueError(tr_c.reason)
    from realm.markets import place_sell_order

    pr = place_sell_order(world, vendor, MaterialId("grain"), 10, 120)
    if not pr.get("ok"):
        raise ValueError(str(pr.get("reason")))
    return world


def world_public_dict(world: World) -> dict:
    """JSON-serializable view for API (hides unsurveyed subsurface)."""
    from realm.markets import market_book_public

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
        "in_transit": [
            {
                "id": s.shipment_id,
                "party": str(s.party),
                "material": str(s.material),
                "qty": s.qty,
                "dest_plot_id": str(s.dest_plot_id),
                "arrive_tick": s.arrive_tick,
            }
            for s in world.in_transit
        ],
        "market_asks": market_book_public(world),
        "reputation": dict(world.reputation),
        "contracts": list(world.contracts),
    }
