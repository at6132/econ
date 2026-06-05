"""Settler voice + LLM negotiation — deterministic when Anthropic is disabled."""

from __future__ import annotations

from unittest.mock import patch

from realm.agents.llm_negotiation import (
    negotiate_bilateral_contract,
    tick_llm_negotiation,
)
from realm.agents.llm_voice import (
    _cache_put,
    generate_settler_voice,
    tick_settler_voice,
)
from realm.agents.settler_identity import assign_settler_personality
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account, system_reserve_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.deals.bilateral_contracts import propose_bilateral_contract
from realm.world import bootstrap_genesis


def _settler(world) -> PartyId:
    for p in world.parties:
        if str(p).startswith("settler_"):
            return p
    raise AssertionError("no settler")


def test_voice_cache_replays_without_second_call() -> None:
    world = bootstrap_genesis(seed=7, grid_width=10, grid_height=8, settler_count=2)
    party = _settler(world)
    _cache_put(world, party, "first_foundry", "The furnace is finally mine.")
    with patch("realm.agents.llm_voice.make_client") as mock_client:
        generate_settler_voice(
            world,
            party,
            "first_foundry",
            {"party_display_name": "Test Settler"},
        )
        mock_client.assert_not_called()
    assert any(
        m.get("source") == "settler_voice" and "furnace" in str(m.get("text", "")).lower()
        for m in world.npc_messages_to_player
    )


def test_voice_skips_when_no_client() -> None:
    world = bootstrap_genesis(seed=8, grid_width=10, grid_height=8, settler_count=2)
    party = _settler(world)
    with patch("realm.agents.llm_voice.make_client", return_value=None):
        generate_settler_voice(
            world,
            party,
            "market_corner",
            {"party_display_name": "A", "material": "coal"},
        )
    tick_settler_voice(world)
    assert not any(m.get("source") == "settler_voice" for m in world.npc_messages_to_player)


def test_negotiation_queues_without_blocking_tick() -> None:
    world = bootstrap_genesis(seed=9, grid_width=10, grid_height=8, settler_count=2)
    settlers = sorted((p for p in world.parties if str(p).startswith("settler_")), key=str)
    seller, buyer = settlers[0], settlers[1]
    assign_settler_personality(world, seller)
    assign_settler_personality(world, buyer)
    for p in (seller, buyer):
        acct = party_cash_account(p)
        world.ledger.transfer(
            debit=system_reserve_account(),
            credit=acct,
            amount_cents=200_000,
        )

    terms = {
        "material_id": "coal",
        "qty_per_week": 3,
        "price_cents_per_unit": 80,
        "duration_weeks": 8,
        "exclusive": False,
    }
    with patch("realm.agents.llm_negotiation.make_client") as mock_client:
        mock_client.return_value = object()
        with patch("realm.agents.llm_negotiation._executor") as mock_exec:
            result = negotiate_bilateral_contract(world, seller, buyer, terms)
            assert result == {"ok": True, "queued": True}
            mock_exec.submit.assert_called_once()
    tick_llm_negotiation(world)


def test_force_accept_bilateral_contract() -> None:
    world = bootstrap_genesis(seed=10, grid_width=10, grid_height=8, settler_count=2)
    settlers = sorted((p for p in world.parties if str(p).startswith("settler_")), key=str)
    seller, buyer = settlers[0], settlers[1]
    assign_settler_personality(world, seller)
    assign_settler_personality(world, buyer)
    world.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(buyer),
        amount_cents=500_000,
    )
    result = propose_bilateral_contract(
        world,
        seller,
        buyer,
        MaterialId("coal"),
        2,
        50,
        4,
        False,
        force_accept=True,
    )
    assert result.get("ok")
    assert world.scenario_state.get("bilateral_contracts")


def test_voice_rate_limit_per_game_day() -> None:
    world = bootstrap_genesis(seed=11, grid_width=10, grid_height=8, settler_count=4)
    settlers = sorted((p for p in world.parties if str(p).startswith("settler_")), key=str)[:4]
    with patch("realm.agents.llm_voice.make_client", return_value=object()):
        with patch("realm.agents.llm_voice._executor") as mock_exec:
            for i, party in enumerate(settlers):
                world.tick = i * 10
                generate_settler_voice(
                    world,
                    party,
                    "patent_granted",
                    {"party_display_name": str(party), "node_id": f"node_{i}"},
                )
            assert mock_exec.submit.call_count == 3
