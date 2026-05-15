"""Unified employment — HTTP surface for laborers + stub NPC path."""

from __future__ import annotations

from fastapi.testclient import TestClient

from realm.api import _state
from realm.api import app
from realm.actions import claim_plot
from realm.core.conservation import ConservationSnapshot, assert_money_conserved
from realm.core.ids import PartyId
from realm.population.employment import tick_laborer_wages
from realm.population.laborers import TICKS_PER_GAME_DAY, laborer_cash_account
from realm.world import bootstrap_genesis


def _install_small_genesis_world(*, seed: int = 910) -> None:
    _state.WORLD = bootstrap_genesis(
        seed=seed,
        grid_width=48,
        grid_height=36,
        settler_count=6,
    )


def test_hire_laborer_via_stub_route_http() -> None:
    _install_small_genesis_world(seed=911)
    c = TestClient(app)
    r = c.get("/laborers", params={"employed": "false"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("count", 0) >= 1
    lid = body["laborers"][0]["laborer_id"]
    r2 = c.post(
        "/hire",
        params={
            "employer": "player",
            "employee": lid,
            "signing_bonus_cents": 150,
            "wage_per_tick_cents": 10,
            "wage_interval_ticks": 2,
        },
    )
    assert r2.status_code == 200
    lab = _state.WORLD.laborers[lid]
    assert lab.employer == PartyId("player")


def test_fire_laborer_http() -> None:
    _install_small_genesis_world(seed=912)
    c = TestClient(app)
    lid = c.get("/laborers", params={"employed": "false"}).json()["laborers"][0]["laborer_id"]
    assert c.post(
        "/hire",
        params={"employer": "player", "employee": lid, "signing_bonus_cents": 50},
    ).status_code == 200
    r = c.post("/hire/fire", params={"employer": "player", "laborer_id": lid})
    assert r.status_code == 200
    assert _state.WORLD.laborers[lid].employer is None


def test_wage_paid_daily_after_hire_conserved() -> None:
    _install_small_genesis_world(seed=913)
    c = TestClient(app)
    w = _state.WORLD
    lid = c.get("/laborers", params={"employed": "false"}).json()["laborers"][0]["laborer_id"]
    assert c.post(
        "/hire",
        params={
            "employer": "player",
            "employee": lid,
            "signing_bonus_cents": 0,
            "wage_per_tick_cents": 25,
            "wage_interval_ticks": 4,
        },
    ).status_code == 200
    snap = ConservationSnapshot.of(w.ledger, w.inventory)
    lc = laborer_cash_account(lid)
    before = w.ledger.balance(lc)
    w.tick = TICKS_PER_GAME_DAY
    tick_laborer_wages(w)
    assert w.ledger.balance(lc) > before
    assert_money_conserved(w.ledger, snap.ledger_total_cents)


def test_list_laborers_filters_unemployed_http() -> None:
    _install_small_genesis_world(seed=914)
    c = TestClient(app)
    r = c.get("/laborers", params={"employed": "false"})
    assert r.status_code == 200
    for row in r.json()["laborers"]:
        assert row.get("employed") is False


def test_hire_phantom_npc_still_works_http() -> None:
    c = TestClient(app)
    assert c.post("/dev/reset", params={"seed": 915, "scenario": "frontier"}).status_code == 200
    r = c.post(
        "/hire",
        params={
            "employer": "player",
            "employee": "npc_grain_vendor",
            "signing_bonus_cents": 250,
            "wage_per_tick_cents": 1,
            "wage_interval_ticks": 10,
        },
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_claim_and_job_opening_http() -> None:
    _install_small_genesis_world(seed=916)
    c = TestClient(app)
    w = _state.WORLD
    human = PartyId("player")
    pid = next(pid for pid, pl in w.plots.items() if pl.owner is None)
    assert claim_plot(w, human, pid)["ok"] is True
    r = c.post(
        "/jobs/openings",
        params={
            "employer": "player",
            "plot_id": str(pid),
            "wage_per_day_cents": 1200,
        },
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True
