"""HTTP surface for the host-side sim clock: ``GET /sim/status`` + ``POST /sim/control``.

The actual loop thread is exercised in solo mode (socket server). Tests here
only verify the routes mutate the shared ``SimClock`` correctly and return
JSON in the documented shape.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from realm.api import app
from realm.core.time_scale import (
    REAL_SECONDS_PER_GAME_DAY,
    TICKS_PER_GAME_DAY,
)
from realm.world.sim_clock import reset_sim_clock_for_tests


@pytest.fixture(autouse=True)
def _isolate_clock() -> None:
    reset_sim_clock_for_tests()
    yield
    reset_sim_clock_for_tests()


def test_sim_status_returns_canon_constants() -> None:
    c = TestClient(app)
    r = c.get("/sim/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ticks_per_game_day"] == TICKS_PER_GAME_DAY
    assert body["real_seconds_per_game_day"] == REAL_SECONDS_PER_GAME_DAY
    assert body["paused"] is False
    assert body["speed"] == 1.0
    # At 1× one tick is 2.5 real seconds.
    assert body["seconds_per_tick"] == pytest.approx(2.5)


def test_world_static_exposes_pacing_constants() -> None:
    """Clients should read pacing from ``/world/static`` instead of hard-coding."""
    c = TestClient(app)
    c.post("/dev/reset", params={"scenario": "frontier", "seed": 991})
    r = c.get("/world/static")
    assert r.status_code == 200
    body = r.json()
    assert body["ticks_per_game_day"] == TICKS_PER_GAME_DAY
    assert body["real_seconds_per_game_day"] == REAL_SECONDS_PER_GAME_DAY
    assert body["real_seconds_per_tick_at_1x"] == pytest.approx(2.5)
    assert body["ticks_per_real_second_at_1x"] == pytest.approx(0.4)
    # Presets must always include 0 (paused) and 1 (default).
    presets = body["sim_speed_presets"]
    assert 0.0 in presets
    assert 1.0 in presets


def test_sim_control_pauses_and_resumes() -> None:
    c = TestClient(app)
    r = c.post("/sim/control", json={"paused": True})
    assert r.status_code == 200
    body = r.json()
    assert body["paused"] is True
    assert body["effective_speed"] == 0.0
    assert body["seconds_per_tick"] is None

    r2 = c.post("/sim/control", json={"paused": False})
    assert r2.status_code == 200
    assert r2.json()["paused"] is False


def test_sim_control_sets_speed_and_resumes_from_paused() -> None:
    c = TestClient(app)
    c.post("/sim/control", json={"paused": True})
    r = c.post("/sim/control", json={"speed": 4})
    assert r.status_code == 200
    body = r.json()
    # speed=4 unpauses (snap to preset 4×).
    assert body["paused"] is False
    assert body["speed"] == 4.0
    # 1× = 2.5s/tick → 4× = 0.625s/tick.
    assert body["seconds_per_tick"] == pytest.approx(0.625)


def test_sim_control_zero_speed_pauses() -> None:
    c = TestClient(app)
    r = c.post("/sim/control", json={"speed": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["paused"] is True
    assert body["effective_speed"] == 0.0


def test_sim_control_rejects_nonsense_speed() -> None:
    c = TestClient(app)
    r = c.post("/sim/control", json={"speed": "fast please"})
    assert r.status_code == 400


def test_sim_control_rejects_non_bool_paused() -> None:
    c = TestClient(app)
    r = c.post("/sim/control", json={"paused": "yes"})
    assert r.status_code == 400


def test_sim_control_speed_snaps_to_preset() -> None:
    c = TestClient(app)
    r = c.post("/sim/control", json={"speed": 1.7})
    assert r.status_code == 200
    body = r.json()
    # 1.7 → snaps to nearest preset (2.0). Result must be in presets.
    assert body["speed"] in body["speed_presets"]


def test_sim_control_empty_body_is_noop() -> None:
    c = TestClient(app)
    r = c.post("/sim/control", json={})
    assert r.status_code == 200
    body = r.json()
    # Defaults preserved.
    assert body["paused"] is False
    assert body["speed"] == 1.0
