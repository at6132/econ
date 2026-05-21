"""Player custom materials and recipes."""

from __future__ import annotations

from realm.actions.blueprint_actions import create_blueprint
from realm.actions.custom_recipe_actions import create_custom_recipe_action, register_material_action
from realm.actions.plot_actions import claim_plot
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import PartyId, PlotId
from realm.production.custom_content import get_recipe, material_exists
from realm.world import bootstrap_frontier


def test_custom_recipe_links_to_blueprint_on_register() -> None:
    world = bootstrap_frontier(seed=91)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(world, player, pid)["ok"]

    snap = ConservationSnapshot.of(world.ledger, world.inventory)
    assert register_material_action(world, player, "Spice Alloy", "processed", "spice_alloy")["ok"]
    assert material_exists(world, "spice_alloy")

    rec = create_custom_recipe_action(
        world,
        player,
        "Refine spice",
        {"coal": 2},
        {"spice_alloy": 3},
        30,
        100,
        "",
    )
    assert rec["ok"]
    rid = str(rec["recipe_id"])

    bp = create_blueprint(
        world,
        player,
        "Spice Refinery",
        "Custom processor",
        2,
        2,
        {"timber": 5},
        5_000,
        1440,
        [rid],
        14400,
        {},
        1440,
        True,
        0,
        "processing",
        [],
        False,
        False,
    )
    assert bp["ok"]
    bid = str(bp["blueprint_id"])
    assert get_recipe(world, rid) is not None
    assert get_recipe(world, rid).requires_building_id == bid
    assert_money_conserved(world.ledger, snap.ledger_total_cents)
