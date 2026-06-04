"""Patents, global era unlock, licensing, and production blocking."""

from __future__ import annotations

from realm.agents.settler_identity import assign_settler_personality
from realm.core.ids import PartyId
from realm.core.ledger import party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.research.patents import (
    PATENT_EXCLUSIVITY_TICKS,
    grant_patent,
    party_has_patent_license,
    recipe_blocked_by_patent,
    tick_era_advancement,
    tick_patent_licensing,
    tick_research_competition,
)
from realm.research.research_lab import complete_research
from realm.research.tech_tree import era_node_ids
from realm.world import bootstrap_frontier, ensure_party_recipe_book


def test_grant_patent_blocks_other_party_production() -> None:
    w = bootstrap_frontier(seed=401, grid_width=4, grid_height=3)
    holder = PartyId("player")
    other = PartyId("npc_grain_vendor")
    assert grant_patent(w, holder, "electric_motors") is True
    assert grant_patent(w, holder, "electric_motors") is False
    blocked, reason = recipe_blocked_by_patent(w, other, "electric_pump")
    assert blocked is True
    assert reason is not None
    assert "electric_motors" in reason


def test_patent_exclusivity_expires() -> None:
    w = bootstrap_frontier(seed=402, grid_width=4, grid_height=3)
    holder = PartyId("player")
    other = PartyId("npc_grain_vendor")
    assert grant_patent(w, holder, "electric_motors") is True
    w.tick = int(w.tick) + PATENT_EXCLUSIVITY_TICKS
    blocked, _ = recipe_blocked_by_patent(w, other, "electric_pump")
    assert blocked is False


def test_complete_research_grants_patent_to_first_only() -> None:
    w = bootstrap_frontier(seed=403, grid_width=4, grid_height=3)
    a = PartyId("player")
    b = PartyId("npc_grain_vendor")
    assert complete_research(w, a, "electric_motors")["ok"] is True
    assert complete_research(w, b, "electric_motors")["ok"] is True
    assert w.scenario_state["research_global_first"]["electric_motors"] == str(a)
    patent_row = w.scenario_state["patents"]["patent:electric_motors"]
    assert patent_row["holder_party"] == str(a)


def test_global_era_unlock_after_prereq_nodes_completed() -> None:
    w = bootstrap_frontier(seed=404, grid_width=4, grid_height=3)
    party = PartyId("player")
    for nid in era_node_ids("industrial"):
        assert complete_research(w, party, nid)["ok"] is True
    w.tick = TICKS_PER_GAME_DAY
    tick_era_advancement(w)
    unlocked = set(w.scenario_state.get("global_eras_unlocked", []))
    assert "electrical" in unlocked
    assert w.scenario_state.get("current_global_era") == "electrical"


def test_research_competition_feed_when_two_active() -> None:
    w = bootstrap_frontier(seed=405, grid_width=4, grid_height=3)
    w.scenario_state["active_research"] = {
        "settler_a": {"node_id": "electric_motors"},
        "settler_b": {"node_id": "electric_motors"},
    }
    w.tick = TICKS_PER_GAME_DAY
    tick_research_competition(w)
    kinds = [e.get("kind") for e in w.event_log if isinstance(e, dict)]
    assert "world_feed" in kinds


def test_patent_license_grants_recipes() -> None:
    w = bootstrap_frontier(seed=406, grid_width=4, grid_height=3)
    holder = PartyId("settler_holder")
    buyer = PartyId("settler_buyer")
    w.parties.add(holder)
    w.parties.add(buyer)
    assign_settler_personality(w, holder)
    store = w.scenario_state["settler_identities"][str(holder)]
    store["personality"]["greed_index"] = 0.2
    assert grant_patent(w, holder, "electric_motors") is True
    cash = party_cash_account(buyer)
    w.ledger.balances[cash] = 50_000_00
    w.tick = 7 * TICKS_PER_GAME_DAY
    tick_patent_licensing(w)
    assert party_has_patent_license(w, buyer, "electric_motors")
    book = ensure_party_recipe_book(w, buyer)
    assert "electric_pump" in book
