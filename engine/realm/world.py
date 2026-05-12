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

# Population-side wallets (genesis scenario) — funded from system reserve at bootstrap.
GENESIS_POP_HUB_CASH_CENTS = 5_000_000  # $50,000 each — aggregate staple demand.


def _subsurface_roll(rng: random.Random, terrain: Terrain, *, correlate: bool) -> SubsurfaceRoll:
    """Terrain-correlated subsurface when ``correlate`` (stronger ore under mountains, etc.)."""
    ir = rng.random()
    cu = rng.random()
    cl = rng.random()
    co = rng.random()
    if correlate:
        if terrain == Terrain.MOUNTAIN:
            ir = min(1.0, ir * 0.38 + 0.48)
            cu = min(1.0, cu * 0.42 + 0.44)
            co = min(1.0, co * 0.45 + 0.38)
        elif terrain == Terrain.FOREST:
            cl = min(1.0, cl * 0.48 + 0.34)
        elif terrain == Terrain.PLAINS:
            cl = min(1.0, cl * 0.52 + 0.28)
        elif terrain == Terrain.SWAMP:
            cl = min(1.0, cl * 0.46 + 0.36)
            cu = min(1.0, cu * 0.48 + 0.32)
        elif terrain == Terrain.DESERT:
            co = min(1.0, co * 0.48 + 0.36)
        elif terrain == Terrain.TUNDRA:
            ir *= 0.85
            co *= 0.85
        elif terrain in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP):
            damp = 0.28
            ir *= damp
            cu *= damp
            cl *= damp
            co *= damp
    return SubsurfaceRoll(
        iron_ore_grade=ir,
        copper_ore_grade=cu,
        clay_grade=cl,
        coal_grade=co,
    )


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
    from_plot_id: PlotId | None = None


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
    llm_agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Tier-3 LLM-controlled parties: party id str → persona fields + ``memory_summary``, ``last_plan_tick``."""
    npc_messages_to_player: list[dict[str, Any]] = field(default_factory=list)
    """Short NPC→human lines (tick, from_party, display_name, text); append-only, trimmed in code."""
    llm_session_cost_micro_usd: int = 0
    """Cumulative estimated API spend for this save/session (micro-dollars; 1 = $1e-6)."""
    llm_session_input_tokens: int = 0
    llm_session_output_tokens: int = 0
    deployed_lua_sources: dict[str, str] = field(default_factory=dict)
    """Party id str → last deployed Lua source (Phase 4 staging; persisted in snapshots)."""
    party_display_names: dict[str, str] = field(default_factory=dict)
    """Optional UI labels keyed by party id str (e.g. Genesis settler personas)."""
    scenario_state: dict[str, Any] = field(default_factory=dict)
    """Scenario-scoped scratch (Genesis digest deltas, scripted NPC flags). Persisted in snapshots."""
    use_plot_output_logistics: bool = False
    """When True, player outputs and inbound shipments stage on plot-local stock (harvest → party inventory)."""
    plot_output_stock: dict[str, dict[str, int]] = field(default_factory=dict)
    """Per-plot staged materials: plot id str → material id str → qty (not in party inventory yet)."""
    market_seller_registered: set[str] = field(default_factory=set)
    """Genesis: composite keys ``party|material`` after one-time clearinghouse seller registration fee is paid."""

    def rng(self, purpose: str) -> random.Random:
        return make_rng(self.tick, purpose)


def generate_plots(
    *,
    seed: int,
    width: int,
    height: int,
    correlate_subsurface: bool = False,
) -> dict[PlotId, Plot]:
    """Grid of width x height plots; terrain from coherent biome fields; subsurface rolled per plot."""
    plots: dict[PlotId, Plot] = {}
    for y in range(height):
        for x in range(width):
            pid = PlotId(f"p-{x}-{y}")
            rng = make_rng(seed, f"gen:{pid}")
            terrain = terrain_for_cell(seed, x, y)
            subsurface = _subsurface_roll(rng, terrain, correlate=correlate_subsurface)
            plots[pid] = Plot(
                plot_id=pid,
                x=x,
                y=y,
                terrain=terrain,
                owner=None,
                subsurface=subsurface,
            )
    return plots


def _seed_genesis_exchange(world: World, inv: Inventory) -> None:
    """Cold-start staple liquidity — genesis allocation (same pattern as Frontier starter inventory)."""
    from realm.event_log import log_event
    from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
    from realm.markets import place_sell_order

    ex = PartyId("genesis_exchange")
    world.parties.add(ex)
    world.reputation[str(ex)] = {"honored": 0, "breached": 0}
    ex_cash = party_cash_account(ex)
    world.ledger.ensure_account(ex_cash)
    trx = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=ex_cash,
        amount_cents=25_000_000,
    )
    if isinstance(trx, MoneyErr):
        raise ValueError(trx.reason)
    listings: list[tuple[MaterialId, int, int, int]] = [
        (MaterialId("grain"), 80_000, 120, 128),
        (MaterialId("timber"), 50_000, 80, 96),
        (MaterialId("coal"), 500_000, 140, 62),
        (MaterialId("electricity"), 100_000, 100, 52),
    ]
    for mid, total_add, list_qty, price in listings:
        ad = inv.add(ex, mid, total_add)
        if isinstance(ad, MatterErr):
            raise ValueError(ad.reason)
        pr = place_sell_order(world, ex, mid, list_qty, price)
        if not pr.get("ok"):
            raise ValueError(str(pr.get("reason")))
    log_event(
        world,
        "world",
        "genesis_exchange listed grain/timber/coal/electricity (cold-start clearing).",
    )


def bootstrap_genesis(
    *,
    seed: int,
    grid_width: int = 96,
    grid_height: int = 72,
    settler_count: int = 250,
    settler_spawn_cap: int | None = None,
    starting_cash_cents: int = 1_000_000,
    system_reserve_cents: int = 100_000_000_000,
) -> World:
    """
    Empty-world / co-founder scenario: large map, cash-only player + algorithmic settlers,
    population demand wallets, neutral exchange listing (no Tier-1 / Tier-2 NPC bootstrap).

    Settlers: **all** ``settler_count`` parties are funded at tick 0 (no random partial wave).
    Optional ``settler_spawn_cap`` (≥ ``settler_count``) sets ``settler_cap``; when omitted and
    ``settler_count`` is the default 250, cap is ``GENESIS_DEFAULT_MAX_SETTLERS`` (500) so random
    arrivals can fill in over time. Otherwise cap defaults to ``settler_count`` (no growth).
    """
    from realm.event_log import log_event
    from realm.market_history import record_market_snapshot

    human = PartyId("player")
    plots = generate_plots(
        seed=seed,
        width=grid_width,
        height=grid_height,
        correlate_subsurface=True,
    )
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
        scenario_id="genesis",
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
    world.reputation[str(human)] = {"honored": 0, "breached": 0}
    from realm.genesis_settler_cycle import genesis_settler_population_plan

    initial_n, settler_cap, cycle_enabled = genesis_settler_population_plan(
        settler_count=settler_count,
        settler_spawn_cap=settler_spawn_cap,
    )
    for i in range(1, initial_n + 1):
        sid = PartyId(f"settler_{i:03d}")
        world.parties.add(sid)
        world.reputation[str(sid)] = {"honored": 0, "breached": 0}
        acct = party_cash_account(sid)
        world.ledger.ensure_account(acct)
        trs = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=starting_cash_cents,
        )
        if isinstance(trs, MoneyErr):
            raise ValueError(trs.reason)
    gst = world.scenario_state.setdefault("genesis", {})
    gst["settler_cycle_enabled"] = cycle_enabled
    gst["settler_cap"] = settler_cap
    gst["next_settler_seq"] = initial_n + 1
    gst["starting_settler_cents"] = starting_cash_cents
    gst["broke_ticks"] = {}
    for name in ("pop_hub_e", "pop_hub_w"):
        ph = PartyId(name)
        world.parties.add(ph)
        world.reputation[str(ph)] = {"honored": 0, "breached": 0}
        acct = party_cash_account(ph)
        world.ledger.ensure_account(acct)
        trp = world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=GENESIS_POP_HUB_CASH_CENTS,
        )
        if isinstance(trp, MoneyErr):
            raise ValueError(trp.reason)
    from realm.genesis_settler_names import assign_settler_display_names

    assign_settler_display_names(world, seed=seed)
    _seed_genesis_exchange(world, inv)
    _seed_tier3_character(world, inv, "genesis")
    log_event(
        world,
        "world",
        f"genesis: {n_plots} plots, {initial_n} settlers at boot (cap {settler_cap})"
        + ("; random arrivals enabled" if cycle_enabled else "")
        + ", terrain-correlated subsurface, cold-start exchange.",
    )
    record_market_snapshot(world)
    world.use_plot_output_logistics = True
    return world


def _seed_tier3_character(world: World, inv: Inventory, scenario_id: str) -> None:
    """Seed the scenario's named Tier-3 rival from ``realm.llm_roster``."""
    from realm.llm_roster import opening_memory, persona_for_scenario

    try:
        persona = persona_for_scenario(scenario_id)
    except KeyError:
        return
    pid = PartyId(persona.party_id)
    world.parties.add(pid)
    world.reputation[str(pid)] = {"honored": 0, "breached": 0}
    cash_acct = party_cash_account(pid)
    world.ledger.ensure_account(cash_acct)
    tr = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=cash_acct,
        amount_cents=persona.starting_cash_cents,
    )
    if isinstance(tr, MoneyErr):
        raise ValueError(tr.reason)
    for mid_s, qty in persona.starter_inventory:
        mid = MaterialId(mid_s)
        ad = inv.add(pid, mid, qty)
        if isinstance(ad, MatterErr):
            raise ValueError(ad.reason)
    blob: dict[str, object] = {
        "display_name": persona.display_name,
        "system_prompt": persona.system_prompt,
        "memory_summary": opening_memory(scenario_id, persona.display_name),
        "last_plan_tick": -10**9,
        "scenario_spawn": scenario_id,
    }
    if scenario_id == "genesis":
        blob["genesis_opener_sent"] = False
    world.llm_agents[str(pid)] = blob


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
    _seed_tier3_character(world, inv, scenario_id)
    from realm.market_history import record_market_snapshot

    if scenario_id == "archive":
        from realm.time_scale import legacy_scaled

        world.market_intel_expires_tick = max(world.market_intel_expires_tick, legacy_scaled(280))

    log_event(
        world,
        "world",
        f"{scenario_id}: {n_plots} plots, seeded markets, tier-1 loops; Tier-3 {next(iter(world.llm_agents.keys()), 'none')}.",
    )
    record_market_snapshot(world)
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
            starting_cash_cents=485_000,
            scenario_id="bootstrapper",
        )
    if sid == "speculator":
        return bootstrap_frontier(
            seed=seed,
            grid_width=40,
            grid_height=30,
            starting_cash_cents=2_050_000,
            scenario_id="speculator",
        )
    if sid == "millrace":
        return bootstrap_frontier(
            seed=seed,
            grid_width=42,
            grid_height=28,
            starting_cash_cents=975_000,
            scenario_id="millrace",
        )
    if sid == "archive":
        return bootstrap_frontier(
            seed=seed,
            grid_width=48,
            grid_height=36,
            starting_cash_cents=1_080_000,
            scenario_id="archive",
        )
    if sid == "genesis":
        return bootstrap_genesis(seed=seed)
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
        if world.use_plot_output_logistics and p.owner is not None:
            entry["output_stock"] = dict(world.plot_output_stock.get(str(p.plot_id), {}))
        plots_out.append(entry)
    balances = {str(k): v for k, v in world.ledger.snapshot().items()}
    inv = {
        str(party): {str(m): q for m, q in mats.items()}
        for party, mats in world.inventory.snapshot().items()
    }
    from realm.actions import hire_catalog_public
    from realm.intel import FREE_MARKET_HISTORY_TICKS
    from realm.time_scale import TICKS_PER_GAME_DAY

    intel_active = world.tick < world.market_intel_expires_tick
    hist = world.market_history
    if intel_active:
        market_hist_out = list(hist)
    else:
        market_hist_out = list(hist[-FREE_MARKET_HISTORY_TICKS:])

    return {
        "seed": world.seed,
        "tick": world.tick,
        "ticks_per_game_day": TICKS_PER_GAME_DAY,
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
                "shipment_id": s.shipment_id,
                "party": str(s.party),
                "material": str(s.material),
                "qty": s.qty,
                "from_plot_id": str(s.from_plot_id) if s.from_plot_id else None,
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
        "llm_agents": [
            {
                "party": pid,
                "display_name": blob.get("display_name", pid),
                "memory_summary": str(blob.get("memory_summary", ""))[:800],
            }
            for pid, blob in sorted(world.llm_agents.items(), key=lambda x: x[0])
        ],
        "npc_messages": list(world.npc_messages_to_player[-48:]),
        "party_display_names": dict(world.party_display_names),
        "llm_session_cost_micro_usd": world.llm_session_cost_micro_usd,
        "llm_session_input_tokens": world.llm_session_input_tokens,
        "llm_session_output_tokens": world.llm_session_output_tokens,
        "deployed_lua": {
            k: {
                "chars": len(v),
                "lines": v.count("\n") + (1 if v else 0),
            }
            for k, v in sorted(world.deployed_lua_sources.items(), key=lambda x: x[0])
        },
    }
