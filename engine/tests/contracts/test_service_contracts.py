"""Service subscriptions — validated service_id and delivery checks."""

from __future__ import annotations

from realm.contracts.stubs import (
    VALID_SERVICE_IDS,
    accept_service_sub,
    propose_service_sub,
    tick_service_subscriptions,
)
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.world import bootstrap_frontier


def test_propose_service_requires_valid_service_id() -> None:
    w = bootstrap_frontier(seed=901, grid_width=4, grid_height=3)
    r = propose_service_sub(
        w,
        PartyId("player"),
        PartyId("t1_consumer"),
        100,
        500,
        "stub_service",
    )
    assert r.get("ok") is False
    assert "stub_service" in str(r.get("reason", "")) or "unknown" in str(r.get("reason", "")).lower()


def test_propose_route_access_service_ok() -> None:
    w = bootstrap_frontier(seed=902, grid_width=4, grid_height=3)
    w.scenario_state["route_operators"] = {
        "r1": [{"operator_party": "player", "route_key": "r1"}],
    }
    r = propose_service_sub(
        w,
        PartyId("player"),
        PartyId("t1_consumer"),
        200,
        800,
        "route_access",
        {"route_key": "r1"},
    )
    assert r.get("ok") is True


def test_service_sub_fee_transfers_on_accept_conserved() -> None:
    w = bootstrap_frontier(seed=903, grid_width=4, grid_height=3)
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    pr = propose_service_sub(
        w,
        PartyId("player"),
        PartyId("t1_consumer"),
        300,
        600,
        "analytics_data",
    )
    cid = str(pr["contract_id"])
    assert accept_service_sub(w, PartyId("t1_consumer"), cid)["ok"] is True
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_service_breach_on_provider_losing_route_prorata_refund() -> None:
    w = bootstrap_frontier(seed=904, grid_width=4, grid_height=3)
    w.scenario_state["route_operators"] = {
        "rk": [{"operator_party": "player", "route_key": "rk"}],
    }
    pr = propose_service_sub(
        w,
        PartyId("player"),
        PartyId("t1_consumer"),
        1_000,
        1_000,
        "route_access",
        {"route_key": "rk"},
    )
    cid = str(pr["contract_id"])
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    assert accept_service_sub(w, PartyId("t1_consumer"), cid)["ok"] is True
    w.scenario_state["route_operators"] = {}
    w.tick = 200
    tick_service_subscriptions(w)
    c = next(x for x in w.contracts if x.get("id") == cid)
    assert c.get("status") == "breached"
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_power_supply_breach_when_plot_unpowered() -> None:
    from realm.infrastructure.power_grid import plot_has_grid_capacity
    from realm.infrastructure.roads import build_road

    w = bootstrap_frontier(seed=905, grid_width=12, grid_height=10)
    from tests.plot_helpers import two_adjacent_plot_ids

    shed, target = two_adjacent_plot_ids(w)
    w.plots[shed].owner = PartyId("player")
    w.plots[target].owner = PartyId("player")
    w.next_building_instance_seq += 1
    iid = f"b{w.next_building_instance_seq:06d}"
    w.plot_buildings.append(
        {
            "instance_id": iid,
            "condition_bps": 10_000,
            "plot_id": str(shed),
            "party": "player",
            "building_id": "power_shed",
            "label": "power_shed",
            "cost_cents": 0,
            "build_mode": "turnkey",
            "completes_at_tick": -10_000,
        }
    )
    w.building_maintenance[iid] = {
        "due_at_tick": 9_999_999,
        "missed_cycles": 0,
        "efficiency_pct": 100,
    }
    player = PartyId("player")
    w.inventory.add(player, MaterialId("lumber"), 4)
    w.inventory.add(player, MaterialId("stone"), 4)
    w.inventory.add(player, MaterialId("lumber"), 4)
    w.inventory.add(player, MaterialId("stone"), 4)
    road = build_road(w, player, shed, target)
    assert road["ok"], road.get("reason")
    assert plot_has_grid_capacity(w, target)
    pr = propose_service_sub(
        w,
        PartyId("player"),
        PartyId("t1_consumer"),
        400,
        900,
        "power_supply",
        {"plot_id": str(target)},
    )
    cid = str(pr["contract_id"])
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    assert accept_service_sub(w, PartyId("t1_consumer"), cid)["ok"] is True
    w.building_maintenance[iid]["efficiency_pct"] = 0
    assert not plot_has_grid_capacity(w, target)
    w.tick = 50
    tick_service_subscriptions(w)
    c = next(x for x in w.contracts if x.get("id") == cid)
    assert c.get("status") == "breached"
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_valid_service_ids_frozenset_nonempty() -> None:
    assert "analytics_data" in VALID_SERVICE_IDS
    assert "route_access" in VALID_SERVICE_IDS
    assert "storage" in VALID_SERVICE_IDS
