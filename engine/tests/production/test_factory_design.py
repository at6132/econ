"""Custom factory design — novel products, machines, production run."""

from __future__ import annotations

from realm.actions import claim_plot, survey_plot
from realm.actions.blueprint_actions import place_blueprint
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.production import start_production
from realm.production.buildings import build_on_plot
from realm.production.factory_design import design_custom_factory
from realm.research.research_lab import complete_research
from realm.world import bootstrap_frontier
from stage_materials import stage_material
from turnkey_fixtures import grant_turnkey_self_materials


def _prep_party(w, player: PartyId) -> None:
    complete_research(w, player, "precision_tooling")
    complete_research(w, player, "workshop_engineering")
    w.inventory.add(player, MaterialId("pump_unit"), 2)
    w.inventory.add(player, MaterialId("gear_set"), 2)
    w.inventory.add(player, MaterialId("grain"), 20)
    w.inventory.add(player, MaterialId("lumber"), 10)
    from realm.core.ledger import party_cash_account, system_reserve_account

    cash = party_cash_account(player)
    w.ledger.ensure_account(cash)
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=cash,
        amount_cents=500_000_00,
    )


def test_factory_creates_novel_product_and_blueprint() -> None:
    w = bootstrap_frontier(seed=601, grid_width=6, grid_height=4)
    player = PartyId("player")
    _prep_party(w, player)
    r = design_custom_factory(
        w,
        player,
        name="Avi Foods Plant",
        description="Protein extrusion",
        footprint_w=3,
        footprint_h=2,
        category="processing",
        construction_materials={"lumber": 4, "brick": 2},
        construction_labor_cents=10_000,
        construction_ticks=1440,
        maintenance_interval_ticks=0,
        maintenance_materials={},
        maintenance_grace_ticks=0,
        is_public=False,
        license_fee_cents=0,
        terrain_requirements=["plains"],
        requires_coastal=False,
        requires_power=True,
        installed_machines={"pump_unit": 1, "gear_set": 1},
        process_name="Extrude protein",
        process_inputs={"grain": 2},
        process_outputs={"avi_protein": 5},
        process_duration_ticks=1440,
        process_labor_cents=500,
        new_products=[
            {
                "display_name": "Avi Protein",
                "material_id": "avi_protein",
                "output_slot": "avi_protein",
                "mass_per_unit_kg": 300.0,
                "category": "processed",
            }
        ],
    )
    assert r["ok"] is True, r
    bid = str(r["blueprint_id"])
    recipe_id = str(r["recipe_id"])
    assert recipe_id in w.party_recipe_books[str(player)]
    assert "avi_protein" in w.scenario_state.get("custom_materials", {})


def test_factory_runs_on_placed_building() -> None:
    w = bootstrap_frontier(seed=602, grid_width=6, grid_height=4)
    player = PartyId("player")
    _prep_party(w, player)
    r = design_custom_factory(
        w,
        player,
        name="Test Mill",
        description="",
        footprint_w=2,
        footprint_h=2,
        category="processing",
        construction_materials={"lumber": 2},
        construction_labor_cents=5_000,
        construction_ticks=1,
        maintenance_interval_ticks=0,
        maintenance_materials={},
        maintenance_grace_ticks=0,
        is_public=False,
        license_fee_cents=0,
        terrain_requirements=["plains"],
        requires_coastal=False,
        requires_power=False,
        installed_machines={"gear_set": 1},
        process_name="Mill test good",
        process_inputs={"grain": 1},
        process_outputs={"test_good": 2},
        process_duration_ticks=1440,
        process_labor_cents=100,
        new_products=[
            {
                "display_name": "Test Good",
                "material_id": "test_good",
                "output_slot": "test_good",
                "mass_per_unit_kg": 350.0,
                "category": "processed",
            }
        ],
    )
    assert r["ok"] is True, r
    bid = str(r["blueprint_id"])
    pid = PlotId("p-0-0")
    for p, plot in w.plots.items():
        if plot.owner is None and str(plot.terrain.value) == "plains":
            pid = PlotId(str(p))
            break
    assert claim_plot(w, player, pid)["ok"] is True
    assert survey_plot(w, player, pid)["ok"] is True
    w.inventory.add(player, MaterialId("pump_unit"), 1)
    w.inventory.add(player, MaterialId("gear_set"), 2)
    grant_turnkey_self_materials(w, player, bid)
    pr = place_blueprint(w, player, pid, bid, 0, 0, build_mode="turnkey")
    assert pr["ok"] is True, pr
    inst = str(pr.get("instance_id", ""))
    for b in w.plot_buildings:
        if b.get("instance_id") == inst:
            b["completes_at_tick"] = -1
    stage_material(w, player, MaterialId("grain"), 5, plot_id=pid)
    prod = start_production(w, player, pid, str(r["recipe_id"]))
    assert prod["ok"] is True, prod
