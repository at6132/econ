"""Strongly-typed identifiers (plain strings at runtime, clarity in signatures)."""

from __future__ import annotations

from typing import NewType

PartyId = NewType("PartyId", str)
PlotId = NewType("PlotId", str)
AccountId = NewType("AccountId", str)
MaterialId = NewType("MaterialId", str)
OrderId = NewType("OrderId", str)
