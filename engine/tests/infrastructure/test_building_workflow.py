from realm.actions.plot_actions import claim_plot
from realm.core.ids import PartyId, PlotId
from realm.infrastructure.building_workflow import (
    get_building_routing,
    set_building_routing,
    set_warehouse_rule,
    workflow_public_dict,
)
from realm.world import bootstrap_frontier


def test_workflow_routing_persists() -> None:
    world = bootstrap_frontier(seed=91)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(world, player, pid)["ok"]
    from realm.actions.blueprint_actions import place_blueprint

    placed = place_blueprint(
        world,
        player,
        pid,
        "warehouse",
        grid_x=0,
        grid_y=0,
        build_mode="turnkey",
    )
    assert placed["ok"], placed
    instance_id = str(placed.get("instance_id", ""))
    assert instance_id
    assert set_building_routing(
        world,
        player,
        instance_id,
        {"coal": "stash_this"},
        {"iron_ingot": "stash_this"},
    )["ok"]
    got = get_building_routing(world, player, instance_id)
    assert got["ok"]
    assert got["input"]["coal"] == "stash_this"
    snap = workflow_public_dict(world, player)
    assert snap["building_routing"][instance_id]["input"]["coal"] == "stash_this"


def test_warehouse_rule_requires_owned_plot() -> None:
    world = bootstrap_frontier(seed=91)
    player = PartyId("player")
    pid = PlotId("p-0-0")
    assert claim_plot(world, player, pid)["ok"]
    assert set_warehouse_rule(
        world,
        player,
        pid,
        "coal",
        enabled=True,
        target_qty=50,
        max_price_cents=100,
    )["ok"]
