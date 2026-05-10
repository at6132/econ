"""Full save/load round-trip checks per Phase 2 scenario (persistence compatibility)."""

from __future__ import annotations

import pytest

from realm.actions import claim_plot
from realm.buildings import build_on_plot
from realm.ids import PartyId, PlotId
from realm.state_io import SNAPSHOT_VERSION, dump_world, dumps_json, loads_json
from realm.tick import advance_tick
from realm.world import bootstrap_by_scenario


SCENARIOS = ("frontier", "cartel", "bootstrapper", "speculator")


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
    assert PartyId("llm_margaux") in w2.parties
    assert w2.plots[pid].owner == PartyId("player")
    assert len(w2.plot_buildings) == len(w.plot_buildings)
    assert w2.plot_buildings == w.plot_buildings


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
