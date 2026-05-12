"""Deterministic display names for Genesis settler parties (settler_### → persona label)."""

from __future__ import annotations

import random

from realm.ids import PartyId
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

_EXTRA_FIRST = (
    "Rafael",
    "Ines",
    "Tariq",
    "Nadia",
    "Chen",
    "Bruno",
    "Elena",
    "Viktor",
    "Amara",
    "Leo",
)
_EXTRA_EPITHET = (
    "the Brewer",
    "the Chandler",
    "the Factor",
    "the Porter",
    "the Sawyer",
    "the Founder",
    "the Clerk",
    "the Ranger",
    "the Dyer",
    "the Smith's Mate",
)

NAMES: tuple[str, ...] = tuple(f"{a} {b}" for a in _FIRST for b in _EPITHET) + tuple(
    f"{a} {b}" for a in _EXTRA_FIRST for b in _EXTRA_EPITHET
)
assert len(NAMES) == 200


def assign_display_name_for_new_settler(world: World, party: PartyId, *, seq: int) -> None:
    """Pick a display label for a settler spawned after bootstrap (deterministic, avoids dupes when possible)."""
    used = set(world.party_display_names.values())
    idx = (int(world.seed) + seq * 7919 + len(world.party_display_names)) % len(NAMES)
    for k in range(len(NAMES)):
        cand = NAMES[(idx + k) % len(NAMES)]
        if cand not in used:
            world.party_display_names[str(party)] = cand
            return
    world.party_display_names[str(party)] = f"Arrival {seq}"


def assign_settler_display_names(world: World, *, seed: int) -> None:
    """Populate ``world.party_display_names`` for every ``settler_*`` party (stable per world seed)."""
    r = random.Random(int(seed) ^ 0xC001D00D)
    pool = list(NAMES)
    r.shuffle(pool)
    settlers = sorted((p for p in world.parties if str(p).startswith("settler_")), key=str)
    for i, party in enumerate(settlers):
        world.party_display_names[str(party)] = pool[i % len(pool)]
