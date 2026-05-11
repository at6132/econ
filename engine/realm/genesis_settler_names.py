"""Deterministic display names for Genesis settler parties (settler_### → persona label)."""

from __future__ import annotations

import random

from realm.world import World

_FIRST = (
    "Aman",
    "Petra",
    "Olu",
    "Mireya",
    "Kaito",
    "Sofia",
    "Dimitri",
    "Yara",
    "Jonah",
    "Helen",
)

_EPITHET = (
    "the Smith",
    "of the Vale",
    "the Mariner",
    "the Miller",
    "the Cooper",
    "the Carter",
    "the Mason",
    "the Tanner",
    "the Weaver",
    "the Drover",
)

NAMES: tuple[str, ...] = tuple(f"{a} {b}" for a in _FIRST for b in _EPITHET)
assert len(NAMES) == 100


def assign_settler_display_names(world: World, *, seed: int) -> None:
    """Populate ``world.party_display_names`` for every ``settler_*`` party (stable per world seed)."""
    r = random.Random(int(seed) ^ 0xC001D00D)
    pool = list(NAMES)
    r.shuffle(pool)
    settlers = sorted((p for p in world.parties if str(p).startswith("settler_")), key=str)
    for i, party in enumerate(settlers):
        world.party_display_names[str(party)] = pool[i % len(pool)]
