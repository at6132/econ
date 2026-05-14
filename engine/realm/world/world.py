"""World state: plots, time, Frontier scenario bootstrap."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from realm.core.ids import PartyId, PlotId
from realm.core.inventory import Inventory, MatterErr
from realm.core.ledger import Ledger, MoneyErr, party_cash_account, system_reserve_account
from realm.materials import MaterialId
from realm.production.recipes import recipe_public_list
from realm.world.biome_noise import terrain_for_cell
from realm.core.rng import make_rng
from realm.world.terrain import Terrain

if TYPE_CHECKING:  # pragma: no cover - typing only
    from realm.employment import JobOpening
    from realm.laborers import LaborerNPC
    from realm.towns import Town


def _subsurface_roll(
    rng: random.Random,
    terrain: Terrain,
    *,
    correlate: bool,
    seed: int = 0,
    x: int = 0,
    y: int = 0,
    apply_belts: bool = False,
) -> SubsurfaceRoll:
    """Terrain-correlated subsurface when ``correlate`` (stronger ore under mountains, etc.).

    Tier-2 grades are rolled here too (sulfur/saltpeter/tin/lead/phosphate/silica). They are
    visible after standard ``survey_plot`` (same as Tier-1 grades), but the *recipes* that mine
    them are locked behind discovery (assay system) — so settlers/players cannot exploit them
    until they unlock the relevant recipe via assay.
    Tier-3 grades (platinum/oil_shale/rare_earth) are rolled rare and remain hidden from the
    ``/world`` API until a deep_survey reveals them on a per-plot basis (see ``deep_surveyed``).
    """
    ir = rng.random()
    cu = rng.random()
    cl = rng.random()
    co = rng.random()
    su = rng.random()
    sp = rng.random()
    tn = rng.random()
    ld = rng.random()
    ph = rng.random()
    si = rng.random()
    pt = rng.random()
    osh = rng.random()
    re = rng.random()
    if correlate:
        if terrain == Terrain.MOUNTAIN:
            ir = min(1.0, ir * 0.38 + 0.48)
            cu = min(1.0, cu * 0.42 + 0.44)
            co = min(1.0, co * 0.45 + 0.38)
            ld = min(1.0, ld * 0.48 + 0.34)
            tn = min(1.0, tn * 0.55 + 0.18)
        elif terrain == Terrain.FOREST:
            cl = min(1.0, cl * 0.48 + 0.34)
            ph = min(1.0, ph * 0.55 + 0.18)
        elif terrain == Terrain.PLAINS:
            cl = min(1.0, cl * 0.52 + 0.28)
            ph = min(1.0, ph * 0.48 + 0.30)
            sp = min(1.0, sp * 0.58 + 0.16)
        elif terrain == Terrain.SWAMP:
            cl = min(1.0, cl * 0.46 + 0.36)
            cu = min(1.0, cu * 0.48 + 0.32)
            su = min(1.0, su * 0.46 + 0.32)
            osh = min(1.0, osh * 0.62 + 0.08)
        elif terrain == Terrain.DESERT:
            co = min(1.0, co * 0.48 + 0.36)
            sp = min(1.0, sp * 0.42 + 0.40)
            si = min(1.0, si * 0.52 + 0.28)
        elif terrain == Terrain.TUNDRA:
            ir *= 0.85
            co *= 0.85
            su = min(1.0, su * 0.55 + 0.18)
        elif terrain in (Terrain.WATER_SHALLOW, Terrain.WATER_DEEP):
            damp = 0.28
            ir *= damp
            cu *= damp
            cl *= damp
            co *= damp
            su *= damp
            sp *= damp
            tn *= damp
            ld *= damp
            ph *= damp
            si *= damp
            pt *= damp
            osh *= damp
            re *= damp
    if apply_belts:
        # Sprint 3 — Phase B.1: layered low-frequency noise creates mineral belts.
        # The bias blends with the iid roll so within a belt the average grade
        # lands at ~0.55–0.65 while neighbouring tiles still vary plot-to-plot.
        from realm.world.geo_clustering import (
            mineral_bias_clay,
            mineral_bias_coal,
            mineral_bias_copper,
            mineral_bias_iron,
        )

        bi = mineral_bias_iron(seed, x, y)
        bc = mineral_bias_coal(seed, x, y)
        bcl = mineral_bias_clay(seed, x, y)
        bcu = mineral_bias_copper(seed, x, y)
        ir = min(1.0, ir * 0.45 + bi * 0.55)
        co = min(1.0, co * 0.55 + bc * 0.45)
        cl = min(1.0, cl * 0.55 + bcl * 0.45)
        cu = min(1.0, cu * 0.55 + bcu * 0.45)
    # Tier-3 rarity gates (cliff most plots to 0 so only a few are interesting).
    pt = pt if pt > 0.97 else 0.0
    osh = osh if osh > 0.95 else 0.0
    re = re if re > 0.98 else 0.0
    # Normalize Tier-3 to the 0..1 range for the few that survive the cliff (so 0.1 gate still bites).
    if pt > 0.0:
        pt = min(1.0, (pt - 0.97) / 0.03 * 0.8 + 0.15)
    if osh > 0.0:
        osh = min(1.0, (osh - 0.95) / 0.05 * 0.8 + 0.12)
    if re > 0.0:
        re = min(1.0, (re - 0.98) / 0.02 * 0.8 + 0.18)
    return SubsurfaceRoll(
        iron_ore_grade=ir,
        copper_ore_grade=cu,
        clay_grade=cl,
        coal_grade=co,
        sulfur_grade=su,
        saltpeter_grade=sp,
        tin_grade=tn,
        lead_grade=ld,
        phosphate_grade=ph,
        silica_grade=si,
        platinum_grade=pt,
        oil_shale_grade=osh,
        rare_earth_grade=re,
    )


@dataclass
class ActiveProduction:
    run_id: str
    party: PartyId
    plot_id: PlotId
    recipe_id: str
    ticks_remaining: int
    runs_remaining: int = 0
    """Sprint 6 — Phase B: number of additional runs to queue after this one
    completes. ``0`` = one-shot (current behaviour). ``-1`` = continuous (until
    cancelled or the workshop degrades below 60% efficiency). ``> 0`` = queue
    that many more runs sequentially."""


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
    """Hidden composition until surveyed.

    Tier-1 (iron/copper/clay/coal) and Tier-2 grades (sulfur..silica) reveal on
    standard ``survey_plot``. Tier-3 (platinum/oil_shale/rare_earth) stay hidden
    from the API view until ``Plot.deep_surveyed`` flips to True.
    """

    iron_ore_grade: float  # 0..1
    copper_ore_grade: float
    clay_grade: float
    coal_grade: float
    # Tier-2 mineral grades — visible after standard survey, but extraction recipes
    # are locked behind discovery (assay system).
    sulfur_grade: float = 0.0
    saltpeter_grade: float = 0.0
    tin_grade: float = 0.0
    lead_grade: float = 0.0
    phosphate_grade: float = 0.0
    silica_grade: float = 0.0
    # Tier-3 ultra-rare grades — hidden from the API until ``deep_surveyed`` on the plot.
    platinum_grade: float = 0.0
    oil_shale_grade: float = 0.0
    rare_earth_grade: float = 0.0


@dataclass
class Plot:
    plot_id: PlotId
    x: int
    y: int
    terrain: Terrain
    owner: PartyId | None
    subsurface: SubsurfaceRoll
    surveyed: bool = False
    deep_surveyed: bool = False


@dataclass
class BusinessRecord:
    """A registered business name backing a party (Sprint 5 — Phase A).

    Registration costs a one-time fee and gives the party a public-facing
    identity that flows through every market event, contract, and feed entry
    via ``world.party_display_names``. Once registered, the business name is
    the authoritative display label.
    """

    party_id: PartyId
    business_name: str
    description: str
    registered_at_tick: int


@dataclass
class RoadSegment:
    """A road built between two adjacent plots (Sprint 6 — Phase A).

    Reduces movement cost on the edge by 50% and lets the owner collect an
    optional ad-valorem toll (0–10%) on goods value transiting the segment.
    """

    segment_id: str
    from_plot: PlotId
    to_plot: PlotId
    owner: PartyId
    built_at_tick: int
    toll_rate_pct: int = 0  # 0-10%, applied to value of goods transiting


@dataclass
class SurveyReport:
    """Tradeable survey document — knowledge as an asset (Sprint 4 — Phase A).

    A standard ``survey_plot`` always reveals the grades to the plot owner.
    When the action runs, an additional ``SurveyReport`` is created and stored
    in ``world.survey_reports``; ownership is tracked separately in
    ``world.scenario_state["report_ownership"]`` so the report can change hands
    independently of the plot.
    """

    report_id: str
    plot_id: PlotId
    conducted_by: PartyId
    conducted_at_tick: int
    grades: dict[str, float]
    survey_type: str  # "standard" | "deep"
    is_deep: bool


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
    world_feed_log: list[dict] = field(default_factory=list)  # world_feed mirror; larger cap than event_log
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
    party_recipe_books: dict[str, set[str]] = field(default_factory=dict)
    """Per-party set of recipe ids the party has discovered. Tier-1 recipes (``requires_discovery=False``)
    are always runnable regardless of book contents — only ``requires_discovery=True`` recipes need
    membership here. Keys are stringified party ids for stable serialization."""
    building_maintenance: dict[str, dict[str, int]] = field(default_factory=dict)
    """Per-building maintenance state, keyed by building instance_id. Values:
    ``{"due_at_tick": int, "missed_cycles": int, "efficiency_pct": int}``. Initialised at
    ``build_on_plot`` completion for any building with a ``maintenance_schedule`` in
    ``buildings.BUILDINGS``. Plain buildings without a schedule have no entry."""
    survey_reports: dict[str, "SurveyReport"] = field(default_factory=dict)
    """Sprint 4 — Phase A: every survey (standard or deep) creates a tradeable
    ``SurveyReport`` keyed by ``report_id``. Ownership is tracked in
    ``scenario_state["report_ownership"]`` so reports can change hands
    independently of the plot."""
    next_report_seq: int = 0
    """Monotonic id generator for ``SurveyReport.report_id`` (format: ``sr-{seq}``)."""
    intel_listings: list[dict] = field(default_factory=list)
    """Sprint 4 — Phase A: active intelligence-market listings for survey
    reports. Each row: ``{"listing_id", "seller", "report_id", "ask_price_cents",
    "listed_at_tick", "status"}``. Status: ``active`` | ``sold`` | ``cancelled``."""
    next_intel_listing_seq: int = 0
    """Monotonic id for intelligence listings (format: ``int-{seq}``)."""
    analytics_purchases: list[dict] = field(default_factory=list)
    """Sprint 4 — Phase B: log of analytics products purchased by parties.
    Each row: ``{"tick", "party", "product", "params", "cost_cents",
    "summary"}``. UI displays recent purchases under "Past purchases"."""
    business_registry: dict[str, "BusinessRecord"] = field(default_factory=dict)
    """Sprint 5 — Phase A: registered business identities keyed by party id
    str. Once registered, the business name is the authoritative
    ``party_display_names`` value for that party."""
    road_segments: list["RoadSegment"] = field(default_factory=list)
    """Sprint 6 — Phase A: built road segments connecting adjacent plot pairs.
    Each segment cuts the per-tile shipping cost on its edge by 50% and lets
    its owner collect a 0–10% ad-valorem toll on goods value transiting it."""
    next_road_segment_seq: int = 0
    """Monotonic id generator for ``RoadSegment.segment_id``."""
    laborers: dict[str, "LaborerNPC"] = field(default_factory=dict)
    """Phase 7B: live laborer NPCs keyed by ``laborer_id``. Replaces the
    static ``population_density``/``labor_pool`` maps. Each laborer has a
    real ledger account (``cash:lab:<id>``) so wage / spend transfers
    obey conservation. Mortal, needs-driven, employed by entrepreneurs."""
    towns: dict[str, "Town"] = field(default_factory=dict)
    """Phase 7C: emergent residential clusters keyed by ``town_id``. A town
    is auto-detected by ``realm.towns.detect_towns`` whenever three or more
    residences sit within 5 tiles of one another. Towns are the catchment
    for laborer spending (7D) and the anchor for store placement."""
    store_inventories: dict[str, dict[str, int]] = field(default_factory=dict)
    """Phase 7D: per-store inventory keyed by ``plot_id_str -> material_id_str -> qty``.
    The store owner stocks the building via ``stock_store``; laborer spending
    drains stock each game-day."""
    store_prices: dict[str, dict[str, int]] = field(default_factory=dict)
    """Phase 7D: per-store retail prices in cents, set by the store owner."""
    store_revenue_today: dict[str, int] = field(default_factory=dict)
    """Phase 7D: cents earned at each store on the current game-day. Reset by
    ``tick_laborer_spending`` at the day boundary so the UI can show a daily
    summary."""
    job_openings: list["JobOpening"] = field(default_factory=list)
    """Phase 7E: active job postings from entrepreneurs. ``tick_job_market``
    matches unemployed laborers to openings once per game-day; wages flow
    employer → laborer via ``tick_laborer_wages``."""

    def rng(self, purpose: str) -> random.Random:
        return make_rng(self.tick, purpose)

    def visible_survey_reports_for(self, party: PartyId) -> list["SurveyReport"]:
        """All survey reports currently owned by ``party`` (Sprint 4 — Phase A).

        The plot's own ``surveyed`` flag is unrelated — owning a report means
        the holder can see the report's grades for that plot regardless of who
        owns the plot itself.
        """
        ownership = self.scenario_state.get("report_ownership") or {}
        if not isinstance(ownership, dict):
            return []
        target = str(party)
        out: list[SurveyReport] = []
        for rid, owner in ownership.items():
            if str(owner) != target:
                continue
            report = self.survey_reports.get(str(rid))
            if report is not None:
                out.append(report)
        out.sort(key=lambda r: r.conducted_at_tick)
        return out

    def can_party_run_recipe(self, party: PartyId, recipe_id: str) -> bool:
        """Backwards-compatible recipe gate.

        - If the recipe is not authored, returns ``False`` (caller still emits a more
          specific error in ``start_production``).
        - If the recipe has ``requires_discovery=False`` → always ``True``.
        - If the recipe has ``requires_discovery=True`` → must be in the party's book.
        """
        from realm.production.recipes import RECIPES

        recipe = RECIPES.get(recipe_id)
        if recipe is None:
            return False
        if not bool(getattr(recipe, "requires_discovery", False)):
            return True
        return recipe_id in self.party_recipe_books.get(str(party), set())


def tier1_recipe_ids() -> set[str]:
    """All ``requires_discovery=False`` recipe ids — the starter book for every fresh party."""
    from realm.production.recipes import RECIPES

    return {rid for rid, r in RECIPES.items() if not bool(getattr(r, "requires_discovery", False))}


def population_density_for(world: "World", plot_id: PlotId) -> float:
    """Cached per-plot density in [0, 1]; frontier scenarios return 0.0.

    Sprint 3 — Phase B.2. Density is set up by ``bootstrap_genesis`` based on
    pop-hub coordinates and read here on demand.
    """
    d = (world.scenario_state.get("population_density") or {}).get(str(plot_id))
    if d is None:
        return 0.0
    return float(d)


def claim_cost_cents_for_plot(world: "World", plot_id: PlotId) -> int:
    """How much it costs to claim ``plot_id`` (Sprint 3 — Phase B.2)."""
    from realm.world.geo_clustering import claim_cost_cents_from_density

    return claim_cost_cents_from_density(population_density_for(world, plot_id))


def ensure_party_recipe_book(world: "World", party: PartyId) -> set[str]:
    """Seed the party's recipe book with Tier-1 recipes if not already present; return the set."""
    key = str(party)
    book = world.party_recipe_books.get(key)
    if book is None:
        book = set(tier1_recipe_ids())
        world.party_recipe_books[key] = book
    return book


