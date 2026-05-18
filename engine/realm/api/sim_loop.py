"""Solo host loop — advances ``advance_tick`` at the wall-clock rate ``SimClock``
prescribes, and pushes tick frames to any registered transport (e.g. the
Godot socket connection).

Invariants:
  * Only **one** loop thread per process. Start is idempotent.
  * The loop **does nothing** until at least one subscriber is attached
    (no point ticking solo if the UI isn't listening) AND the world is
    already initialized (do not trigger a multi-minute genesis bootstrap
    from a background thread — the user expects that to happen on their
    explicit "start" click via the first API request).
  * Each ``advance_tick`` runs under ``_state.WORLD_LOCK`` so action
    handlers can't race it.
  * Wall clock affects **only pacing**. ``advance_tick`` reads no host
    time → deterministic per-tick (Law 9).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Final

from realm.api import _state
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.world.sim_clock import get_sim_clock

_log = logging.getLogger("realm.sim_loop")

# Subscriber registry — each entry is a callable ``push(payload_dict)`` that
# delivers a single newline-delimited frame to one client.
_subscribers: list[Callable[[dict[str, Any]], None]] = []
_subscribers_lock = threading.Lock()

_thread: threading.Thread | None = None
_thread_lock = threading.Lock()
_stop_event = threading.Event()

# Sentinel: prevent the loop from busy-looping when paused / no clients.
_IDLE_SLEEP_S: Final[float] = 0.25
# Max real-time slice before we re-read clock state. Even at 4× speed that's
# ~0.6s/tick, so 0.25s granularity gives <10% pacing error and lets pause
# react quickly.
_PACING_GRANULARITY_S: Final[float] = 0.05


def subscribe(push: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
    """Register a push callback; returns an ``unsubscribe`` thunk."""
    with _subscribers_lock:
        _subscribers.append(push)

    def _unsub() -> None:
        with _subscribers_lock:
            if push in _subscribers:
                _subscribers.remove(push)

    return _unsub


def _has_subscribers() -> bool:
    with _subscribers_lock:
        return bool(_subscribers)


def _push_to_all(payload: dict[str, Any]) -> None:
    """Best-effort delivery. Failures are the transport's problem."""
    with _subscribers_lock:
        targets = list(_subscribers)
    for cb in targets:
        try:
            cb(payload)
        except Exception:  # noqa: BLE001 -- transport failures are logged, not fatal
            _log.exception("sim_loop: push callback raised")


def build_tick_frame() -> dict[str, Any]:
    """Tiny per-tick HUD payload. **Cheap** — no serialization of plots."""
    # Cheap read; the loop already holds WORLD_LOCK when calling us.
    world = _state.WORLD  # type: ignore[attr-defined]
    tick = int(world.tick)
    tpd = TICKS_PER_GAME_DAY
    day_index = tick // tpd  # 0-based; UI adds +1
    year_index = day_index // 365
    day_of_year = day_index % 365
    if day_of_year < 91:
        season = "Spring"
    elif day_of_year < 182:
        season = "Summer"
    elif day_of_year < 273:
        season = "Autumn"
    else:
        season = "Winter"

    clk = get_sim_clock()
    return {
        "kind": "tick",
        "tick": tick,
        "game_day": day_index + 1,
        "game_year": year_index + 1,
        "season": season,
        "paused": clk.paused,
        "speed": float(clk.speed),
        "effective_speed": float(clk.effective_speed()),
    }


def _loop_body() -> None:
    """Long-running daemon body. Caller owns ``_stop_event``."""
    clk = get_sim_clock()
    _log.info("sim_loop started")
    while not _stop_event.is_set():
        # 1. Don't tick if no client is attached (solo is a single-seat game).
        if not _has_subscribers():
            _stop_event.wait(_IDLE_SLEEP_S)
            continue

        # 2. Don't trigger a lazy bootstrap from the background. Wait for the
        #    first request handler to materialize ``WORLD`` (the user clicking
        #    Start / Load).
        if not _state.is_world_initialized():
            _stop_event.wait(_IDLE_SLEEP_S)
            continue

        # 3. Paused → sleep with quick wake so resume is snappy.
        if clk.paused or clk.effective_speed() <= 0.0:
            _stop_event.wait(_IDLE_SLEEP_S)
            continue

        target_interval = clk.seconds_per_tick()

        # 4. Advance exactly one tick under the world lock. Record actual cost
        #    so a slow tick doesn't get an additional sleep on top.
        tick_started = time.perf_counter()
        try:
            with _state.WORLD_LOCK:
                from realm.world.tick import advance_tick

                advance_tick(_state.WORLD)  # type: ignore[attr-defined]
                frame = build_tick_frame()
            clk.note_frame()
            _push_to_all(frame)
        except Exception:  # noqa: BLE001 -- loop must survive a bad tick
            _log.exception("sim_loop: advance_tick raised; pausing for safety")
            clk.set_paused(True)
            _push_to_all({"kind": "sim_status", **clk.status_dict(), "error": "advance_tick_failed"})
            continue

        # 5. Sleep the remainder of the tick interval in small slices so that
        #    a speed change / pause reacts within ~50ms.
        elapsed = time.perf_counter() - tick_started
        remaining = target_interval - elapsed
        while remaining > 0.0 and not _stop_event.is_set():
            slice_s = min(_PACING_GRANULARITY_S, remaining)
            if _stop_event.wait(slice_s):
                break
            # Re-read in case the user paused or sped up mid-sleep.
            if clk.paused:
                break
            new_interval = clk.seconds_per_tick()
            if new_interval != target_interval:
                # Resize remaining sleep proportionally so a 1×→4× speed-up
                # cuts the current rest, not just the next tick.
                target_interval = new_interval
                # Re-derive remaining from the original tick start.
                remaining = target_interval - (time.perf_counter() - tick_started)
            else:
                remaining -= slice_s
    _log.info("sim_loop stopped")


def start_sim_loop() -> None:
    """Idempotent: start the daemon thread once per process."""
    global _thread
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop_event.clear()
        t = threading.Thread(target=_loop_body, name="realm-sim-loop", daemon=True)
        t.start()
        _thread = t


def stop_sim_loop(timeout: float = 2.0) -> None:
    """Signal the loop to exit. Returns after the thread joins or ``timeout``."""
    global _thread
    with _thread_lock:
        if _thread is None:
            return
        _stop_event.set()
        _thread.join(timeout=timeout)
        _thread = None
