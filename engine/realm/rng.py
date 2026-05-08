"""Deterministic RNG: Law 9 — same tick + purpose → same stream."""

from __future__ import annotations

import hashlib
import random
from typing import Final


def make_rng(tick: int, purpose: str) -> random.Random:
    """
    Build a stdlib Random isolated for (tick, purpose).

    Uses blake2b so we never rely on Python's salted str hash (not stable across runs).
    """
    payload = f"{tick}\0{purpose}".encode("utf-8")
    digest: Final[bytes] = hashlib.blake2b(payload, digest_size=8).digest()
    seed = int.from_bytes(digest, "big")
    return random.Random(seed)
