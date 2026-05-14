"""Full save/load round-trip checks per Phase 2 scenario (persistence compatibility)."""

from __future__ import annotations

import pytest

from realm.actions import claim_plot
from realm.buildings import build_on_plot
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.event_log import log_event
from realm.state_io import SNAPSHOT_VERSION, dump_world, dumps_json, loads_json
from realm.tick import advance_tick
from realm.world import bootstrap_by_scenario, bootstrap_genesis


SCENARIOS = ("frontier", "cartel", "bootstrapper", "speculator", "millrace", "archive")


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_dump_load_roundtrip_after_ticks_and_building(scenario: str) -> None:
    w = bootstrap_by_scenario(seed=101, scenario=scenario)
    pid = PlotId("p-0-0")
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert build_on_plot(w, PartyId("player"), pid, "watch_hut")["ok"] is True
    for _ in range(4):
        advance_tick(w)

    assert dump_world(w)["version"] == SNAPSHOT_VERSION
    ledger_total = w.ledger.total_cents()
    inv_snapshot = w.inventory.snapshot()
    w2 = loads_json(dumps_json(w))

    assert w2.tick == w.tick
    assert w2.scenario_id == w.scenario_id
    assert w2.seed == w.seed
    assert w2.market_intel_expires_tick == w.market_intel_expires_tick
    assert w2.next_building_instance_seq == w.next_building_instance_seq
    assert w2.ledger.total_cents() == ledger_total
    assert w2.inventory.snapshot() == inv_snapshot
    assert w2.llm_agents == w.llm_agents
    assert w2.npc_messages_to_player == w.npc_messages_to_player
    assert w2.llm_session_cost_micro_usd == w.llm_session_cost_micro_usd
    if w.llm_agents:
        tier3_party = next(iter(w.llm_agents.keys()))
        assert PartyId(tier3_party) in w2.parties
    assert w2.plots[pid].owner == PartyId("player")
    assert len(w2.plot_buildings) == len(w.plot_buildings)
    assert w2.plot_buildings == w.plot_buildings


def test_dump_load_roundtrip_genesis_small_grid() -> None:
    """Genesis defaults to a large map — use a compact bootstrap for CI-friendly persistence checks."""
    w = bootstrap_genesis(seed=101, grid_width=14, grid_height=12, settler_count=6)
    pid = PlotId("p-0-0")
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert build_on_plot(w, PartyId("player"), pid, "watch_hut")["ok"] is True
    for _ in range(4):
        advance_tick(w)

    w.deployed_lua_sources["player"] = "return 0\n"

    assert dump_world(w)["version"] == SNAPSHOT_VERSION
    ledger_total = w.ledger.total_cents()
    inv_snapshot = w.inventory.snapshot()
    w2 = loads_json(dumps_json(w))

    assert w2.tick == w.tick
    assert w2.scenario_id == "genesis"
    assert w2.seed == w.seed
    assert w2.ledger.total_cents() == ledger_total
    assert w2.inventory.snapshot() == inv_snapshot
    assert w2.llm_agents == w.llm_agents
    assert "llm_margaux" in w2.llm_agents
    assert w.party_display_names.get("settler_001")
    assert w2.party_display_names == w.party_display_names
    assert w2.plots[pid].owner == PartyId("player")
    assert len(w2.plot_buildings) == len(w.plot_buildings)
    assert w2.plot_buildings == w.plot_buildings
    assert w2.deployed_lua_sources.get("player") == "return 0\n"
    assert w2.use_plot_output_logistics is True
    assert w.use_plot_output_logistics is True
    # Sprint 6 — Phase D.1: ``plot_output_stock`` is a display log, mutated
    # by production_done and shipment arrival. We seed a counter directly
    # to verify the snapshot field still round-trips.
    pid2 = PlotId("p-1-0")
    assert claim_plot(w, PartyId("player"), pid2)["ok"] is True
    w.plot_output_stock[str(pid2)] = {"timber": 11}
    w4 = loads_json(dumps_json(w))
    assert w4.plot_output_stock.get(str(pid2), {}).get("timber") == 11
    assert w4.use_plot_output_logistics is True
    assert w4.market_seller_registered == w.market_seller_registered
    w.scenario_state["persist_probe"] = {"n": w.tick}
    w3 = loads_json(dumps_json(w))
    assert w3.scenario_state.get("persist_probe", {}).get("n") == w.tick


def test_world_feed_log_survives_dump_roundtrip() -> None:
    w = bootstrap_by_scenario(seed=7, scenario="frontier")
    log_event(w, "world_feed", "headline A", topic="coal")
    log_event(w, "world_feed", "headline B")
    log_event(w, "world", "non-feed row")
    w2 = loads_json(dumps_json(w))
    assert [e.get("message") for e in w2.world_feed_log] == ["headline A", "headline B"]
    assert w2.world_feed_log[0].get("topic") == "coal"
    assert "world_feed_log" in dump_world(w)


def test_dump_plot_buildings_decoupled_from_live_mutations() -> None:
    """Regression: ``dump_world`` must not alias live ``plot_buildings`` rows."""
    w = bootstrap_by_scenario(seed=3, scenario="frontier")
    pid = PlotId("p-1-0")
    assert claim_plot(w, PartyId("player"), pid)["ok"] is True
    assert build_on_plot(w, PartyId("player"), pid, "field_stockade")["ok"] is True
    blob = dump_world(w)
    orig = int(blob["plot_buildings"][0]["condition_bps"])
    w.plot_buildings[0]["condition_bps"] = 123
    assert blob["plot_buildings"][0]["condition_bps"] == orig
    assert w.plot_buildings[0]["condition_bps"] == 123
