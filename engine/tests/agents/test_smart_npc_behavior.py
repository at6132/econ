"""Behavior tests for settler archetypes and market oracle."""

from __future__ import annotations

import os
import random

import pytest


def test_archetypes_assigned_deterministically() -> None:
    from realm.agents.settler_archetypes import get_archetype
    from realm.core.ids import PartyId

    p = PartyId("settler_000")
    assert get_archetype(p) == get_archetype(p)
    archetypes = {get_archetype(PartyId(f"settler_{i:03d}")) for i in range(50)}
    assert len(archetypes) >= 3, "expected at least 3 archetype types in 50 settlers"


def test_market_oracle_built_once_per_day() -> None:
    os.environ["REALM_LLM_DISABLE"] = "1"
    from realm.agents.market_oracle import get_oracle
    from realm.world.tick import advance_tick
    from realm.world.world import bootstrap_genesis

    w = bootstrap_genesis(seed=1, settler_count=5)
    oracle1 = get_oracle(w)
    oracle2 = get_oracle(w)
    assert oracle1 is oracle2
    for _ in range(1440):
        advance_tick(w)
    oracle3 = get_oracle(w)
    assert oracle3 is not oracle1, "oracle should rebuild on new game-day"


def test_market_aware_recipe_prefers_profitable(monkeypatch: pytest.MonkeyPatch) -> None:
    os.environ["REALM_LLM_DISABLE"] = "1"
    from realm.agents.genesis_settlers import _recipe_rank_score
    from realm.agents.market_oracle import _build_oracle
    from realm.core.ids import PartyId, PlotId
    from realm.core.ledger import party_cash_account, system_reserve_account
    from realm.world.world import bootstrap_genesis

    w = bootstrap_genesis(seed=5, settler_count=5)
    oracle = _build_oracle(w, 0)
    oracle.scarce.add("coal")
    oracle.recipe_margins["mine_coal"] = 0.5
    oracle.recipe_margins["grow_grain"] = -0.3
    monkeypatch.setattr(
        "realm.agents.market_oracle.get_oracle", lambda _world: oracle
    )

    party = PartyId("settler_000")
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=1_000_000,
    )
    pid = next(
        PlotId(k)
        for k, p in w.plots.items()
        if "water" not in str(p.terrain).lower() and p.owner is None
    )
    rng = random.Random(42)
    coal_score = _recipe_rank_score(w, party, pid, "mine_coal", rng=rng)
    grain_score = _recipe_rank_score(w, party, pid, "grow_grain", rng=rng)
    assert coal_score > grain_score, "profitable recipe should score higher"


def test_researcher_archetype_creates_blueprint_on_discovery() -> None:
    os.environ["REALM_LLM_DISABLE"] = "1"
    import pytest

    from realm.agents.settler_archetypes import (
        Archetype,
        get_archetype,
        maybe_create_discovery_blueprint,
    )
    from realm.core.ids import PartyId
    from realm.core.ledger import party_cash_account, system_reserve_account
    from realm.world.world import bootstrap_genesis

    w = bootstrap_genesis(seed=99, settler_count=5)
    researchers = [
        p
        for p in w.parties
        if str(p).startswith("settler_") and get_archetype(p) == Archetype.RESEARCHER
    ]
    if not researchers:
        pytest.skip("no researcher settlers in this seed")
    party = researchers[0]
    w.ledger.transfer(
        debit=system_reserve_account(),
        credit=party_cash_account(party),
        amount_cents=5_000_000,
    )
    blueprints_before = len(w.blueprints)
    maybe_create_discovery_blueprint(w, party, "smelt_iron")
    assert len(w.blueprints) > blueprints_before, "researcher should create blueprint"
    new_bp = [b for b in w.blueprints.values() if b.creator_party == str(party)]
    assert new_bp, "blueprint should be credited to researcher"
    assert new_bp[0].license_fee_cents > 0, "blueprint should have a license fee"
    assert new_bp[0].is_public, "researcher blueprints are public"
