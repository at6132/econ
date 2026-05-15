"""Settler entrepreneurs post jobs when workshops are operational."""

from __future__ import annotations

from realm.world.tick import advance_tick
from realm.world import bootstrap_genesis


def test_settlers_post_job_openings_after_workshops_built() -> None:
    w = bootstrap_genesis(seed=42, grid_width=48, grid_height=36, settler_count=12)
    for _ in range(3 * 1440):
        advance_tick(w)
    settler_openings = [
        o for o in w.job_openings if str(o.employer).startswith("settler_")
    ]
    assert len(settler_openings) >= 1, "expected at least one settler-posted opening"
