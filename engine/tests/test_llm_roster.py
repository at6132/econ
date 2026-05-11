"""Tier-3 roster — scenario → persona mapping."""

from __future__ import annotations

from realm.ids import PartyId
from realm.llm_roster import SCENARIO_TIER3_PARTY
from realm.world import bootstrap_by_scenario


def test_scenario_party_mapping() -> None:
    assert SCENARIO_TIER3_PARTY["frontier"] == SCENARIO_TIER3_PARTY["millrace"] == "llm_margaux"
    assert SCENARIO_TIER3_PARTY["cartel"] == "llm_elira"
    assert SCENARIO_TIER3_PARTY["bootstrapper"] == "llm_finn"
    assert SCENARIO_TIER3_PARTY["speculator"] == "llm_rico"
    assert SCENARIO_TIER3_PARTY["archive"] == "llm_yuki"
    assert SCENARIO_TIER3_PARTY["genesis"] == "llm_margaux"


def test_cartel_bootstraps_elira_not_margaux() -> None:
    w = bootstrap_by_scenario(seed=2, scenario="cartel")
    assert "llm_elira" in w.llm_agents
    assert "llm_margaux" not in w.llm_agents


def test_archive_intel_tick_boost() -> None:
    w = bootstrap_by_scenario(seed=3, scenario="archive")
    assert w.market_intel_expires_tick >= 280


def test_genesis_bootstraps_margaux() -> None:
    w = bootstrap_by_scenario(seed=5, scenario="genesis")
    assert "llm_margaux" in w.llm_agents
    assert PartyId("llm_margaux") in w.parties
