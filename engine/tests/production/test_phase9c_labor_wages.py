"""Phase 9C — production wages flow to a real laborer (not system:reserve).

Before this slice, recipes with ``labor_cents > 0`` sank the labor cost to
``system:reserve`` whenever the producer had no stub-hire employee. That
dissolved money out of the consumer economy at every production tick.

Now ``_pay_recipe_labor`` finds a real local laborer (preferring the same
island as the plot) and credits *their* cash account, so spending power
flows into the population that actually buys food/fuel/medicine.

These tests prove:

* The labor cost lands on a LaborerNPC, not system_reserve, when one is
  housed and reachable.
* The same-island preference holds.
* Conservation: money out of employer == money into laborer.
* Frontier fallback: when the world has no housed laborers, the wage
  still sinks to ``system:reserve`` (legacy behaviour).
* The rotation index advances so the same employer doesn't keep paying
  the same person on every run.
"""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.population.laborers import (
    LaborerNPC,
    laborer_cash_account,
)
from realm.production import start_production
from realm.production.buildings import build_on_plot
from realm.world import bootstrap_frontier
from realm.world.tick import advance_tick

from stage_materials import stage_material
from turnkey_fixtures import ensure_plot_grid_power, grant_turnkey_self_materials
from plot_helpers import claimable_land_plot_id, first_land_plot_id


def _setup_sawmill_ready(seed: int = 1) -> tuple:
    """Frontier world with a player who has a sawmill ready to run."""
    w = bootstrap_frontier(seed=seed, grid_width=3, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"]
    assert survey_plot(w, player, pid)["ok"]
    grant_turnkey_self_materials(w, player, "wood_shop", plot_id=pid)
    r = build_on_plot(w, player, pid, "wood_shop", build_mode="turnkey")
    assert r["ok"], r
    # Step time until the wood_shop completes.
    while True:
        row = next(
            (
                b
                for b in w.plot_buildings
                if b.get("party") == str(player)
                and b.get("plot_id") == str(pid)
                and b.get("building_id") == "wood_shop"
            ),
            None,
        )
        assert row is not None
        ct = row.get("completes_at_tick")
        if ct is None or w.tick >= int(ct):
            break
        advance_tick(w)
    ensure_plot_grid_power(w, pid)
    stage_material(w, player, MaterialId("timber"), 40, plot_id=pid)
    return w, player, pid


def _seed_laborer(
    w,
    laborer_id: str,
    *,
    island_id: int,
    home_town: str | None = "town_0001",
    employer: PartyId | None = None,
) -> LaborerNPC:
    """Place a single laborer into ``world.laborers`` with a real cash account."""
    lab = LaborerNPC(
        laborer_id=laborer_id,
        display_name=laborer_id.title(),
        island_id=island_id,
        home_plot_id=PlotId("p-0-0"),
        home_town=home_town,
        employer=employer,
    )
    w.laborers[laborer_id] = lab
    w.ledger.ensure_account(laborer_cash_account(laborer_id))
    return lab


def test_sawmill_wage_lands_on_a_real_laborer():
    w, player, pid = _setup_sawmill_ready(seed=21)
    # Tell the world the plot is on island 0 so the locator can find a same-island laborer.
    w.scenario_state["plot_islands"] = {str(pid): 0}
    lab = _seed_laborer(w, "lab-9c-01", island_id=0)
    reserve_before = w.ledger.balance(system_reserve_account())
    lab_before = w.ledger.balance(laborer_cash_account(lab.laborer_id))
    res = start_production(w, player, pid, "sawmill")
    assert res["ok"], res
    lab_after = w.ledger.balance(laborer_cash_account(lab.laborer_id))
    reserve_after = w.ledger.balance(system_reserve_account())
    # Sawmill labor_cents = 500.
    assert lab_after - lab_before == 500, (lab_before, lab_after)
    # And system_reserve did NOT receive the wage (the leftover sink is now disabled).
    assert reserve_after == reserve_before


def test_same_island_laborer_preferred_over_other_islands():
    w, player, pid = _setup_sawmill_ready(seed=1)
    w.scenario_state["plot_islands"] = {str(pid): 1}
    # Plot is on island 1; seed two laborers: one on island 0, one on island 1.
    far = _seed_laborer(w, "lab-far", island_id=0)
    near = _seed_laborer(w, "lab-near", island_id=1)
    far_before = w.ledger.balance(laborer_cash_account(far.laborer_id))
    near_before = w.ledger.balance(laborer_cash_account(near.laborer_id))
    res = start_production(w, player, pid, "sawmill")
    assert res["ok"], res
    far_after = w.ledger.balance(laborer_cash_account(far.laborer_id))
    near_after = w.ledger.balance(laborer_cash_account(near.laborer_id))
    assert near_after - near_before == 500
    assert far_after == far_before  # far-island laborer skipped


def test_wage_routes_to_reserve_when_no_housed_laborers_exist():
    """Frontier path — bootstrap_frontier ships no laborers by design, so the
    wage still sinks to system_reserve (legacy compatibility)."""
    w, player, pid = _setup_sawmill_ready(seed=23)
    assert not w.laborers
    reserve_before = w.ledger.balance(system_reserve_account())
    res = start_production(w, player, pid, "sawmill")
    assert res["ok"], res
    reserve_after = w.ledger.balance(system_reserve_account())
    assert reserve_after - reserve_before == 500


def test_wage_conservation_money_in_equals_money_out():
    w, player, pid = _setup_sawmill_ready(seed=24)
    w.scenario_state["plot_islands"] = {str(pid): 0}
    _seed_laborer(w, "lab-c-01", island_id=0)
    total_before = w.ledger.total_cents()
    res = start_production(w, player, pid, "sawmill")
    assert res["ok"], res
    total_after = w.ledger.total_cents()
    assert total_before == total_after


def test_rotation_spreads_wages_across_multiple_local_laborers():
    """Two runs with two eligible laborers shouldn't both go to the same person.

    The second ``start_production`` would short-circuit on an active run on
    the same plot, so we advance to completion of the first run before
    starting the second.
    """
    w, player, pid = _setup_sawmill_ready(seed=25)
    w.scenario_state["plot_islands"] = {str(pid): 0}
    lab_a = _seed_laborer(w, "lab-a", island_id=0)
    lab_b = _seed_laborer(w, "lab-b", island_id=0)
    a_before = w.ledger.balance(laborer_cash_account(lab_a.laborer_id))
    b_before = w.ledger.balance(laborer_cash_account(lab_b.laborer_id))
    r1 = start_production(w, player, pid, "sawmill")
    assert r1["ok"] and r1["started"]
    while w.active_production:
        advance_tick(w)
    r2 = start_production(w, player, pid, "sawmill")
    assert r2["ok"] and r2["started"], r2
    a_after = w.ledger.balance(laborer_cash_account(lab_a.laborer_id))
    b_after = w.ledger.balance(laborer_cash_account(lab_b.laborer_id))
    # Two runs at 500c each = 1000c total, split one to each laborer via
    # the rotation index.
    assert (a_after - a_before) == 500
    assert (b_after - b_before) == 500


def test_laborer_cash_mirror_kept_in_sync():
    w, player, pid = _setup_sawmill_ready(seed=1)
    w.scenario_state["plot_islands"] = {str(pid): 0}
    lab = _seed_laborer(w, "lab-mirror", island_id=0)
    assert start_production(w, player, pid, "sawmill")["ok"]
    assert lab.cash_cents == w.ledger.balance(
        laborer_cash_account(lab.laborer_id)
    )
