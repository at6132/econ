"""Thin FastAPI layer — clients propose; engine validates (Law 10)."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from realm.actions import claim_plot, survey_plot
from realm.ids import PartyId, PlotId
from realm.tick import advance_tick
from realm.world import bootstrap_frontier, world_public_dict

app = FastAPI(title="Realm Engine", version="0.1.0")

# Single in-memory world for dev; persistence comes later
_world = bootstrap_frontier(seed=42)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/world")
def get_world() -> dict:
    return world_public_dict(_world)


@app.post("/tick")
def post_tick() -> dict:
    advance_tick(_world)
    return {"ok": True, "tick": _world.tick}


@app.post("/plots/{plot_id}/claim")
def post_claim(plot_id: str, party: Annotated[str, Query()] = "player") -> dict:
    party_id = PartyId(party)
    r = claim_plot(_world, party_id, PlotId(plot_id))
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/plots/{plot_id}/survey")
def post_survey(plot_id: str, party: Annotated[str, Query()] = "player") -> dict:
    r = survey_plot(_world, PartyId(party), PlotId(plot_id))
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["reason"])
    return dict(r)


@app.post("/dev/reset")
def dev_reset(seed: Annotated[int, Query()] = 42) -> dict:
    """Recreate Frontier world (dev only)."""
    global _world
    _world = bootstrap_frontier(seed=seed)
    return {"ok": True, "seed": seed}
