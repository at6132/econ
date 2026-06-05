"""Settler entrepreneurs post jobs when workshops are operational."""

from __future__ import annotations

from realm.world.tick import advance_tick
from realm.world import bootstrap_genesis
from stage_materials import seed_settler_workshop_materials


def test_settlers_post_job_openings_after_workshops_built() -> None:
    w = bootstrap_genesis(seed=42, grid_width=48, grid_height=36, settler_count=12)
    seed_settler_workshop_materials(
        w,
        [("lumber", 25), ("stone", 20), ("brick", 15), ("timber", 10), ("coal", 10)],
    )
    for _ in range(5000):
        advance_tick(w)
    settler_openings = [
        o for o in w.job_openings if str(o.employer).startswith("settler_")
    ]
    assert len(settler_openings) >= 1, "expected at least one settler-posted opening"
