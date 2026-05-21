"""Production: inputs at start, outputs after duration; money conservation."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.production.buildings import build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import party_cash_account
from realm.production import start_production
from realm.production.recipes import RECIPES
from realm.world.tick import advance_tick
from realm.world import bootstrap_frontier

from realm.infrastructure.plot_logistics import plot_output_qty

from plot_helpers import claimable_land_plot_id
from stage_materials import stage_material
from turnkey_fixtures import ensure_plot_grid_power, grant_turnkey_self_materials


def _advance_until_building_ready(w, party: PartyId, plot_id: PlotId, building_id: str) -> None:
    while True:
        row = next(
            (
                b
                for b in w.plot_buildings
                if b.get("party") == str(party)
                and b.get("plot_id") == str(plot_id)
                and b.get("building_id") == building_id
            ),
            None,
        )
        assert row is not None
        ct = row.get("completes_at_tick")
        if ct is None or w.tick >= int(ct):
            return
        advance_tick(w)


def _complete_recipe(w, recipe_id: str) -> None:
    n = RECIPES[recipe_id].duration_ticks
    for _ in range(n):
        advance_tick(w)


def _workshop_turnkey(w, party: PartyId, pid: PlotId, building_id: str) -> None:
    grant_turnkey_self_materials(w, party, building_id, plot_id=pid)
    r = build_on_plot(w, party, pid, building_id, build_mode="self")
    assert r["ok"] is True, r
    _advance_until_building_ready(w, party, pid, building_id)
    if building_id == "wood_shop":
        ensure_plot_grid_power(w, pid)
        stage_material(w, party, MaterialId("timber"), 20, plot_id=pid)


def test_sawmill_completes_after_duration_ticks() -> None:
    w = bootstrap_frontier(seed=1, grid_width=3, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    _workshop_turnkey(w, PartyId("player"), pid, "wood_shop")
    cash0 = w.ledger.balance(party_cash_account(PartyId("player")))
    assert start_production(w, PartyId("player"), pid, "sawmill")["ok"] is True
    assert plot_output_qty(w, pid, MaterialId("timber")) == 20 - 2
    assert w.inventory.qty(PartyId("player"), MaterialId("electricity")) == 0
    cash1 = w.ledger.balance(party_cash_account(PartyId("player")))
    assert cash1 == cash0 - 500  # labor_cents on sawmill recipe
    assert len(w.active_production) == 1
    _complete_recipe(w, "sawmill")
    assert len(w.active_production) == 0
    assert plot_output_qty(w, pid, MaterialId("lumber")) == 1


def test_money_conserved_across_sawmill_run() -> None:
    w = bootstrap_frontier(seed=2, grid_width=2, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    _workshop_turnkey(w, PartyId("player"), pid, "wood_shop")
    total0 = w.ledger.total_cents()
    assert start_production(w, PartyId("player"), pid, "sawmill")["ok"] is True
    _complete_recipe(w, "sawmill")
    assert w.ledger.total_cents() == total0


def test_rejects_second_production_same_plot() -> None:
    w = bootstrap_frontier(seed=3, grid_width=2, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert survey_plot(w, PartyId("player"), pid)["ok"] is True
    _workshop_turnkey(w, PartyId("player"), pid, "power_shed")
    stage_material(w, PartyId("player"), MaterialId("coal"), 10, plot_id=pid)
    assert start_production(w, PartyId("player"), pid, "coal_generator")["ok"] is True
    r = start_production(w, PartyId("player"), pid, "coal_generator")
    assert r["ok"] is True
    assert r.get("started") is False
    assert r.get("completes_at_tick") == w.tick + r["ticks_remaining"]
    assert r.get("recipe_id") == "coal_generator"


def test_tool_cache_reduces_recipe_labor_cash() -> None:
    w = bootstrap_frontier(seed=5, grid_width=3, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    grant_turnkey_self_materials(w, player, "tool_cache", plot_id=pid)
    assert build_on_plot(w, player, pid, "tool_cache", build_mode="self")["ok"] is True
    _advance_until_building_ready(w, player, pid, "tool_cache")
    _workshop_turnkey(w, player, pid, "wood_shop")
    cash0 = w.ledger.balance(party_cash_account(player))
    assert start_production(w, player, pid, "sawmill")["ok"] is True
    cash1 = w.ledger.balance(party_cash_account(player))
    assert cash1 == cash0 - 450  # 500¢ × 90% (tool_cache labor BPS)


def test_stub_hire_routes_part_of_labor_to_employee() -> None:
    from realm.actions import hire_worker_stub

    w = bootstrap_frontier(seed=4, grid_width=2, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    player = PartyId("player")
    emp = PartyId("t1_timber_merchant")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    _workshop_turnkey(w, player, pid, "wood_shop")
    assert hire_worker_stub(w, player, emp, 500)["ok"] is True
    pc = party_cash_account(player)
    ec = party_cash_account(emp)
    cash_p0 = w.ledger.balance(pc)
    cash_e0 = w.ledger.balance(ec)
    total0 = w.ledger.total_cents()
    assert start_production(w, player, pid, "sawmill")["ok"] is True
    assert w.ledger.total_cents() == total0
    assert w.ledger.balance(pc) == cash_p0 - 500
    assert w.ledger.balance(ec) == cash_e0 + 200


def test_twist_rope_completes_and_conserves_ledger() -> None:
    w = bootstrap_frontier(seed=6, grid_width=2, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    _workshop_turnkey(w, player, pid, "wood_shop")
    total0 = w.ledger.total_cents()
    t0 = plot_output_qty(w, pid, MaterialId("timber"))
    assert start_production(w, player, pid, "twist_rope")["ok"] is True
    assert plot_output_qty(w, pid, MaterialId("timber")) == t0 - 1
    _complete_recipe(w, "twist_rope")
    assert w.ledger.total_cents() == total0
    assert plot_output_qty(w, pid, MaterialId("rope")) == 3


def test_build_ladder_completes_and_conserves_ledger() -> None:
    w = bootstrap_frontier(seed=8, grid_width=2, grid_height=2)
    pid = claimable_land_plot_id(w, PartyId("player"))
    player = PartyId("player")
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    _workshop_turnkey(w, player, pid, "wood_shop")
    stage_material(w, player, MaterialId("lumber"), 4, plot_id=pid)
    stage_material(w, player, MaterialId("rope"), 4, plot_id=pid)
    total0 = w.ledger.total_cents()
    assert start_production(w, player, pid, "build_ladder")["ok"] is True
    _complete_recipe(w, "build_ladder")
    assert w.ledger.total_cents() == total0
    assert plot_output_qty(w, pid, MaterialId("ladder")) == 1
    assert plot_output_qty(w, pid, MaterialId("lumber")) == 2
    assert plot_output_qty(w, pid, MaterialId("rope")) == 2
