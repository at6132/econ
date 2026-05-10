"""Matter inventory — Law 1 (matter conserved on transfers between holders)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Union

from realm.ids import MaterialId, PartyId


@dataclass(frozen=True, slots=True)
class MatterOk:
    ok: Literal[True] = True


@dataclass(frozen=True, slots=True)
class MatterErr:
    reason: str
    ok: Literal[False] = False


MatterResult = Union[MatterOk, MatterErr]


@dataclass
class Inventory:
    """Per-party material quantities (integer units)."""

    stock: dict[PartyId, dict[MaterialId, int]] = field(default_factory=dict)

    def qty(self, party: PartyId, material: MaterialId) -> int:
        return self.stock.get(party, {}).get(material, 0)

    def ensure_party_bucket(self, party: PartyId) -> None:
        """Ensure ``party`` exists in ``stock`` (empty dict). Used when rehydrating saves."""
        self._ensure_party(party)

    def stock_for_party(self, party: PartyId) -> dict[MaterialId, int]:
        """Shallow copy of ``party``'s holdings; empty if no bucket has been created yet."""
        return dict(self.stock.get(party, {}))

    def _ensure_party(self, party: PartyId) -> dict[MaterialId, int]:
        if party not in self.stock:
            self.stock[party] = {}
        return self.stock[party]

    def transfer(
        self,
        *,
        material: MaterialId,
        qty: int,
        from_party: PartyId,
        to_party: PartyId,
    ) -> MatterResult:
        if qty < 0:
            return MatterErr(reason="quantity must be non-negative")
        if qty == 0:
            return MatterOk()
        src = self._ensure_party(from_party)
        dst = self._ensure_party(to_party)
        if src.get(material, 0) < qty:
            return MatterErr(reason="insufficient material")
        src[material] = src.get(material, 0) - qty
        dst[material] = dst.get(material, 0) + qty
        if src[material] == 0:
            del src[material]
        return MatterOk()

    def add(self, party: PartyId, material: MaterialId, qty: int) -> MatterResult:
        """Production output / extraction (designed channel — caller must validate recipe)."""
        if qty < 0:
            return MatterErr(reason="quantity must be non-negative")
        bucket = self._ensure_party(party)
        bucket[material] = bucket.get(material, 0) + qty
        return MatterOk()

    def remove(self, party: PartyId, material: MaterialId, qty: int) -> MatterResult:
        """Consumption for production inputs."""
        if qty < 0:
            return MatterErr(reason="quantity must be non-negative")
        if qty == 0:
            return MatterOk()
        bucket = self._ensure_party(party)
        if bucket.get(material, 0) < qty:
            return MatterErr(reason="insufficient material")
        bucket[material] = bucket.get(material, 0) - qty
        if bucket[material] == 0:
            del bucket[material]
        return MatterOk()

    def total_units(self) -> int:
        return sum(sum(m.values()) for m in self.stock.values())

    def snapshot(self) -> Mapping[PartyId, Mapping[MaterialId, int]]:
        return {p: dict(m) for p, m in self.stock.items()}
