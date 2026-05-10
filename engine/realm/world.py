"""World state: plots, time, Frontier scenario bootstrap."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from realm.ids import PartyId, PlotId
from realm.inventory import Inventory, MatterErr
from realm.ledger import Ledger, MoneyErr, party_cash_account, system_reserve_account
from realm.materials import MaterialId
from realm.recipes import recipe_public_list
from realm.biome_noise import terrain_for_cell
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
    market_bids_by_material: dict[str, list[Any]] = field(default_factory=dict)
    next_order_seq: int = 0
    reputation: dict[str, dict[str, int]] = field(default_factory=dict)
    contracts: list[dict] = field(default_factory=list)
    next_contract_seq: int = 0
    event_log: list[dict] = field(default_factory=list)
    plot_buildings: list[dict] = field(default_factory=list)
    stub_hires: list[dict] = field(default_factory=list)
    market_history: list[dict] = field(default_factory=list)
    p2p_idempotency: dict[str, dict] = field(default_factory=dict)
    scenario_id: str = "frontier"
    """Active scenario name (Frontier, bootstrapper, speculator, cartel)."""
    market_intel_expires_tick: int = 0
    """While ``world.tick < market_intel_expires_tick``, API exposes full ``market_history``; else a short free window."""
    next_building_instance_seq: int = 0
    """Monotonic id generator for ``plot_buildings[].instance_id``."""

    def rng(self, purpose: str) -> random.Random:
        return make_rng(self.tick, purpose)


def generate_plots(*, seed: int, width: int, height: int) -> dict[PlotId, Plot]:
    """Grid of width x height plots; terrain from coherent biome fields, subsurface iid per plot."""
    plots: dict[PlotId, Plot] = {}
    for y in range(height):
        for x in range(width):
            pid = PlotId(f"p-{x}-{y}")
            rng = make_rng(seed, f"gen:{pid}")
            terrain = terrain_for_cell(seed, x, y)
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


def _seed_tier2_agents(
    world: World,
    inv: Inventory,
    timber_merchant: PartyId,
    clay_vendor: PartyId,
    player: PartyId,
) -> None:
    """Phase 2 optimizing NPCs — cash from system reserve; inventory seed from Tier-1 buffers or player (1 coal for t2_coal_spread)."""
    specs = (
        ("t2_ele_bidstack", 42_000),
        ("t2_lumber_bid", 55_000),
        ("t2_timber_spread", 35_000),
        ("t2_clay_sweep", 38_000),
        ("t2_coal_spread", 32_000),
    )
    for name, cents in specs:
        pid = PartyId(name)
        world.parties.add(pid)
        world.reputation[str(pid)] = {"honored": 0, "breached": 0}
        acct = party_cash_account(pid)
        world.ledger.ensure_account(acct)
        tr = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=cents,
        )
        if isinstance(tr, MoneyErr):
            raise ValueError(tr.reason)
    ts = PartyId("t2_timber_spread")
    tr_t = inv.transfer(
        material=MaterialId("timber"),
        qty=1,
        from_party=timber_merchant,
        to_party=ts,
    )
    if isinstance(tr_t, MatterErr):
        raise ValueError(tr_t.reason)
    cs = PartyId("t2_clay_sweep")
    tr_c = inv.transfer(
        material=MaterialId("clay"),
        qty=1,
        from_party=clay_vendor,
        to_party=cs,
    )
    if isinstance(tr_c, MatterErr):
        raise ValueError(tr_c.reason)
    tcoal = PartyId("t2_coal_spread")
    tr_coal = inv.transfer(
        material=MaterialId("coal"),
        qty=1,
        from_party=player,
        to_party=tcoal,
    )
    if isinstance(tr_coal, MatterErr):
        raise ValueError(tr_coal.reason)


def _seed_cartel_grain_overlay(
    world: World,
    inv: Inventory,
    grain_vendor: PartyId,
    vendor_grain_order_id: str,
) -> None:
    """
    Cartel scenario: cancel the bulk vendor grain clip, split stock between the incumbent
    vendor and a synthetic pool that lists at a premium (information / rationing pressure).
    """
    from realm.markets import cancel_sell_order, place_sell_order

    if not vendor_grain_order_id:
        raise ValueError("cartel overlay requires vendor grain order id")
    cr = cancel_sell_order(world, grain_vendor, vendor_grain_order_id)
    if not cr.get("ok"):
        raise ValueError(str(cr.get("reason")))
    cell = PartyId("cartel_grain_cell")
    world.parties.add(cell)
    world.reputation[str(cell)] = {"honored": 0, "breached": 0}
    tr = inv.transfer(
        material=MaterialId("grain"),
        qty=6,
        from_party=grain_vendor,
        to_party=cell,
    )
    if isinstance(tr, MatterErr):
        raise ValueError(tr.reason)
    pr_hi = place_sell_order(world, cell, MaterialId("grain"), 6, 168)
    if not pr_hi.get("ok"):
        raise ValueError(str(pr_hi.get("reason")))
    pr_lo = place_sell_order(world, grain_vendor, MaterialId("grain"), 4, 118)
    if not pr_lo.get("ok"):
        raise ValueError(str(pr_lo.get("reason")))
    from realm.event_log import log_event

    log_event(
        world,
        "world",
        "Cartel overlay: split grain listings (pool @ premium vs vendor remainder).",
    )


def bootstrap_frontier(
    *,
    seed: int,
    grid_width: int = 48,
    grid_height: int = 36,
    starting_cash_cents: int = 1_000_000,  # $10,000.00
    system_reserve_cents: int = 100_000_000_000,  # $1B — unallocated pool
    scenario_id: str = "frontier",
) -> World:
    """
    Frontier scenario: one human player party + plots + funded economy.

    Phase 1: single human party `player` — AI parties added with agents module.
    """
    human = PartyId("player")
    plots = generate_plots(seed=seed, width=grid_width, height=grid_height)
    n_plots = len(plots)
    ledger = Ledger()
    inv = Inventory()
    world = World(
        seed=seed,
        tick=0,
        plots=plots,
        ledger=ledger,
        inventory=inv,
        parties={human},
        scenario_id=scenario_id,
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
    from realm.event_log import log_event
    from realm.markets import place_sell_order

    pr = place_sell_order(world, vendor, MaterialId("grain"), 10, 120)
    if not pr.get("ok"):
        raise ValueError(str(pr.get("reason")))
    grain_vendor_ask_id = str(pr.get("order_id", ""))
    timber_merch = PartyId("t1_timber_merchant")
    lumber_buyer = PartyId("t1_lumber_buyer")
    world.parties.add(timber_merch)
    world.parties.add(lumber_buyer)
    world.reputation[str(timber_merch)] = {"honored": 0, "breached": 0}
    world.reputation[str(lumber_buyer)] = {"honored": 0, "breached": 0}
    tr_tm = inv.transfer(
        material=MaterialId("timber"), qty=4, from_party=human, to_party=timber_merch
    )
    if isinstance(tr_tm, MatterErr):
        raise ValueError(tr_tm.reason)
    lb_cash = party_cash_account(lumber_buyer)
    world.ledger.ensure_account(lb_cash)
    tr_lb = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=lb_cash,
        amount_cents=50_000,
    )
    if isinstance(tr_lb, MoneyErr):
        raise ValueError(tr_lb.reason)
    pr2 = place_sell_order(world, timber_merch, MaterialId("timber"), 2, 68)
    if not pr2.get("ok"):
        raise ValueError(str(pr2.get("reason")))
    coal_v = PartyId("t1_coal_vendor")
    clay_v = PartyId("t1_clay_vendor")
    elec_b = PartyId("t1_electricity_buyer")
    for px in (coal_v, clay_v, elec_b):
        world.parties.add(px)
        world.reputation[str(px)] = {"honored": 0, "breached": 0}
    tr_coal = inv.transfer(material=MaterialId("coal"), qty=3, from_party=human, to_party=coal_v)
    if isinstance(tr_coal, MatterErr):
        raise ValueError(tr_coal.reason)
    tr_clay = inv.transfer(material=MaterialId("clay"), qty=3, from_party=human, to_party=clay_v)
    if isinstance(tr_clay, MatterErr):
        raise ValueError(tr_clay.reason)
    eb_cash = party_cash_account(elec_b)
    world.ledger.ensure_account(eb_cash)
    tr_eb = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=eb_cash,
        amount_cents=30_000,
    )
    if isinstance(tr_eb, MoneyErr):
        raise ValueError(tr_eb.reason)
    pr_coal = place_sell_order(world, coal_v, MaterialId("coal"), 2, 38)
    if not pr_coal.get("ok"):
        raise ValueError(str(pr_coal.get("reason")))
    pr_clay = place_sell_order(world, clay_v, MaterialId("clay"), 2, 54)
    if not pr_clay.get("ok"):
        raise ValueError(str(pr_clay.get("reason")))
    if scenario_id == "cartel":
        _seed_cartel_grain_overlay(world, inv, vendor, grain_vendor_ask_id)
    _seed_tier2_agents(world, inv, timber_merch, clay_v, human)
    from realm.market_history import record_market_snapshot

    log_event(
        world,
        "world",
        f"Frontier ready: {n_plots} plots, seeded commodity books, six tier-1 agent loops.",
    )
    record_market_snapshot(world)
    for p in world.parties:
        inv.ensure_party_bucket(p)
    return world


def bootstrap_by_scenario(*, seed: int, scenario: str) -> World:
    """Named Phase 2 scenarios — same engine, different starting parameters."""
    sid = scenario.strip().lower()
    if sid in ("frontier", "cartel"):
        return bootstrap_frontier(seed=seed, scenario_id=sid)
    if sid == "bootstrapper":
        return bootstrap_frontier(
            seed=seed,
            grid_width=32,
            grid_height=24,
            starting_cash_cents=500_000,
            scenario_id="bootstrapper",
        )
    if sid == "speculator":
        return bootstrap_frontier(
            seed=seed,
            grid_width=40,
            grid_height=30,
            starting_cash_cents=2_000_000,
            scenario_id="speculator",
        )
    raise ValueError(f"unknown scenario: {scenario!r}")


def world_public_dict(world: World) -> dict:
    """JSON-serializable view for API (hides unsurveyed subsurface)."""
    from realm.buildings import building_catalog_public
    from realm.markets import market_book_public, market_bids_public
    from realm.recipe_workshops import recipe_ids_on_plot_for_owner

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
            entry["recipe_ids"] = recipe_ids_on_plot_for_owner(world, p)
        plots_out.append(entry)
    balances = {str(k): v for k, v in world.ledger.snapshot().items()}
    inv = {
        str(party): {str(m): q for m, q in mats.items()}
        for party, mats in world.inventory.snapshot().items()
    }
    from realm.actions import hire_catalog_public
    from realm.intel import FREE_MARKET_HISTORY_TICKS

    intel_active = world.tick < world.market_intel_expires_tick
    hist = world.market_history
    if intel_active:
        market_hist_out = list(hist)
    else:
        market_hist_out = list(hist[-FREE_MARKET_HISTORY_TICKS:])

    return {
        "seed": world.seed,
        "tick": world.tick,
        "scenario_id": world.scenario_id,
        "market_intel_expires_tick": world.market_intel_expires_tick,
        "market_intel_active": intel_active,
        "market_history_free_window_ticks": FREE_MARKET_HISTORY_TICKS,
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
        "market_bids": market_bids_public(world),
        "reputation": dict(world.reputation),
        "contracts": list(world.contracts),
        "event_log": list(world.event_log[-120:]),
        "plot_buildings": list(world.plot_buildings),
        "stub_hires": list(world.stub_hires),
        "building_catalog": building_catalog_public(),
        "market_history": market_hist_out[-160:],
        "hire_catalog": hire_catalog_public(),
    }