def generate_plots(
    *,
    seed: int,
    width: int,
    height: int,
    correlate_subsurface: bool = False,
    terrain_fn: Any | None = None,
) -> dict[PlotId, Plot]:
    """Grid of width x height plots; terrain from coherent biome fields; subsurface rolled per plot.

    ``terrain_fn`` is an optional callable ``(seed, x, y) -> Terrain`` that overrides the
    default :func:`realm.world.biome_noise.terrain_for_cell`. Genesis bootstraps the four-island
    layout by passing a closure that wraps :func:`realm.world.biome_noise.terrain_for_genesis_island_cell`
    with the active map width/height.
    """
    plots: dict[PlotId, Plot] = {}
    pick = terrain_fn if terrain_fn is not None else terrain_for_cell
    for y in range(height):
        for x in range(width):
            pid = PlotId(f"p-{x}-{y}")
            rng = make_rng(seed, f"gen:{pid}")
            terrain = pick(seed, x, y)
            subsurface = _subsurface_roll(
                rng,
                terrain,
                correlate=correlate_subsurface,
                seed=seed,
                x=x,
                y=y,
                apply_belts=correlate_subsurface,
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


def _seed_genesis_exchange(world: World, inv: Inventory) -> None:
    """Cold-start staple liquidity — genesis allocation (same pattern as Frontier starter inventory)."""
    from realm.events.event_log import log_event
    from realm.economy.exchange import ensure_exchange_state_initialised
    from realm.economy.pricing import exchange_ask_cents
    from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
    from realm.economy.markets import place_sell_order

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
    ensure_exchange_state_initialised(world)
    # Seed prices come from the same model used by ``tick_genesis_exchange_quoting``
    # so the cold-start book is consistent with steady-state quotes (no mid-tick price jump).
    listings: list[tuple[MaterialId, int, int]] = [
        (MaterialId("grain"), 80_000, 120),
        (MaterialId("timber"), 500_000, 200),
        (MaterialId("coal"), 500_000, 140),
        (MaterialId("electricity"), 100_000, 100),
        (MaterialId("lumber"), 400_000, 200),
        (MaterialId("brick"), 400_000, 200),
        (MaterialId("stone"), 400_000, 200),
        (MaterialId("pick_axe"), 50_000, 200),
        (MaterialId("mining_pick"), 50_000, 200),
        (MaterialId("spade"), 50_000, 200),
        (MaterialId("hand_saw"), 25_000, 100),
        # Tier-2 raws — moderate stock so settlers can bootstrap chains after discovery.
        (MaterialId("sulfur_ore"), 800, 60),
        (MaterialId("saltpeter_ore"), 800, 60),
        (MaterialId("tin_ore"), 700, 50),
        (MaterialId("lead_ore"), 700, 50),
        (MaterialId("phosphate_ore"), 900, 80),
        (MaterialId("raw_silica"), 1_200, 100),
        # Processed Tier-2 (turnkey buyers can skip the chemical works for a while).
        (MaterialId("pig_iron"), 300, 30),
        (MaterialId("cast_iron"), 200, 20),
        (MaterialId("bronze_ingot"), 150, 15),
        (MaterialId("tin_ingot"), 200, 20),
        (MaterialId("lead_ingot"), 200, 20),
        # Tool components — small clearing-house presence so tool_workshop is usable on day one.
        (MaterialId("pick_head"), 300, 30),
        (MaterialId("saw_blade"), 200, 20),
        (MaterialId("drill_bit"), 100, 10),
        # Transport capital — durable, no recipe path yet (Sprint 2). Small
        # finite supply makes coastal route registration achievable on day one.
        (MaterialId("vessel"), 20, 4),
        # Sprint 3 — Phase D.1: coastal food chain liquidity.
        (MaterialId("fish"), 600, 30),
        (MaterialId("smoked_fish"), 200, 12),
    ]
    for mid, total_add, list_qty in listings:
        ad = inv.add(ex, mid, total_add)
        if isinstance(ad, MatterErr):
            raise ValueError(ad.reason)
        pr = place_sell_order(world, ex, mid, list_qty, exchange_ask_cents(mid))
        if not pr.get("ok"):
            raise ValueError(str(pr.get("reason")))
    log_event(
        world,
        "world",
        "genesis_exchange listed grain/timber/coal/electricity/lumber/brick/stone/tools (cold-start clearing).",
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
    map_layout: str = "auto",
) -> World:
    """
    Empty-world / co-founder scenario: large map, cash-only player + algorithmic settlers,
    neutral exchange listing (no Tier-1 / Tier-2 NPC bootstrap).

    Map layout (``map_layout``):
      * ``"islands"`` — four landmasses (NW / NE / SW / SE) separated by a
        cross-shaped deep-ocean gap. Phase 7A: ocean tiles are impassable by
        land movement and inter-island shipments pay ``2×`` per-tile shipping
        cost (open-ocean modifier).
      * ``"continent"`` — legacy single-continent map (whatever ``terrain_for_cell``
        produces for the seed); kept for backward compat in tiny-grid tests.
      * ``"auto"`` (default) — use ``"islands"`` if the grid is large enough
        (≥ ``GENESIS_ISLAND_MIN_WIDTH × GENESIS_ISLAND_MIN_HEIGHT``), otherwise
        fall back to ``"continent"``.

    Phase 7: there are no ``pop_hub_*`` parties anymore. Demand will be supplied
    by real ``LaborerNPC`` agents (Phase 7B) buying from entrepreneur-run stores
    (Phase 7D). For 7A the world simply has no artificial demand layer beyond
    the cold-start ``genesis_exchange`` listings — entrepreneurs trade with each
    other on the open book.

    Settlers: **all** ``settler_count`` parties are funded at tick 0 (no random partial wave).
    Optional ``settler_spawn_cap`` (≥ ``settler_count``) sets ``settler_cap``; when omitted and
    ``settler_count`` is the default 250, cap is ``GENESIS_DEFAULT_MAX_SETTLERS`` (1000) so random
    arrivals can fill in over time. Otherwise cap defaults to ``settler_count`` (no growth).
    """
    from realm.world.biome_noise import (
        genesis_island_layout_supported,
        terrain_for_genesis_island_cell,
    )
    from realm.events.event_log import log_event
    from realm.economy.market_history import record_market_snapshot

    human = PartyId("player")
    if map_layout == "auto":
        effective_layout = (
            "islands" if genesis_island_layout_supported(grid_width, grid_height) else "continent"
        )
    elif map_layout in ("islands", "continent"):
        effective_layout = map_layout
    else:
        raise ValueError(
            f"unknown map_layout {map_layout!r}; expected 'auto' | 'islands' | 'continent'"
        )
    if effective_layout == "islands":
        def _genesis_island_fn(s: int, x: int, y: int) -> Terrain:
            return terrain_for_genesis_island_cell(s, x, y, grid_width, grid_height)

        plots = generate_plots(
            seed=seed,
            width=grid_width,
            height=grid_height,
            correlate_subsurface=True,
            terrain_fn=_genesis_island_fn,
        )
    else:
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
    # Phase 7A — cache per-plot island membership (connected components of
    # non-ocean plots). Ocean plots have no entry. Used by movement.py to
    # detect inter-island shipments (2× per-tile cost) and by future phases
    # for town/island scoping.
    if effective_layout == "islands":
        from realm.world.islands import compute_plot_islands

        world.scenario_state["plot_islands"] = compute_plot_islands(world)
    else:
        world.scenario_state["plot_islands"] = {}
    # Phase 7B — seed LaborerNPCs per island. Each laborer gets a real
    # ledger account funded with the subsistence stake from the system
    # reserve. Non-island worlds (small grids in tests) get no laborer
    # population — those tests target older sprint mechanics.
    from realm.laborers import bootstrap_island_laborer_populations

    laborer_seeds = bootstrap_island_laborer_populations(world)
    if laborer_seeds:
        world.scenario_state["laborer_seeds_by_island"] = {
            str(k): int(v) for k, v in laborer_seeds.items()
        }
    # Phase 7C — seed one starting town per island so laborers have somewhere
    # to live on day 1. Residences are owned by a synthetic ``genesis_settlement``
    # placeholder so players + entrepreneur NPCs build their own on top.
    from realm.towns import seed_genesis_starting_towns

    starting_towns = seed_genesis_starting_towns(world)
    if starting_towns:
        world.scenario_state["starting_towns_by_island"] = {
            str(k): str(v) for k, v in starting_towns.items()
        }
    # Phase 7D — seed one NPC-operated general store per starting town so
    # laborers can buy food/fuel from day 1 (at a generous markup). The first
    # player to undercut these training-wheels stores captures real market
    # share.
    from realm.stores import seed_genesis_npc_stores

    npc_stores = seed_genesis_npc_stores(world)
    if npc_stores:
        world.scenario_state["starting_npc_store_plots"] = [str(p) for p in npc_stores]
    # Phase 7A: pop hubs are removed. Population density (Sprint 3 — Phase B.2)
    # no longer derives from hub coordinates; it is set to the frontier
    # baseline everywhere so the per-plot field stays well-defined for
    # legacy readers (claim cost, flipper, UI overlay) until the real
    # laborer-derived density signal lands in Phase 7B/7D.
    from realm.world.geo_clustering import POPULATION_FRONTIER_DENSITY_BASELINE

    density_map: dict[str, float] = {
        str(pid): POPULATION_FRONTIER_DENSITY_BASELINE for pid in world.plots
    }
    world.scenario_state["population_density"] = density_map
    # Phase 7A: keep regional labor pools seeded for legacy callers
    # (``hire_worker_stub`` scarcity branch); 7B replaces this entirely with
    # live LaborerNPC counts. With uniform low density every region gets the
    # ``REGION_LABOR_FRONTIER_POOL`` baseline.
    from realm.labor import bootstrap_labor_pools

    bootstrap_labor_pools(world)
    from realm.genesis_settler_names import assign_settler_display_names

    assign_settler_display_names(world, seed=seed)
    _seed_genesis_exchange(world, inv)
    _seed_tier3_character(world, inv, "genesis")
    from realm.genesis_shippers import seed_npc_shippers

    seed_npc_shippers(world)
    from realm.genesis_energy import seed_npc_energy

    seed_npc_energy(world)
    from realm.genesis_consolidator import seed_consolidator

    seed_consolidator(world)
    from realm.genesis_broker import seed_survey_broker

    seed_survey_broker(world)
    from realm.economy.analytics import seed_analytics_vendor

    seed_analytics_vendor(world)
    from realm.genesis_bank import seed_first_bank

    seed_first_bank(world)
    from realm.genesis_archetypes import seed_archetype_agents

    seed_archetype_agents(world)
    from realm.genesis_road_builders import seed_frontier_roads

    seed_frontier_roads(world)
    # Phase 7E — seed the day-1 job market so laborers have somewhere to
    # earn wages immediately. Runs AFTER every entrepreneur NPC is seated
    # (consolidator, archetypes, shippers, energy, bank) so their owned
    # plots are eligible to host openings.
    from realm.employment import seed_genesis_npc_job_market

    employment_seed = seed_genesis_npc_job_market(world)
    if employment_seed:
        world.scenario_state["starting_job_market"] = {
            str(k): int(v) for k, v in employment_seed.items()
        }
    log_event(
        world,
        "world",
        f"genesis: {n_plots} plots, {initial_n} settlers at boot (cap {settler_cap})"
        + ("; random arrivals enabled" if cycle_enabled else "")
        + ", terrain-correlated subsurface, cold-start exchange.",
    )
    record_market_snapshot(world)
    world.use_plot_output_logistics = True
    for px in list(world.parties):
        ensure_party_recipe_book(world, px)
    return world


def _seed_tier3_character(world: World, inv: Inventory, scenario_id: str) -> None:
    """Seed the scenario's named Tier-3 rival from ``realm.llm_roster``."""
    from realm.agents.llm_roster import opening_memory, persona_for_scenario

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
    from realm.economy.markets import cancel_sell_order, place_sell_order

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
    from realm.events.event_log import log_event

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
    from realm.events.event_log import log_event
    from realm.economy.markets import place_sell_order

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
    from realm.economy.market_history import record_market_snapshot

    if scenario_id == "archive":
        from realm.core.time_scale import legacy_scaled

        world.market_intel_expires_tick = max(world.market_intel_expires_tick, legacy_scaled(280))

    log_event(
        world,
        "world",
        f"{scenario_id}: {n_plots} plots, seeded markets, tier-1 loops; Tier-3 {next(iter(world.llm_agents.keys()), 'none')}.",
    )
    record_market_snapshot(world)
    for px in list(world.parties):
        ensure_party_recipe_book(world, px)
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


def _building_maintenance_view(world: World, row: dict) -> dict:
    """Public DTO for a single building's maintenance state (forwarded to API/UI)."""
    from realm.production.decay import building_maintenance_status

    return building_maintenance_status(world, row)


def world_public_dict(world: World) -> dict:
    """JSON-serializable view for API (hides unsurveyed subsurface)."""
    from realm.production.buildings import building_catalog_public
    from realm.energy import ensure_powered_plots_fresh
    from realm.economy.markets import market_book_public, market_bids_public
    from realm.production.recipe_workshops import recipe_ids_on_plot_for_owner

    powered_set = ensure_powered_plots_fresh(world)
    density_map = world.scenario_state.get("population_density") or {}
    plots_out: list[dict] = []
    for p in world.plots.values():
        density = float(density_map.get(str(p.plot_id), 0.0))
        entry: dict = {
            "id": p.plot_id,
            "x": p.x,
            "y": p.y,
            "terrain": p.terrain.value,
            "owner": p.owner,
            "surveyed": p.surveyed,
            "deep_surveyed": getattr(p, "deep_surveyed", False),
            "powered": str(p.plot_id) in powered_set,
            "population_density": density,
            "claim_cost_cents": claim_cost_cents_for_plot(world, p.plot_id),
        }
        if p.surveyed:
            sub_view: dict[str, float] = {
                "iron_ore_grade": p.subsurface.iron_ore_grade,
                "copper_ore_grade": p.subsurface.copper_ore_grade,
                "clay_grade": p.subsurface.clay_grade,
                "coal_grade": p.subsurface.coal_grade,
                "sulfur_grade": p.subsurface.sulfur_grade,
                "saltpeter_grade": p.subsurface.saltpeter_grade,
                "tin_grade": p.subsurface.tin_grade,
                "lead_grade": p.subsurface.lead_grade,
                "phosphate_grade": p.subsurface.phosphate_grade,
                "silica_grade": p.subsurface.silica_grade,
            }
            if getattr(p, "deep_surveyed", False):
                sub_view["platinum_grade"] = p.subsurface.platinum_grade
                sub_view["oil_shale_grade"] = p.subsurface.oil_shale_grade
                sub_view["rare_earth_grade"] = p.subsurface.rare_earth_grade
            entry["subsurface"] = sub_view
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
    from realm.economy.intel import FREE_MARKET_HISTORY_TICKS
    from realm.core.time_scale import TICKS_PER_GAME_DAY

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
        "world_feed_log": list(world.world_feed_log[-1500:]),
        "plot_buildings": [
            {**b, "maintenance": _building_maintenance_view(world, b)}
            for b in world.plot_buildings
        ],
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
        "party_recipe_books": {
            str(k): sorted(v) for k, v in world.party_recipe_books.items()
        },
        "intel_listings": _intel_listings_public(world),
        "player_owned_reports": _player_owned_reports_public(world, PartyId("player")),
        "analytics_purchases": list(world.analytics_purchases[-48:]),
        "business_registry": _business_registry_public(world),
        "player_accounts": _player_accounts_public(world),
        "bank_rates": _bank_rates_public(world),
        "bank_loans": _bank_loans_for_player(world),
        "bank_plot_id": world.scenario_state.get("bank_plot"),
        "road_segments": _road_segments_public(world),
        "player_price_alerts": list(
            (world.scenario_state.get("player_price_alerts") or [])
        ),
        "forward_contracts": _forward_contracts_public(world, PartyId("player")),
    }


