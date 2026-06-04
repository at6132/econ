"""Labor competition — poaching, unrest, training."""

from __future__ import annotations

from realm.agents.settler_identity import assign_settler_personality
from realm.core.ids import PartyId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.events.event_log import log_event
from realm.population.labor_competition import (
    island_has_labor_unrest,
    labor_unrest_yield_multiplier,
    tick_labor_organizing,
    tick_labor_poaching,
    tick_labor_training,
)
from realm.population.laborers import TICKS_PER_GAME_DAY, LaborerNPC
from realm.world import bootstrap_genesis


def _bootstrap() -> object:
    return bootstrap_genesis(seed=7, settler_count=6, settler_starting_cash_cents=50_000_000)


def test_poaching_moves_skilled_laborer() -> None:
    w = _bootstrap()
    poacher = PartyId("settler_001")
    employer = PartyId("settler_002")
    assign_settler_personality(w, poacher)
    assign_settler_personality(w, employer)
    store = w.scenario_state["settler_identities"]
    store[str(poacher)]["personality"]["greed_index"] = 0.9
    w.reputation[str(poacher)] = {"honored": 5, "breached": 0}

    plot = next(iter(w.plots.values()))
    island_id = 0
    w.scenario_state.setdefault("plot_islands", {})[str(plot.plot_id)] = island_id
    plot.owner = poacher
    w.plots[plot.plot_id].owner = poacher

    lab = LaborerNPC(
        laborer_id="lab_poach01",
        display_name="Skilled Sam",
        island_id=island_id,
        home_plot_id=plot.plot_id,
        employer=employer,
        wage_per_day_cents=800,
        skill_levels={"mine_ore": 45},
    )
    w.laborers[lab.laborer_id] = lab
    w.tick = 3 * TICKS_PER_GAME_DAY

    stats = tick_labor_poaching(w)
    assert stats["accepted"] >= 1
    assert lab.employer == poacher
    assert lab.wage_per_day_cents == 1000
    kinds = [e.get("kind") for e in w.event_log if e.get("laborer_id") == lab.laborer_id]
    assert "laborer_hired" in kinds
    assert "wage_unpaid_quit" in kinds


def test_unrest_reduces_output_and_clears_on_raise() -> None:
    w = _bootstrap()
    island_id = 0
    w.scenario_state["labor_unrest"] = {str(island_id): True}
    assert labor_unrest_yield_multiplier(w, island_id) == 0.7

    low_wage = 800
    high_wage = 2500
    plot_id = str(next(iter(w.plots.keys())))
    w.scenario_state.setdefault("plot_islands", {})[plot_id] = island_id
    w.tick = 30 * TICKS_PER_GAME_DAY
    for i in range(5):
        w.tick = 30 * TICKS_PER_GAME_DAY + i
        log_event(
            w,
            "laborer_wage_paid",
            "wage",
            plot_id=plot_id,
            amount_cents=low_wage if i < 4 else high_wage,
        )
    w.tick = 7 * TICKS_PER_GAME_DAY
    tick_labor_organizing(w)
    assert island_has_labor_unrest(w, island_id)

    settler = PartyId("settler_001")
    plot = next(iter(w.plots.values()))
    plot.owner = settler
    w.plots[plot.plot_id].owner = settler
    clear_wage = 1400
    lab = LaborerNPC(
        laborer_id="lab_unrest",
        display_name="Worker",
        island_id=island_id,
        home_plot_id=plot.plot_id,
        employer=settler,
        wage_per_day_cents=clear_wage,
        skill_levels={},
    )
    w.laborers[lab.laborer_id] = lab
    w.tick = 7 * TICKS_PER_GAME_DAY
    tick_labor_organizing(w)
    assert not island_has_labor_unrest(w, island_id)


def test_training_spends_reserve_and_raises_skill() -> None:
    w = _bootstrap()
    settler = PartyId("settler_001")
    acct = party_cash_account(settler)
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=acct,
        amount_cents=500_000,
    )
    lab = LaborerNPC(
        laborer_id="lab_train",
        display_name="Trainee",
        island_id=0,
        home_plot_id=next(iter(w.plots.keys())),
        employer=settler,
        skill_levels={"mine_ore": 10},
    )
    w.laborers[lab.laborer_id] = lab
    w.tick = TICKS_PER_GAME_DAY
    reserve_before = w.ledger.balance(system_reserve_account())
    stats = tick_labor_training(w)
    assert stats["trained"] >= 1
    assert lab.skill_levels["mine_ore"] == 13
    assert w.ledger.balance(system_reserve_account()) == reserve_before + 500
    contracts = w.scenario_state.get("training_contracts") or {}
    assert str(settler) in contracts
