"""Solo host clock — owns wall-clock pacing of ``advance_tick``.

This is **not** the game calendar (that lives on ``world.tick``). It's the
**scheduler state** for the host loop: paused vs running, speed multiplier
(1×/2×/4×), and the derived seconds-per-tick the loop should sleep.

Public-mode shards ignore this module and run their own fixed 1× loop;
solo and dev tools instantiate / mutate it freely.

Game logic NEVER reads from here — it would break determinism (Law 9).
The only consumer is the host loop and the ``/sim/*`` endpoints.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Final

from realm.core.time_scale import (
    DEFAULT_SPEED_MULTIPLIER,
    REAL_SECONDS_PER_GAME_DAY,
    SPEED_MULTIPLIERS,
    TICKS_PER_GAME_DAY,
    real_seconds_per_tick,
    ticks_per_real_second,
)


@dataclass
class SimClock:
    """Mutable host-side clock state.

    Fields are intentionally simple ints/floats so the state machine is easy
    to inspect from the API and trivial to JSON-serialize for ``/sim/status``.
    """

    paused: bool = False
    speed: float = DEFAULT_SPEED_MULTIPLIER
    # Monotonic counter of tick frames the host emitted (separate from
    # ``world.tick`` so the host can audit "did the loop actually fire?" even
    # if the world rolls back via dev reset).
    frames_emitted: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    # ── State machine ────────────────────────────────────────────────────────
    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self.paused = bool(paused)

    def set_speed(self, speed: float) -> None:
        """Snap ``speed`` to the nearest preset; 0 / negative = paused."""
        with self._lock:
            s = float(speed)
            if s <= 0.0:
                self.paused = True
                return
            # Snap to the nearest preset so UI buttons and headless callers
            # produce the same loop behaviour.
            allowed = [m for m in SPEED_MULTIPLIERS if m > 0.0]
            self.speed = min(allowed, key=lambda m: abs(m - s))
            self.paused = False

    def note_frame(self) -> None:
        with self._lock:
            self.frames_emitted += 1

    # ── Derived ──────────────────────────────────────────────────────────────
    def effective_speed(self) -> float:
        """``0.0`` when paused, else the snapped multiplier."""
        return 0.0 if self.paused else self.speed

    def seconds_per_tick(self) -> float:
        return real_seconds_per_tick(self.effective_speed())

    def ticks_per_second(self) -> float:
        return ticks_per_real_second(self.effective_speed())

    # ── Wire shape ───────────────────────────────────────────────────────────
    def status_dict(self) -> dict[str, object]:
        """JSON-safe snapshot for ``/sim/status`` and tick-frame headers."""
        return {
            "paused": self.paused,
            "speed": float(self.speed),
            "effective_speed": float(self.effective_speed()),
            "seconds_per_tick": (
                float(self.seconds_per_tick())
                if self.effective_speed() > 0.0
                else None
            ),
            "ticks_per_real_second": float(self.ticks_per_second()),
            "ticks_per_game_day": TICKS_PER_GAME_DAY,
            "real_seconds_per_game_day": REAL_SECONDS_PER_GAME_DAY,
            "speed_presets": list(SPEED_MULTIPLIERS),
            "frames_emitted": int(self.frames_emitted),
        }


# Process-wide singleton — one host = one clock. Tests reset it explicitly.
_CLOCK: Final[SimClock] = SimClock()


def get_sim_clock() -> SimClock:
    return _CLOCK


def reset_sim_clock_for_tests() -> None:
    """Restore defaults so a fresh test sees ``running, 1×, no frames``."""
    _CLOCK.paused = False
    _CLOCK.speed = DEFAULT_SPEED_MULTIPLIER
    _CLOCK.frames_emitted = 0