def _player_accounts_public(world: "World") -> list[dict]:
    """Public view of the player's accounts (Sprint 5 — Phase B)."""
    try:
        from realm.sub_accounts import party_accounts_view
    except Exception:
        return []
    return party_accounts_view(world, PartyId("player"))


def _bank_rates_public(world: "World") -> dict | None:
    """Public view of the bank's posted rates for the player (Sprint 5 — Phase C)."""
    try:
        from realm.genesis_bank import FIRST_BANK_PARTY_ID, bank_rates_view
    except Exception:
        return None
    if FIRST_BANK_PARTY_ID not in world.parties:
        return None
    return bank_rates_view(world, PartyId("player"))


def _bank_loans_for_player(world: "World") -> list[dict]:
    """Active bank loans for the player (Sprint 5 — Phase C)."""
    try:
        from realm.genesis_bank import active_loans_for_borrower
    except Exception:
        return []
    return active_loans_for_borrower(world, PartyId("player"))


def _road_segments_public(world: "World") -> list[dict]:
    """Public view of every built road segment (Sprint 6 — Phase A)."""
    try:
        from realm.roads import all_roads_public
    except Exception:
        return []
    return all_roads_public(world)


def _business_registry_public(world: "World") -> dict[str, dict]:
    """Public view of registered businesses (Sprint 5 — Phase A)."""
    out: dict[str, dict] = {}
    for pid_s, rec in world.business_registry.items():
        out[str(pid_s)] = {
            "party_id": str(rec.party_id),
            "business_name": rec.business_name,
            "description": rec.description,
            "registered_at_tick": int(rec.registered_at_tick),
        }
    return out


