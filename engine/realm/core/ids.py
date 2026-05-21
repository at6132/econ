"""Strongly-typed identifiers (plain strings at runtime, clarity in signatures)."""

from __future__ import annotations

import re
import uuid
from typing import NewType

PartyId = NewType("PartyId", str)
PlotId = NewType("PlotId", str)
AccountId = NewType("AccountId", str)
MaterialId = NewType("MaterialId", str)
OrderId = NewType("OrderId", str)
WorldId = NewType("WorldId", str)

_WORLD_ID_RE = re.compile(r"^w_[0-9a-f]{8,32}$")


def new_world_id() -> WorldId:
    """Allocate a stable identity for a new world (bootstrap only, not tick RNG)."""
    return WorldId(f"w_{uuid.uuid4().hex[:12]}")


def normalize_world_id(raw: str) -> WorldId | None:
    """Return a validated id or ``None`` if ``raw`` is not a supported world id."""
    s = str(raw).strip().lower()
    if not s:
        return None
    if _WORLD_ID_RE.fullmatch(s):
        return WorldId(s)
    return None
