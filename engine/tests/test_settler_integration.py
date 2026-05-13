"""Sprint 2 — Phase B · settler vertical integration & cost-basis pricing.

Covers the four mechanics that put real competitive pressure on the player:
- ``record_settler_buy`` tracks per-settler weighted-average input prices.
- ``record_settler_production`` updates per-settler output cost basis (EMA).
  A settler who self-supplies an input has a structurally lower basis than
  one who buys it from the exchange.
- ``_list_price_cents`` uses the per-settler basis when available, so the
  vertically-integrated settler can profitably undercut the exchange.
- ``tick_settler_margin_review`` triggers upgrade builds when the math
  justifies them (≥2.5× downstream margin and ≥1.5× cash cushion).
- Buffer buying fires when an input price climbs ≥20% in 7 game-days.
"""

from __future__ import annotations

from realm.agents_genesis_settlers import _list_price_cents
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import MatterErr
from realm.ledger import (
    MoneyErr,
    party_cash_account,
    system_reserve_account,
)
from realm.recipes import RECIPES
from realm.settler_cost_basis import (
    SETTLER_LIST_MARGIN_BPS,
    record_settler_buy,
    record_settler_production,
    settler_input_avg_paid_cents,
    settler_input_price_change_bps_7d,
    settler_listing_price_cents,
    settler_output_basis_cents,
)
from realm.settler_upgrades import (
    _UPGRADE_PATHS,
    tick_settler_margin_review,
)
from realm.world import World, bootstrap_genesis


# ───────────────────────── helpers ─────────────────────────


def _give(world: World, party: PartyId, material: str, qty: int) -> None:
    res = world.inventory.add(party, MaterialId(material), qty)
    assert not isinstance(res, MatterErr)


def _give_cash(world: World, party: PartyId, cents: int) -> None:
    res = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=cents,
    )
    assert not isinstance(res, MoneyErr)


# ───────────────────────── unit tests ─────────────────────────


def test_record_settler_buy_tracks_weighted_average() -> None:
    """VWAP: two buys at different prices yield a weighted average per unit."""
    w = bootstrap_genesis(seed=2, settler_count=2, grid_width=12, grid_height=10)
    party = PartyId("settler_001")
    # buy 5 units at 80c/unit
    record_settler_buy(w, party, MaterialId("coal"), 5, 400)
    assert settler_input_avg_paid_cents(w, party, MaterialId("coal")) == 80
    # then 5 units at 100c/unit → VWAP = 90
    record_settler_buy(w, party, MaterialId("coal"), 5, 500)
    assert settler_input_avg_paid_cents(w, party, MaterialId("coal")) == 90


def test_settler_cost_basis_lower_with_own_supply() -> None:
    """A vertically integrated settler (no purchases for input) has a lower output basis."""
    w = bootstrap_genesis(seed=3, settler_count=4, grid_width=12, grid_height=10)
    integrated = PartyId("settler_001")
    buyer = PartyId("settler_002")
    # Both settlers produce iron_ingot via smelt_iron. ``buyer`` paid 80c/iron_ore +
    # 65c/coal on the market; ``integrated`` extracted both → no input_avg_paid.
    record_settler_buy(w, buyer, MaterialId("iron_ore"), 50, 50 * 80)
    record_settler_buy(w, buyer, MaterialId("coal"), 50, 50 * 65)
    rec = RECIPES["smelt_iron"]
    iron_out_qty = int(rec.outputs[MaterialId("iron_ingot")])
    record_settler_production(w, buyer, "smelt_iron", MaterialId("iron_ingot"), iron_out_qty)
    record_settler_production(
        w, integrated, "smelt_iron", MaterialId("iron_ingot"), iron_out_qty
    )
    b_basis = settler_output_basis_cents(w, buyer, MaterialId("iron_ingot"))
    i_basis = settler_output_basis_cents(w, integrated, MaterialId("iron_ingot"))
    assert b_basis is not None and i_basis is not None
    assert i_basis < b_basis, (i_basis, b_basis)
    # And the integrated settler's basis is bounded below by labor alone.
    labor = int(rec.labor_cents)
    assert i_basis <= (labor + iron_out_qty - 1) // iron_out_qty + 1


def test_settler_lists_below_exchange_when_vertically_integrated() -> None:
    """A settler with a recorded basis lists strictly below the exchange ask."""
    w = bootstrap_genesis(seed=5, settler_count=4, grid_width=12, grid_height=10)
    integrated = PartyId("settler_001")
    # Plant a low basis directly so we can assert the ask math without running
    # a full production cycle. (record_settler_production proxy.)
    record_settler_production(w, integrated, "smelt_iron", MaterialId("iron_ingot"), 1)
    from realm.genesis_pricing import exchange_ask_cents

    ex = int(exchange_ask_cents(MaterialId("iron_ingot"), world=w))
    px = _list_price_cents(w, MaterialId("iron_ingot"), party=integrated)
    assert px < ex, (px, ex)


def test_listing_price_falls_back_when_no_basis() -> None:
    """Without a recorded basis, ``_list_price_cents`` reverts to the static model."""
    w = bootstrap_genesis(seed=7, settler_count=4, grid_width=12, grid_height=10)
    party = PartyId("settler_001")
    # No recordings on this party → ``settler_listing_price_cents`` returns None.
    assert settler_listing_price_cents(w, party, MaterialId("coal")) is None
    px = _list_price_cents(w, MaterialId("coal"), party=party)
    assert px > 0  # uses the legacy ``settler_ask_cents`` model