def _intel_listings_public(world: "World") -> list[dict]:
    """Public view of active intelligence-market listings (grades hidden)."""
    out: list[dict] = []
    for row in world.intel_listings:
        if str(row.get("status", "")) != "active":
            continue
        rid = str(row.get("report_id", ""))
        report = world.survey_reports.get(rid)
        if report is None:
            continue
        out.append(
            {
                "listing_id": str(row.get("listing_id", "")),
                "seller": str(row.get("seller", "")),
                "report_id": rid,
                "plot_id": str(report.plot_id),
                "survey_type": report.survey_type,
                "is_deep": report.is_deep,
                "conducted_at_tick": int(report.conducted_at_tick),
                "ask_price_cents": int(row.get("ask_price_cents", 0)),
                "listed_at_tick": int(row.get("listed_at_tick", 0)),
            }
        )
    return out


def _player_owned_reports_public(world: "World", party: PartyId) -> list[dict]:
    """Public view of reports owned by ``party`` (grades revealed)."""
    out: list[dict] = []
    for report in world.visible_survey_reports_for(party):
        out.append(
            {
                "report_id": report.report_id,
                "plot_id": str(report.plot_id),
                "conducted_by": str(report.conducted_by),
                "conducted_at_tick": int(report.conducted_at_tick),
                "survey_type": report.survey_type,
                "is_deep": report.is_deep,
                "grades": dict(report.grades),
            }
        )
    return out


