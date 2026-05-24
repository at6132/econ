"""Lab preset catalog — every id bootstraps; sample conservation + tick smoke."""

from __future__ import annotations

import random

import pytest

from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.labs import all_lab_presets, bootstrap_lab_preset, catalog_stats, list_lab_presets
from realm.labs.preset_schema import LAB_CATEGORIES
from realm.world.tick import advance_tick


def test_catalog_has_many_presets() -> None:
    stats = catalog_stats()
    assert stats["total"] >= 150
    assert stats["featured"] >= 35


def test_all_categories_represented() -> None:
    cats = {p.category for p in all_lab_presets()}
    for c in LAB_CATEGORIES:
        assert c in cats


@pytest.mark.parametrize("preset_id", [p.id for p in all_lab_presets()])
def test_every_preset_bootstraps(preset_id: str) -> None:
    w = bootstrap_lab_preset(preset_id=preset_id, seed=42)
    assert w.scenario_state.get("lab_mode") is True
    assert w.scenario_state.get("lab_preset_id") == preset_id
    assert w.tick == 0
    assert len(w.plots) > 0


def test_bootstrap_with_overrides() -> None:
    w = bootstrap_lab_preset(
        preset_id="feat_tutorial_first_claim",
        seed=99,
        overrides={"map_scale_pct": 120, "cash_scale_pct": 50},
    )
    assert w.seed == 99
    assert w.scenario_state["lab_seed"] == 99


def test_list_filter_and_pagination() -> None:
    page, total = list_lab_presets(category="Markets", limit=10, offset=0)
    assert len(page) <= 10
    assert total >= len(page)
    assert all(p.category == "Markets" for p in page)

    featured, ft = list_lab_presets(featured_only=True, limit=1000)
    assert ft == len(featured)
    assert all(p.featured for p in featured)


def test_money_conserved_sample_on_tick() -> None:
    rng = random.Random(0)
    presets = list(all_lab_presets())
    sample = rng.sample(presets, min(12, len(presets)))
    for preset in sample:
        w = bootstrap_lab_preset(preset_id=preset.id, seed=7)
        snap = ConservationSnapshot.of(w.ledger, w.inventory)
        for _ in range(5):
            advance_tick(w)
        assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_unknown_preset_raises() -> None:
    with pytest.raises(ValueError, match="unknown lab preset"):
        bootstrap_lab_preset(preset_id="no_such_lab", seed=1)
