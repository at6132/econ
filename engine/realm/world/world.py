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
from realm.world.biome_noise import clear_noise_cache, terrain_for_cell
from realm.core.rng import make_rng
from realm.world.subsurface import SubsurfaceRoll, subsurface_roll
from realm.world.terrain import Terrain

# Backwards-compat alias: the worldgen helper used to live in this module.
_subsurface_roll = subsurface_roll

if TYPE_CHECKING:  # pragma: no cover - typing only
    from realm.economy.businesses import BusinessEntity
    from realm.population.employment import JobOpening
    from realm.population.laborers import LaborerNPC
    from realm.population.nascent_settlements import NascentSettlement
    from realm.population.towns import Town


# NB: the worldgen helper ``_subsurface_roll`` and the ``SubsurfaceRoll``
# dataclass used to live here. They moved to ``realm.world.subsurface`` in
# the architecture refactor; the alias at the top of this module preserves
# the legacy import path ``from realm.world.world import _subsurface_roll``.


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
    # Phase 9A — inter-island shipments record the destination dock owner so
    # the receiving fee credits coastal infrastructure on arrival. ``None``
    # for intra-island shipments (door-to-door, no port).
    dest_dock_owner: str | None = None
    inter_island: bool = False
    # Phase 10B — route the shipment is travelling along (or None for intra-
    # region). Used by ``deliver_transit`` to bump ``world.voyage_history``
    # so NPC shippers can detect heavy-traffic uncharted lanes and self-
    # register an operator.
    route_key: str | None = None
    uncharted: bool = False


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
    # Phase 9F — road condition. Decays once per game-day until the owner
    # pays maintenance; below ROAD_MIN_EFFECTIVE_BPS the segment stops
    # granting the cost discount and the owner can no longer collect tolls
    # until it's repaired (the road is gravel + ruts again).
    condition_bps: int = 10_000
    last_maintenance_tick: int = 0


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
    plot_listings: list[dict] = field(default_factory=list)
    """Phase 9B — public plot sale listings. Each row:
    ``{"listing_id", "seller", "plot_id", "ask_price_cents", "listed_at_tick",
    "status"}``. Status: ``active`` | ``sold`` | ``cancelled``."""
    next_plot_listing_seq: int = 0
    """Phase 9B — monotonic id for plot listings (format: ``plot-{seq}``)."""
    survey_authorizations: list[dict] = field(default_factory=list)
    """Phase 9B — owner authorizations for third-party (speculative) surveying.
    Each row: ``{"plot_id", "surveyor", "expires_at_tick"}``. A surveyor may
    survey a plot they don't own when an active authorization exists.
    Unauthorized speculative surveys are still allowed when the plot is
    unclaimed (no owner)."""
    liens: list[dict] = field(default_factory=list)
    """Phase 9E — outstanding debts owed by a debtor to a creditor. Created
    automatically when a supply-contract breach can't be fully covered by
    the supplier's cash on hand: the unpaid liquidated-damages portion is
    recorded here and ``tick_liens`` auto-pulls from the debtor's cash
    every tick until the lien is closed. Each row:
    ``{"lien_id", "debtor", "creditor", "amount_remaining_cents",
    "source_contract_id", "created_at_tick", "status"}`` where status is
    ``open`` | ``closed``."""
    next_lien_seq: int = 0
    """Phase 9E — monotonic id generator for liens (format: ``lien-{seq}``)."""
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
    is auto-detected by ``realm.population.towns.detect_towns`` whenever three or more
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
    landmass_id: dict[str, int] = field(default_factory=dict)
    """Phase 10A: plot-id-str → landmass id (-1 / absent for ocean). Mirrors
    ``scenario_state["plot_islands"]`` for backwards-compat with movement /
    demand callers; both are kept in sync by
    ``realm.world.landmasses.compute_landmasses``."""
    landmass_type: dict[int, str] = field(default_factory=dict)
    """Phase 10A: landmass id → ``"continent"`` | ``"island"`` | ``"islet"``.
    Used by movement.py to compute the cross-landmass shipping multiplier
    and by viability validation at bootstrap."""
    landmass_plot_count: dict[int, int] = field(default_factory=dict)
    """Phase 10A: landmass id → number of plots in that landmass."""
    voyage_history: dict[str, int] = field(default_factory=dict)
    """Phase 10B: ``route_key`` → cumulative voyage count. Updated in
    ``deliver_transit`` so NPC shippers can detect heavy traffic and register
    a regular operator on the lane."""
    businesses: dict[str, "BusinessEntity"] = field(default_factory=dict)
    """Phase 10C: registered business entities keyed by ``business_id``.
    Distinct from the legacy ``business_registry`` (which is a per-party
    name/identity record). One party may own multiple businesses; each
    business is the wrapper around a set of plots + buildings + labor that
    it organises and is publicly visible / market-tracked under."""
    next_business_seq: int = 0
    """Phase 10C: monotonic id generator for ``BusinessEntity.business_id``
    (format: ``biz-{seq:05d}``)."""
    nascent_settlements: dict[str, "NascentSettlement"] = field(default_factory=dict)
    """Phase 10F: residential clusters that haven't yet qualified as towns.
    Promoted to a town after ``resident_count >= 2`` for 3+ consecutive
    game-days."""
    next_nascent_settlement_seq: int = 0
    futures_orders: list[Any] = field(default_factory=list)
    fx_orders: list[Any] = field(default_factory=list)
    issued_currencies: dict[str, Any] = field(default_factory=dict)
    regional_advantages: dict[int, dict[str, float]] = field(default_factory=dict)

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
    clear_noise_cache()
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
        # Phase 10B — islet / short-hop craft (exchange-listed; non-continent lanes).
        (MaterialId("small_vessel"), 120, 60),
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
    grid_width: int = 192,
    grid_height: int = 144,
    settler_count: int | None = None,
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
    ``settler_count`` is ``None`` or ≥ ``GENESIS_DEFAULT_START_SETTLERS``, boot count is derived
    from landmass labor targets and cap is ``GENESIS_DEFAULT_MAX_SETTLERS`` (1000). Smaller
    explicit ``settler_count`` values default cap to that count (no growth).
    """
    from realm.world.biome_noise import (
        continental_layout_supported,
        continental_layout_terrain,
        genesis_island_layout_supported,
        terrain_for_genesis_island_cell,
    )
    from realm.events.event_log import log_event
    from realm.economy.market_history import record_market_snapshot

    human = PartyId("player")
    if map_layout == "auto":
        # Phase 10A — three-tier auto-selection. Large grids get the new
        # procedural continental layout; medium grids stay on the legacy
        # four-island layout (preserves existing tests + saves); tiny grids
        # use the single-continent ``terrain_for_cell`` fallback.
        if continental_layout_supported(grid_width, grid_height):
            effective_layout = "continental"
        elif genesis_island_layout_supported(grid_width, grid_height):
            effective_layout = "islands"
        else:
            effective_layout = "continent"
    elif map_layout in ("islands", "continent", "continental"):
        effective_layout = map_layout
    else:
        raise ValueError(
            f"unknown map_layout {map_layout!r}; expected 'auto' | 'islands' | 'continent' | 'continental'"
        )
    if effective_layout == "continental":
        def _continental_fn(s: int, x: int, y: int) -> Terrain:
            return continental_layout_terrain(s, x, y, grid_width, grid_height)

        plots = generate_plots(
            seed=seed,
            width=grid_width,
            height=grid_height,
            correlate_subsurface=True,
            terrain_fn=_continental_fn,
        )
    elif effective_layout == "islands":
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
    if effective_layout in ("islands", "continental"):
        from realm.world.landmasses import compute_landmasses

        compute_landmasses(world)
        from realm.world.regional_advantage import seed_regional_advantages

        seed_regional_advantages(world)
    else:
        world.scenario_state["plot_islands"] = {}
    if settler_count is None:
        from realm.population.landmass_density import genesis_settler_count_for_world

        settler_count = (
            genesis_settler_count_for_world(world)
            if world.landmass_plot_count
            else 250
        )
    from realm.genesis.settler_cycle import genesis_settler_population_plan

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
    gst["boot_settler_count"] = initial_n
    # Phase 7B — seed LaborerNPCs per landmass (density-scaled). Each laborer gets a real
    # ledger account funded with the subsistence stake from the system
    # reserve. Non-island worlds (small grids in tests) get no laborer
    # population — those tests target older sprint mechanics.
    from realm.population.laborers import bootstrap_island_laborer_populations

    laborer_seeds = bootstrap_island_laborer_populations(world)
    if laborer_seeds:
        world.scenario_state["laborer_seeds_by_island"] = {
            str(k): int(v) for k, v in laborer_seeds.items()
        }
    # Phase 7C — seed one starting town per island so laborers have somewhere
    # to live on day 1. Residences are owned by a synthetic ``genesis_settlement``
    # placeholder so players + entrepreneur NPCs build their own on top.
    from realm.population.towns import seed_genesis_starting_towns

    starting_towns = seed_genesis_starting_towns(world)
    if starting_towns:
        world.scenario_state["starting_towns_by_island"] = {
            str(k): str(v) for k, v in starting_towns.items()
        }
    # Phase 7D — seed one NPC-operated general store per starting town so
    # laborers can buy food/fuel from day 1 (at a generous markup). The first
    # player to undercut these training-wheels stores captures real market
    # share.
    from realm.population.stores import seed_genesis_npc_stores

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
    from realm.population.labor import bootstrap_labor_pools

    bootstrap_labor_pools(world)
    from realm.genesis.settler_names import assign_settler_display_names

    assign_settler_display_names(world, seed=seed)
    _seed_genesis_exchange(world, inv)
    _seed_tier3_character(world, inv, "genesis")
    from realm.genesis.shippers import seed_npc_shippers

    seed_npc_shippers(world)
    from realm.genesis.energy import seed_npc_energy

    seed_npc_energy(world)
    from realm.genesis.consolidator import seed_consolidator

    seed_consolidator(world)
    from realm.genesis.broker import seed_survey_broker

    seed_survey_broker(world)
    from realm.economy.analytics import seed_analytics_vendor

    seed_analytics_vendor(world)
    from realm.genesis.bank import seed_first_bank

    seed_first_bank(world)
    from realm.genesis.archetypes import seed_archetype_agents

    seed_archetype_agents(world)
    # Phase 9G — seed a residential-developer NPC per starting town. This
    # NPC plus the expanded starting-residence count (12 per island) house
    # ~40 % of laborers at bootstrap, and tick_home_builders extends that
    # over time so the homeless pool drains naturally.
    from realm.genesis.home_builders import seed_home_builders

    seed_home_builders(world)
    from realm.genesis.road_builders import seed_frontier_roads

    seed_frontier_roads(world)
    # Phase 7E — seed the day-1 job market so laborers have somewhere to
    # earn wages immediately. Runs AFTER every entrepreneur NPC is seated
    # (consolidator, archetypes, shippers, energy, bank) so their owned
    # plots are eligible to host openings.
    from realm.population.employment import seed_genesis_npc_job_market

    employment_seed = seed_genesis_npc_job_market(world)
    if employment_seed:
        world.scenario_state["starting_job_market"] = {
            str(k): int(v) for k, v in employment_seed.items()
        }
    from realm.genesis.construction_firms import seed_genesis_construction_firm

    seed_genesis_construction_firm(world)
    sjmk = world.scenario_state.get("starting_job_market")
    if isinstance(sjmk, dict):
        from realm.population.employment import active_employment_count

        sjmk["hired_immediately"] = active_employment_count(world)
    # Phase 10A — viability enforcement. After all bootstrap seeding runs,
    # ensure every continent has a baseline laborer count. Smaller-grid
    # worlds (legacy four-island) skip this step so existing tests stay
    # deterministic.
    if effective_layout == "continental":
        from realm.world.landmasses import validate_continental_viability

        viability = validate_continental_viability(world)
        if viability["laborers_added"] > 0:
            log_event(
                world,
                "world",
                f"viability: topped up {viability['laborers_added']} emergency laborers "
                f"across {viability['continents']} continents.",
            )
    log_event(
        world,
        "world",
        f"genesis: {n_plots} plots, {initial_n} settlers at boot (cap {settler_cap})"
        + ("; random arrivals enabled" if cycle_enabled else "")
        +         f", layout={effective_layout}, terrain-correlated subsurface, cold-start exchange.",
    )
    record_market_snapshot(world)
    world.use_plot_output_logistics = True
    for px in list(world.parties):
        ensure_party_recipe_book(world, px)
    ins = PartyId("frontier_insurance_co")
    world.parties.add(ins)
    world.reputation[str(ins)] = {"honored": 0, "breached": 0}
    iac = party_cash_account(ins)
    world.ledger.ensure_account(iac)
    tr_ins = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=iac,
        amount_cents=10_000_000,
    )
    if isinstance(tr_ins, MoneyErr):
        raise ValueError(tr_ins.reason)
    ensure_party_recipe_book(world, ins)
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


# ---------------------------------------------------------------------------
# Public-dict serialization (world_public_dict / world_compact_dict /
# world_summary_dict and their helpers) lives in realm.world.serialization.
# We re-export from there so `from realm.world.world import world_public_dict`
# (used by tests and a handful of legacy importers) still resolves.
# ---------------------------------------------------------------------------
from realm.world.serialization import (  # noqa: E402,F401
    _bank_loans_for_player,
    _bank_rates_public,
    _building_maintenance_view,
    _business_registry_public,
    _forward_contracts_public,
    _intel_listings_public,
    _player_accounts_public,
    _player_owned_reports_public,
    _road_segments_public,
    world_compact_dict,
    world_public_dict,
    world_summary_dict,
)