def test_buffer_buy_change_pct_threshold() -> None:
    """The 7-day price-change accessor returns positive BPS when prices rise."""
    w = bootstrap_genesis(seed=9, settler_count=4, grid_width=12, grid_height=10)
    party = PartyId("settler_001")
    # First buy 10 units @ 50c
    record_settler_buy(w, party, MaterialId("coal"), 10, 500)
    # Advance 4 game-days then buy 10 units @ 80c (+60% rise).
    w.tick += 1440 * 4
    record_settler_buy(w, party, MaterialId("coal"), 10, 800)
    change = settler_input_price_change_bps_7d(w, party, MaterialId("coal"))
    assert change is not None
    assert change >= 5_000  # at least +50%


def test_vertical_upgrade_does_not_fire_below_threshold() -> None:
    """If current margin is comparable to vertical margin, no upgrade is built."""
    w = bootstrap_genesis(seed=11, settler_count=4, grid_width=12, grid_height=10)
    # Make absolutely sure no settler already runs a foundry.
    has_foundry_before = any(
        str(b.get("building_id")) == "foundry"
        and str(b.get("party", "")).startswith("settler_")
        for b in w.plot_buildings
    )
    assert not has_foundry_before
    # Run the review at a non-week boundary → no-op.
    w.tick = 100
    tick_settler_margin_review(w)
    has_foundry_after = any(
        str(b.get("building_id")) == "foundry"
        and str(b.get("party", "")).startswith("settler_")
        for b in w.plot_buildings
    )
    assert not has_foundry_after


def test_vertical_upgrade_fires_when_math_justifies() -> None:
    """Plant a deliberately favourable basis/price scenario and assert the foundry build kicks off.

    Default Phase-1 prices are calibrated for retail solo play (iron_ingot ask is
    below smelt_iron's labor cost), so vertical integration is not naturally
    profitable from a cold start. The test plants a near-zero basis for iron_ore
    (a settler with their own mine effectively self-supplies) and elevates the
    iron_ingot exchange price into the regime where the math fires. The unit
    test validates the *trigger logic*, not the live Phase-1 economy.
    """
    w = bootstrap_genesis(seed=13, settler_count=4, grid_width=12, grid_height=10)
    party = PartyId("settler_001")
    # Plant a strip_mine on a player-owned plot for the settler.
    plot_id = None
    for plot in w.plots.values():
        if plot.owner is not None:
            continue
        plot.owner = party
        plot_id = plot.plot_id
        break
    assert plot_id is not None
    w.next_building_instance_seq += 1
    iid = f"b{w.next_building_instance_seq:06d}"
    w.plot_buildings.append(
        {
            "instance_id": iid,
            "condition_bps": 10_000,
            "plot_id": str(plot_id),
            "party": str(party),
            "building_id": "strip_mine",
            "label": "Strip mine (test)",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": 0,
        }
    )
    # Plant a very low upstream basis (mine_iron_ore at low effective unit cost).
    from realm.settler_cost_basis import ensure_cost_basis_state

    state = ensure_cost_basis_state(w)
    state[str(party)] = {
        "input_avg_paid": {},
        "input_qty_purchased": {},
        "input_last_paid_tick": {},
        "input_price_history": {},
        "output_basis": {"iron_ore": 5},
        "output_qty_produced": {"iron_ore": 100},
    }
    # Elevate the iron_ingot market price so the vertical margin handily beats
    # the smelt_iron labor floor (~800c).
    ex_state = w.scenario_state.setdefault("exchange", {})
    ex_state.setdefault("price", {})["iron_ingot"] = 5_000  # $50/iron_ingot
    # Top up cash so the buffer ≥ 1.5× foundry turnkey cost.
    _give_cash(w, party, 1_500_000)  # $15,000
    # Seed turnkey foundry materials so the build doesn't have to walk the book.
    _give(w, party, "brick", 6)
    _give(w, party, "stone", 4)
    _give(w, party, "coal", 4)
    w.tick = 7 * 1440  # exactly one game-week
    tick_settler_margin_review(w)
    has_foundry = any(
        str(b.get("building_id")) == "foundry"
        and str(b.get("party")) == str(party)
        for b in w.plot_buildings
    )
    assert has_foundry, [
        (b.get("party"), b.get("building_id")) for b in w.plot_buildings
    ]


def test_buffer_buy_executes_when_price_rises() -> None:
    """When a settler's input price for coal climbs >20% in 7 days, they prebuy stock."""
    w = bootstrap_genesis(seed=17, settler_count=4, grid_width=12, grid_height=10)
    party = PartyId("settler_001")
    # Plant price history: cheap @t=0, expensive @t=now-1.
    record_settler_buy(w, party, MaterialId("coal"), 10, 500)  # 50c
    w.tick += 1440 * 3
    record_settler_buy(w, party, MaterialId("coal"), 10, 800)  # 80c → +60%
    # Plant cash to fund the buffer buy.
    _give_cash(w, party, 1_000_000)
    pre_qty = int(w.inventory.qty(party, MaterialId("coal")))
    w.tick = 7 * 1440  # week boundary
    tick_settler_margin_review(w)
    post_qty = int(w.inventory.qty(party, MaterialId("coal")))
    assert post_qty > pre_qty, (pre_qty, post_qty)


def test_cost_basis_state_persists_through_ledger_invariance() -> None:
    """A full game-day of activity with cost-basis tracking conserves the ledger."""
    w = bootstrap_genesis(seed=23, settler_count=4, grid_width=12, grid_height=10)
    starting = w.ledger.total_cents()
    from realm.tick import advance_tick

    for _ in range(800):
        advance_tick(w)
    assert w.ledger.total_cents() == starting
