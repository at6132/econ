"""Sprint 1 / Phase D — first-day economics, fishing gate, hub bid calibration."""

from __future__ import annotations

from realm.actions import claim_plot, start_production_on_plot, survey_plot
from realm.buildings import BUILDINGS, build_on_plot
from realm.decay import maintenance_schedule_for
from realm.genesis_pricing import (
    exchange_ask_cents,
    hub_max_bid_cents,
    producer_cost_basis_cents,
)
from realm.ids import MaterialId, PartyId, PlotId
from realm.ledger import party_cash_account, system_reserve_account
from realm.recipe_sites import recipe_allowed_on_plot
from realm.terrain import Terrain
from realm.world import SubsurfaceRoll, bootstrap_genesis, bootstrap_frontier


_TICKS_PER_GAME_DAY = 1440


def _seed_party_cash(w, party: PartyId, cents: int) -> None:
    w.ledger.ensure_account(party_cash_account(party))
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=cents,
    )


# ──────────────────────────── fishing terrain gates ────────────────────────────


def test_fishing_blocked_on_inland_plains() -> None:
    """Inland plains plot with no water neighbours: fishing rejected."""
    w = bootstrap_frontier(seed=4, grid_width=4, grid_height=4)
    # Land lock a centre plot.
    for pid in ("p-0-1", "p-2-1", "p-1-0", "p-1-2", "p-1-1"):
        w.plots[PlotId(pid)].terrain = Terrain.PLAINS
    plot = w.plots[PlotId("p-1-1")]
    ok, reason = recipe_allowed_on_plot(w, plot, "fishing")
    assert ok is False
    assert reason is not None and "coastal" in reason.lower()


def test_fishing_allowed_on_coastal_plot() -> None:
    """Plains plot adjacent to water: fishing allowed."""
    w = bootstrap_frontier(seed=4, grid_width=4, grid_height=4)
    w.plots[PlotId("p-0-0")].terrain = Terrain.PLAINS
    w.plots[PlotId("p-1-0")].terrain = Terrain.WATER_SHALLOW
    ok, _ = recipe_allowed_on_plot(w, w.plots[PlotId("p-0-0")], "fishing")
    assert ok is True


def test_fishing_full_run_on_coastal_plot() -> None:
    """End-to-end: player claims coastal plot, holds hand_saw, runs fishing once."""
    from realm.production import tick_production

    w = bootstrap_frontier(seed=4, grid_width=4, grid_height=4)
    pid = PlotId("p-0-0")
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    w.plots[pid].terrain = Terrain.PLAINS
    w.plots[PlotId("p-1-0")].terrain = Terrain.WATER_SHALLOW
    assert survey_plot(w, player, pid)["ok"] is True
    _seed_party_cash(w, player, 50_000)
    w.inventory.add(player, MaterialId("hand_saw"), 1)
    # Sprint 3 — Phase D.1: fishing now yields ``fish`` (real food material),
    # not the grain proxy used in Sprint 1.
    fish_before = w.inventory.qty(player, MaterialId("fish"))
    r = start_production_on_plot(w, player, pid, "fishing")
    assert r["ok"], r
    for _ in range(int(r["ticks_remaining"]) + 1):
        tick_production(w)
        w.tick += 1
    assert w.inventory.qty(player, MaterialId("fish")) == fish_before + 2


# ──────────────────────────── hub bid calibration ────────────────────────────


def test_hub_bids_above_cost_basis() -> None:
    """Hubs must be willing to pay at least 1.10× the producer cost basis for staples,
    so settlers undercutting the exchange always find a clearing price.

    For coal at the new markup pricing: cost_basis ≈ 67-77c (depending on labor split).
    Hub willingness = exchange_ask × 0.92. The product must clear ≥ 75c per spec."""
    w = bootstrap_genesis(seed=99, settler_count=4, grid_width=20, grid_height=14)
    for mat_str in ("coal", "timber", "grain", "iron_ore"):
        mat = MaterialId(mat_str)
        cap = hub_max_bid_cents(mat)
        basis = producer_cost_basis_cents(mat)
        assert basis is not None and basis > 0, f"{mat_str} should have a cost basis"
        assert cap >= int(basis * 1.10), (
            f"{mat_str}: hub cap {cap}¢ should be ≥ 110% of cost basis {basis}¢"
        )
    # Spec-specified hard floor for coal.
    assert hub_max_bid_cents(MaterialId("coal")) >= 75


