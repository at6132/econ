"""Tier-3 LLM agents — tool dispatch + persistence (no live API in CI)."""

from __future__ import annotations

from typing import Any

import pytest

from realm.agents_tier3 import (
    build_observation_json,
    execute_llm_tool,
    plan_llm_party_once,
)
from realm.ids import MaterialId, PartyId
from realm.tick import advance_tick
from realm.world import bootstrap_frontier


def test_build_observation_json_shape() -> None:
    w = bootstrap_frontier(seed=2, grid_width=3, grid_height=2)
    party = PartyId("llm_margaux")
    raw = build_observation_json(w, party)
    assert "llm_margaux" in raw
    assert "cash_cents" in raw


def test_execute_unknown_tool() -> None:
    w = bootstrap_frontier(seed=3, grid_width=2, grid_height=2)
    r = execute_llm_tool(w, PartyId("llm_margaux"), "sim_not_a_real_tool", {})
    assert r["ok"] is False


def test_execute_market_buy_conserves_ledger() -> None:
    w = bootstrap_frontier(seed=4, grid_width=2, grid_height=2)
    buyer = PartyId("llm_margaux")
    total_before = w.ledger.total_cents()
    r = execute_llm_tool(w, buyer, "sim_market_buy", {"material": "grain", "max_qty": 1})
    assert r.get("ok") is True
    assert w.ledger.total_cents() == total_before
    assert w.inventory.qty(buyer, MaterialId("grain")) >= 1


def test_plan_with_mocked_haiku_updates_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    w = bootstrap_frontier(seed=5, grid_width=3, grid_height=2)

    def fake_run(
        *,
        system: str,
        user_message: str,
        on_tool: Any,
        max_rounds: int = 6,
    ) -> tuple[list[dict[str, Any]], str | None]:
        _ = (system, user_message, max_rounds)
        out = on_tool("sim_noop", {})
        return ([{"event": "tool", "name": "sim_noop", "result": out}], "done")

    monkeypatch.setattr("realm.agents_tier3.run_haiku_tool_session", fake_run)
    party = PartyId("llm_margaux")
    before = str(w.llm_agents[str(party)]["memory_summary"])
    r = plan_llm_party_once(w, party)
    assert r["ok"] is True
    assert w.llm_agents[str(party)]["last_plan_tick"] == w.tick
    assert str(w.llm_agents[str(party)]["memory_summary"]) != before


def test_tick_skips_llm_without_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REALM_LLM_DISABLE", "1")
    w = bootstrap_frontier(seed=6, grid_width=2, grid_height=2)
    t0 = w.tick
    advance_tick(w)
    assert w.tick == t0 + 1


def test_execute_place_sell_order_moves_inventory() -> None:
    w = bootstrap_frontier(seed=8, grid_width=2, grid_height=2)
    party = PartyId("llm_margaux")
    before = w.inventory.qty(party, MaterialId("timber"))
    r = execute_llm_tool(
        w,
        party,
        "sim_place_sell_order",
        {"material": "timber", "qty": 1, "price_per_unit_cents": 500},
    )
    assert r.get("ok") is True
    assert w.inventory.qty(party, MaterialId("timber")) == before - 1
