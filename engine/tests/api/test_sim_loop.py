"""Host sim loop: subscriber registry, tick-frame shape, no-tick-without-clients.

These tests exercise the building blocks of ``realm.api.sim_loop`` directly.
The full daemon loop's wall-clock pacing is covered by the SimClock unit
tests; here we focus on the parts that touch the world.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from realm.api import _state, sim_loop
from realm.api import app  # registers routes_sim
from realm.world.sim_clock import (
    get_sim_clock,
    reset_sim_clock_for_tests,
)


@pytest.fixture(autouse=True)
def _isolate_clock_and_subs() -> None:
    reset_sim_clock_for_tests()
    # Subscriber list is module-level; clear any test residue.
    with sim_loop._subscribers_lock:  # noqa: SLF001
        sim_loop._subscribers.clear()  # noqa: SLF001
    yield
    with sim_loop._subscribers_lock:  # noqa: SLF001
        sim_loop._subscribers.clear()  # noqa: SLF001
    reset_sim_clock_for_tests()


def test_subscribe_returns_unsubscribe_and_routes_pushes() -> None:
    received: list[dict[str, Any]] = []
    unsub = sim_loop.subscribe(lambda p: received.append(p))
    sim_loop._push_to_all({"kind": "test", "x": 1})
    assert received == [{"kind": "test", "x": 1}]
    unsub()
    sim_loop._push_to_all({"kind": "test", "x": 2})
    assert len(received) == 1  # nothing after unsubscribe


def test_failing_subscriber_does_not_kill_other_subscribers() -> None:
    received: list[dict[str, Any]] = []

    def boom(_p: dict[str, Any]) -> None:
        raise RuntimeError("transport down")

    sim_loop.subscribe(boom)
    sim_loop.subscribe(lambda p: received.append(p))
    sim_loop._push_to_all({"kind": "test"})
    assert received == [{"kind": "test"}]


def test_build_tick_frame_shape() -> None:
    # Need a world: bootstrap via /dev/reset (small frontier).
    c = TestClient(app)
    c.post("/dev/reset", params={"scenario": "frontier", "seed": 999})
    # Advance a couple ticks so we can sanity-check day math.
    c.post("/tick/batch", params={"count": 2880})  # 2 game-days
    frame = sim_loop.build_tick_frame()
    assert frame["kind"] == "tick"
    assert frame["tick"] == _state.WORLD.tick  # type: ignore[attr-defined]
    # 2880 / 1440 = 2 days elapsed → current day index = 2 → game_day = 3 (1-based).
    assert frame["game_day"] == 3
    assert frame["game_year"] == 1
    assert frame["season"] in {"Spring", "Summer", "Autumn", "Winter"}
    assert frame["paused"] is False
    assert frame["speed"] == 1.0
    assert frame["effective_speed"] == 1.0


def test_sim_control_post_broadcasts_status_to_subscribers() -> None:
    received: list[dict[str, Any]] = []
    sim_loop.subscribe(lambda p: received.append(p))
    c = TestClient(app)
    c.post("/sim/control", json={"paused": True})
    # The route calls _broadcast_status which uses sim_loop._push_to_all.
    kinds = [r.get("kind") for r in received]
    assert "sim_status" in kinds
    status = next(r for r in received if r.get("kind") == "sim_status")
    assert status["paused"] is True


def test_clock_pause_persists_speed_for_resume() -> None:
    c = TestClient(app)
    c.post("/sim/control", json={"speed": 2})
    c.post("/sim/control", json={"paused": True})
    clk = get_sim_clock()
    assert clk.paused is True
    assert clk.speed == 2.0
    assert clk.effective_speed() == 0.0
    c.post("/sim/control", json={"paused": False})
    assert clk.effective_speed() == 2.0
