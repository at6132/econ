"""SimClock state machine + time_scale conversion helpers."""

from __future__ import annotations

import math

import pytest

from realm.core.time_scale import (
    REAL_SECONDS_PER_GAME_DAY,
    REAL_SECONDS_PER_TICK_AT_1X,
    SPEED_MULTIPLIERS,
    TICKS_PER_GAME_DAY,
    TICKS_PER_REAL_SECOND_AT_1X,
    real_seconds_per_tick,
    ticks_per_real_second,
)
from realm.world.sim_clock import (
    SimClock,
    get_sim_clock,
    reset_sim_clock_for_tests,
)


def test_canon_one_real_hour_equals_one_game_day() -> None:
    assert TICKS_PER_GAME_DAY == 1440
    assert REAL_SECONDS_PER_GAME_DAY == 3600
    assert math.isclose(TICKS_PER_REAL_SECOND_AT_1X, 0.4)
    assert math.isclose(REAL_SECONDS_PER_TICK_AT_1X, 2.5)


def test_paused_real_seconds_per_tick_is_inf() -> None:
    assert math.isinf(real_seconds_per_tick(0.0))
    assert ticks_per_real_second(0.0) == 0.0


def test_speed_multipliers_scale_pacing() -> None:
    # 2× speed → half a tick interval; 4× → quarter.
    assert math.isclose(real_seconds_per_tick(2.0), REAL_SECONDS_PER_TICK_AT_1X / 2.0)
    assert math.isclose(real_seconds_per_tick(4.0), REAL_SECONDS_PER_TICK_AT_1X / 4.0)
    assert math.isclose(ticks_per_real_second(2.0), TICKS_PER_REAL_SECOND_AT_1X * 2.0)


def test_simclock_defaults_to_running_at_1x() -> None:
    clk = SimClock()
    assert not clk.paused
    assert clk.speed == 1.0
    assert clk.effective_speed() == 1.0


def test_simclock_set_speed_snaps_to_presets() -> None:
    clk = SimClock()
    clk.set_speed(3.0)
    assert clk.speed in SPEED_MULTIPLIERS
    # 3.0 is equidistant between 2 and 4 → snap to either is fine, just must
    # be a valid preset and resume from paused.
    assert clk.speed >= 2.0
    assert not clk.paused


def test_simclock_zero_speed_pauses() -> None:
    clk = SimClock()
    clk.set_speed(0.0)
    assert clk.paused
    assert clk.effective_speed() == 0.0


def test_simclock_set_paused_does_not_change_speed() -> None:
    clk = SimClock()
    clk.set_speed(2.0)
    clk.set_paused(True)
    assert clk.paused
    # Speed preserved so "resume" returns to the chosen rate.
    assert clk.speed == 2.0
    clk.set_paused(False)
    assert clk.effective_speed() == 2.0


def test_status_dict_is_json_safe() -> None:
    import json

    clk = SimClock()
    clk.set_speed(2.0)
    clk.note_frame()
    payload = clk.status_dict()
    json.dumps(payload)  # round-trip
    assert payload["ticks_per_game_day"] == TICKS_PER_GAME_DAY
    assert payload["frames_emitted"] == 1
    assert payload["speed"] == 2.0
    assert payload["paused"] is False


def test_status_dict_paused_has_none_seconds_per_tick() -> None:
    clk = SimClock()
    clk.set_paused(True)
    assert clk.status_dict()["seconds_per_tick"] is None


def test_global_singleton_reset() -> None:
    clk = get_sim_clock()
    clk.set_speed(4.0)
    clk.note_frame()
    reset_sim_clock_for_tests()
    fresh = get_sim_clock()
    assert fresh is clk  # same object
    assert fresh.speed == 1.0
    assert fresh.frames_emitted == 0
    assert not fresh.paused


@pytest.mark.parametrize("mult", [m for m in SPEED_MULTIPLIERS if m > 0.0])
def test_loop_interval_lands_in_expected_band(mult: float) -> None:
    # The whole point: at 1× a tick should sleep ~2.5s. At 4× ~0.625s.
    s = real_seconds_per_tick(mult)
    assert s > 0.0
    assert s == pytest.approx(REAL_SECONDS_PER_TICK_AT_1X / mult)