def test_hub_bid_below_exchange_ask() -> None:
    """Hub willingness sits strictly below the exchange ask — settlers always have room."""
    w = bootstrap_genesis(seed=99, settler_count=4, grid_width=20, grid_height=14)
    for mat_str in ("coal", "timber", "grain"):
        mat = MaterialId(mat_str)
        cap = hub_max_bid_cents(mat)
        ask = exchange_ask_cents(mat, world=w)
        assert cap < ask, f"{mat_str}: hub cap {cap}¢ should be below exchange ask {ask}¢"


# ──────────────────────── first-day balance (headless) ────────────────────────


def test_coal_strategy_cash_positive_after_24_game_hours() -> None:
    """Headless: build strip_mine, mine coal, sell to a P2P-style buyer.

    The success criterion is that the player's *operating* P&L (revenue minus
    inputs minus amortised maintenance, excluding the initial capex) is
    positive over one game-day at the documented fair clearing price.

    The buyer here is a stand-in for hub demand. We deliberately do NOT run
    the full ``advance_tick`` (which would activate settler producers that
    compete with the player's listings on price). The intent of this test
    is the operator math of the player's coal strategy at the spec
    parameters; multi-agent competition is covered by the integration test.
    """
    from realm.markets import (
        cancel_party_asks_for_material,
        market_buy,
        place_sell_order,
    )
    from realm.decay import tick_building_decay, tick_building_maintenance
    from realm.production import tick_production

    w = bootstrap_genesis(seed=42, settler_count=12, grid_width=20, grid_height=14)
    player = PartyId("player")
    target = PlotId("p-0-0")
    w.plots[target].terrain = Terrain.MOUNTAIN
    w.plots[target].subsurface = SubsurfaceRoll(
        iron_ore_grade=0.3,
        copper_ore_grade=0.3,
        clay_grade=0.3,
        coal_grade=0.8,
    )
    w.plots[target].owner = player
    w.plots[target].surveyed = True

    mats = BUILDINGS["strip_mine"]["self_materials"] or {}
    for mid_s, qty in mats.items():
        w.inventory.add(player, MaterialId(mid_s), int(qty) + 2)
    _seed_party_cash(w, player, 50_000)

    r = build_on_plot(w, player, target, "strip_mine", build_mode="self_contract")
    assert r["ok"], r
    iid = r["instance_id"]
    row = next(b for b in w.plot_buildings if b.get("instance_id") == iid)
    row["completes_at_tick"] = max(0, int(w.tick) - 1)
    w.inventory.add(player, MaterialId("electricity"), 200)

    # Simulate post-withdrawal market conditions: the exchange has yielded the
    # coal book to real producers. Strip its resting coal asks and zero its
    # coal inventory so it cannot keep relisting via the iceberg/quoting paths.
    # (Direct mutation here represents the steady-state "withdrawn" mode; the
    # production code reaches the same state via the managed/reserve gates.)
    asks = w.market_asks_by_material.get("coal", [])
    w.market_asks_by_material["coal"] = [
        a for a in asks if a.party != PartyId("genesis_exchange")
    ]
    if not w.market_asks_by_material["coal"]:
        del w.market_asks_by_material["coal"]
    ex_coal = w.inventory.qty(PartyId("genesis_exchange"), MaterialId("coal"))
    if ex_coal > 0:
        w.inventory.remove(PartyId("genesis_exchange"), MaterialId("coal"), ex_coal)

    # Pay the first-time market-seller registration fee with a tiny warm-up
    # listing (placed before we capture the operating baseline). Avoids the
    # one-shot ¢2 000 setup cost dominating a single-day P&L window.
    w.inventory.add(player, MaterialId("coal"), 1)
    warm = place_sell_order(w, player, MaterialId("coal"), 1, 100)
    assert warm.get("ok"), warm

    # Sprint 3 — Phase C: production with labor_cents > 0 needs at least one
    # hired worker to run at 100 % output. Plant a no-wage placeholder hire
    # directly so the test focuses on operator-side P&L without entangling
    # with the wage flow.
    w.stub_hires.append(
        {
            "employer": str(player),
            "employee": "npc_grain_vendor",
            "wage_per_tick_cents": 0,
            "wage_interval_ticks": 1,
            "next_wage_tick": -1,
            "signing_bonus_cents": 0,
            "contract_id": "c-coal-test-hire",
            "tick": int(w.tick),
            "skill_level": 0,
            "region_id": "",
            "workers_count": 1,
        }
    )

    cash_after_build = w.ledger.balance(party_cash_account(player))

    # Stand-in for hub demand. Non-settler id so the genesis AI ignores it.
    buyer = PartyId("test_hub_buyer")
    w.parties.add(buyer)
    w.reputation.setdefault(str(buyer), {"honored": 0, "breached": 0})
    _seed_party_cash(w, buyer, 5_000_00)
    # Soak up the warm-up clip so it doesn't sit on the book at 100¢ and
    # absorb settler-priced fills later.
    market_buy(w, buyer, MaterialId("coal"), 1)

    from realm.plot_logistics import (
        ensure_inventory_from_stash,
        plot_output_qty,
        uses_plot_logistics,
    )

    started_first = False
    starts_succeeded = 0
    for _ in range(_TICKS_PER_GAME_DAY):
        active = any(a.plot_id == target for a in w.active_production)
        if not active:
            res = start_production_on_plot(w, player, target, "mine_coal")
            if res.get("ok") and res.get("started"):
                started_first = True
                starts_succeeded += 1
        tick_building_decay(w)
        tick_building_maintenance(w)
        tick_production(w)
        w.tick += 1
        # Move freshly-mined coal from plot stash to player inventory so it can
        # be listed (the genesis scenario uses plot-output logistics).
        if uses_plot_logistics(w, player):
            stash = plot_output_qty(w, target, MaterialId("coal"))
            if stash > 0:
                ensure_inventory_from_stash(
                    w, player, MaterialId("coal"),
                    w.inventory.qty(player, MaterialId("coal")) + stash,
                )
        coal_in_hand = w.inventory.qty(player, MaterialId("coal"))
        if coal_in_hand > 0:
            ask_px = 85  # post-withdrawal fair clearing price (spec §D1).
            place_sell_order(w, player, MaterialId("coal"), coal_in_hand, ask_px)
            market_buy(w, buyer, MaterialId("coal"), coal_in_hand)

    assert started_first, "expected at least one production run to start in 1 game-day"
    cash_after_day = w.ledger.balance(party_cash_account(player))
    delta = cash_after_day - cash_after_build
    # Amortised maintenance estimate: timber×2 + rope×1 over a 5-day interval ≈ 51¢/day.
    AMORTISED_MAINTENANCE_CENTS_PER_DAY = 51
    operating_pnl = delta - AMORTISED_MAINTENANCE_CENTS_PER_DAY
    assert operating_pnl > 0, (
        f"first-day operating P&L should be positive (got {operating_pnl}¢; "
        f"raw delta {delta}¢; starts={starts_succeeded})"
    )


# ───────────────────────────── conservation ─────────────────────────────────


def test_genesis_bootstrap_with_phase_a_d_conserves() -> None:
    """Full bootstrap + 50 ticks of genesis agents leaves the ledger total constant."""
    from realm.agents_genesis import tick_genesis_agents

    w = bootstrap_genesis(seed=17, settler_count=8, grid_width=18, grid_height=12)
    starting_total = w.ledger.total_cents()
    for _ in range(50):
        tick_genesis_agents(w)
        w.tick += 1
    assert w.ledger.total_cents() == starting_total