def _forward_contracts_public(world: "World", party: PartyId) -> list[dict]:
    """Forward contracts involving ``party`` as buyer or seller."""
    out: list[dict] = []
    for c in world.contracts:
        if str(c.get("kind", "")) != "forward_contract":
            continue
        if str(c.get("seller", "")) != str(party) and str(c.get("buyer", "")) != str(party):
            continue
        out.append(dict(c))
    return out


def world_summary_dict(world: "World", party: PartyId) -> dict[str, Any]:
    """Sprint 6 — Phase D.4: ultra-lightweight HUD payload.

    Intended for high-frequency polling (every ~30 ticks). Excludes the plots
    grid, full inventories, and event-log bodies — just enough for the HUD
    bar at the top of the UI.
    """
    cash_acct = str(party_cash_account(party))
    balances = world.ledger.snapshot()
    cash_cents = int(balances.get(cash_acct, 0))
    # Inventory units valued at fair-value heuristic; falls back to 0 if missing.
    try:
        from realm.economy.pricing import _FAIR_VALUE_CENTS
    except Exception:
        _FAIR_VALUE_CENTS = {}  # type: ignore[assignment]
    inv_value_cents = 0
    for mat, qty in world.inventory.stock.get(party, {}).items():
        unit = int(_FAIR_VALUE_CENTS.get(str(mat), 0))
        inv_value_cents += unit * int(qty)
    net_worth_estimate = cash_cents + inv_value_cents

    active = [
        {
            "run_id": a.run_id,
            "plot_id": str(a.plot_id),
            "recipe_id": a.recipe_id,
            "ticks_remaining": int(a.ticks_remaining),
            "runs_remaining": int(getattr(a, "runs_remaining", 0)),
        }
        for a in world.active_production
        if a.party == party
    ]

    maintenance_warning: list[dict[str, Any]] = []
    try:
        from realm.maintenance import building_efficiency_pct
        for b in world.plot_buildings:
            if b.get("party") != str(party):
                continue
            iid = str(b.get("instance_id") or "")
            if not iid:
                continue
            pct = building_efficiency_pct(world, iid)
            if pct < 100:
                maintenance_warning.append({
                    "instance_id": iid,
                    "building_id": str(b.get("building_id") or ""),
                    "plot_id": str(b.get("plot_id") or ""),
                    "efficiency_pct": int(pct),
                })
    except Exception:
        pass

    npc_msgs = world.scenario_state.get("npc_messages", []) if isinstance(world.scenario_state, dict) else []
    unread_msgs = sum(1 for m in npc_msgs if not bool(m.get("read")))
    unread_feed = len(getattr(world, "world_feed_log", []) or [])

    open_orders = sum(
        1
        for lst in world.market_asks_by_material.values()
        for o in lst
        if o.party == party
    ) + sum(
        1
        for lst in world.market_bids_by_material.values()
        for o in lst
        if o.party == party
    )

    ac_count = 0
    try:
        for c in getattr(world, "contracts", []) or []:
            if str(c.get("status") or "") != "active":
                continue
            ps = str(party)
            if (
                c.get("buyer") == ps
                or c.get("seller") == ps
                or c.get("borrower") == ps
                or c.get("lender") == ps
                or c.get("from_party") == ps
                or c.get("to_party") == ps
            ):
                ac_count += 1
    except Exception:
        ac_count = 0

    return {
        "tick": world.tick,
        "party": str(party),
        "cash": cash_cents,
        "inventory_value_estimate": inv_value_cents,
        "net_worth_estimate": net_worth_estimate,
        "active_production": active,
        "maintenance_warnings": maintenance_warning[:8],
        "unread_npc_messages": unread_msgs,
        "unread_feed_entries": unread_feed,
        "active_contracts": int(ac_count),
        "open_orders": int(open_orders),
    }


def world_compact_dict(world: World) -> dict[str, Any]:
    """Small JSON snapshot for dev/automation: player + aggregates, no full ``plots`` grid."""
    from realm.production.recipe_workshops import recipe_ids_on_plot_for_owner
    from realm.core.time_scale import TICKS_PER_GAME_DAY

    player = PartyId("player")
    balances = {str(k): v for k, v in world.ledger.snapshot().items()}
    player_acct = str(party_cash_account(player))
    bal_sample: dict[str, int] = {player_acct: balances.get(player_acct, 0)}
    for acct, cents in sorted(
        ((k, v) for k, v in balances.items() if k != player_acct),
        key=lambda kv: -abs(kv[1]),
    )[:24]:
        bal_sample[acct] = cents

    inv_player = world.inventory.stock.get(player, {})
    inv_top = [
        {"material": str(m), "qty": q}
        for m, q in sorted(inv_player.items(), key=lambda x: -x[1])[:28]
    ]

    player_plot_entries: list[dict[str, Any]] = []
    for pid, pl in world.plots.items():
        if pl.owner != player:
            continue
        player_plot_entries.append(
            {
                "id": str(pid),
                "terrain": pl.terrain.value,
                "surveyed": pl.surveyed,
                "recipe_ids": recipe_ids_on_plot_for_owner(world, pl),
            }
        )
    player_plot_entries.sort(key=lambda x: x["id"])

    hint_mountain: str | None = None
    hint_any: str | None = None
    for pl in world.plots.values():
        if pl.owner is not None:
            continue
        pid_s = str(pl.plot_id)
        if hint_any is None:
            hint_any = pid_s
        if pl.terrain == Terrain.MOUNTAIN and hint_mountain is None:
            hint_mountain = pid_s

    settler_n = sum(1 for p in world.parties if str(p).startswith("settler_"))
    ask_mats = len(world.market_asks_by_material)
    ask_lots = sum(len(v) for v in world.market_asks_by_material.values())

    def _trim_event(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        msg = out.get("message")
        if isinstance(msg, str) and len(msg) > 220:
            out["message"] = msg[:220] + "…"
        return out

    scen = world.scenario_state
    scen_preview: dict[str, Any] = {}
    if isinstance(scen, dict):
        for k in sorted(scen.keys())[:14]:
            v = scen[k]
            if isinstance(v, (int, float, bool)) or v is None:
                scen_preview[k] = v
            else:
                s = str(v)
                scen_preview[k] = s if len(s) <= 100 else s[:100] + "…"

    return {
        "compact": True,
        "seed": world.seed,
        "tick": world.tick,
        "ticks_per_game_day": TICKS_PER_GAME_DAY,
        "scenario_id": world.scenario_id,
        "plot_counts": {
            "total": len(world.plots),
            "claimed": sum(1 for pl in world.plots.values() if pl.owner is not None),
            "player_owned": len(player_plot_entries),
        },
        "claim_hint_mountain_plot_id": hint_mountain,
        "claim_hint_any_plot_id": hint_any,
        "settler_party_count": settler_n,
        "party_count": len(world.parties),
        "balances_sample_cents": bal_sample,
        "player": {
            "balance_cents": balances.get(player_acct, 0),
            "inventory_top": inv_top,
            "plots": player_plot_entries,
            "buildings": [
                {**b, "maintenance": _building_maintenance_view(world, b)}
                for b in world.plot_buildings
                if b.get("party") == str(player)
            ],
        },
        "active_production": [
            {
                "run_id": a.run_id,
                "party": str(a.party),
                "plot_id": str(a.plot_id),
                "recipe_id": a.recipe_id,
                "ticks_remaining": a.ticks_remaining,
            }
            for a in world.active_production
            if a.party == player
        ][:24],
        "in_transit": [
            {
                "shipment_id": s.shipment_id,
                "party": str(s.party),
                "material": str(s.material),
                "qty": s.qty,
                "dest_plot_id": str(s.dest_plot_id),
                "arrive_tick": s.arrive_tick,
            }
            for s in world.in_transit
            if s.party == player
        ][:16],
        "market_asks_summary": {"materials_with_asks": ask_mats, "total_lots": ask_lots},
        "event_log_tail": [_trim_event(e) for e in world.event_log[-36:]],
        "world_feed_tail": [_trim_event(e) for e in world.world_feed_log[-48:]],
        "npc_messages_tail": list(world.npc_messages_to_player[-12:]),
        "scenario_state_preview": scen_preview,
    }
