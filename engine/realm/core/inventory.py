"""Matter inventory — Law 1 (matter conserved on transfers between holders)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Union

from realm.core.ids import MaterialId, PartyId

QUALITY_STANDARD: str = "standard"
QUALITY_TIERS: tuple[str, ...] = ("low", "standard", "high")

# Per-material stock: legacy int (standard only) or quality → qty map.
MaterialStock = Union[int, dict[str, int]]


@dataclass(frozen=True, slots=True)
class MatterOk:
    ok: Literal[True] = True


@dataclass(frozen=True, slots=True)
class MatterErr:
    reason: str
    ok: Literal[False] = False


MatterResult = Union[MatterOk, MatterErr]


def _normalize_bucket(raw: MaterialStock | None) -> dict[str, int]:
    if raw is None:
        return {}
    if isinstance(raw, int):
        return {QUALITY_STANDARD: int(raw)} if int(raw) > 0 else {}
    return {str(q): int(v) for q, v in raw.items() if int(v) > 0}


def _write_bucket(party_stock: dict[MaterialId, MaterialStock], material: MaterialId, bucket: dict[str, int]) -> None:
    if not bucket:
        party_stock.pop(material, None)
    elif len(bucket) == 1 and QUALITY_STANDARD in bucket:
        party_stock[material] = int(bucket[QUALITY_STANDARD])
    else:
        party_stock[material] = dict(bucket)


@dataclass
class Inventory:
    """Per-party material quantities (integer units), optionally by quality tier."""

    stock: dict[PartyId, dict[MaterialId, MaterialStock]] = field(default_factory=dict)

    def qty(
        self,
        party: PartyId,
        material: MaterialId,
        quality: str = QUALITY_STANDARD,
    ) -> int:
        """Get quantity. If quality='any', returns sum across all tiers."""
        bucket = _normalize_bucket(self.stock.get(party, {}).get(material))
        if quality == "any":
            return sum(bucket.values())
        return int(bucket.get(quality, 0))

    def qty_by_quality(self, party: PartyId, material: MaterialId) -> dict[str, int]:
        return dict(_normalize_bucket(self.stock.get(party, {}).get(material)))

    def ensure_party_bucket(self, party: PartyId) -> None:
        """Ensure ``party`` exists in ``stock`` (empty dict). Used when rehydrating saves."""
        self._ensure_party(party)

    def stock_for_party(self, party: PartyId) -> dict[MaterialId, int]:
        """Totals per material (all qualities summed)."""
        out: dict[MaterialId, int] = {}
        for mat, raw in self.stock.get(party, {}).items():
            total = sum(_normalize_bucket(raw).values())
            if total > 0:
                out[mat] = total
        return out

    def parties_with_stock_rows(self) -> list[PartyId]:
        """Parties that have an inventory bucket (possibly empty)."""
        return list(self.stock.keys())

    def _ensure_party(self, party: PartyId) -> dict[MaterialId, MaterialStock]:
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
        quality: str = QUALITY_STANDARD,
    ) -> MatterResult:
        if qty < 0:
            return MatterErr(reason="quantity must be non-negative")
        if qty == 0:
            return MatterOk()
        if self.qty(from_party, material, quality) < qty:
            return MatterErr(reason="insufficient material")
        rm = self.remove(from_party, material, qty, quality=quality)
        if isinstance(rm, MatterErr):
            return rm
        return self.add(to_party, material, qty, quality=quality)

    def add(
        self,
        party: PartyId,
        material: MaterialId,
        qty: int,
        *,
        quality: str = QUALITY_STANDARD,
    ) -> MatterResult:
        """Production output / extraction (designed channel — caller must validate recipe)."""
        if qty < 0:
            return MatterErr(reason="quantity must be non-negative")
        if qty == 0:
            return MatterOk()
        party_stock = self._ensure_party(party)
        bucket = _normalize_bucket(party_stock.get(material))
        bucket[quality] = int(bucket.get(quality, 0)) + int(qty)
        _write_bucket(party_stock, material, bucket)
        return MatterOk()

    def remove(
        self,
        party: PartyId,
        material: MaterialId,
        qty: int,
        *,
        quality: str = QUALITY_STANDARD,
    ) -> MatterResult:
        """Consumption for production inputs."""
        if qty < 0:
            return MatterErr(reason="quantity must be non-negative")
        if qty == 0:
            return MatterOk()
        party_stock = self._ensure_party(party)
        bucket = _normalize_bucket(party_stock.get(material))
        if quality == "any":
            left = int(qty)
            for q in QUALITY_TIERS:
                have = int(bucket.get(q, 0))
                if have <= 0:
                    continue
                take = min(left, have)
                bucket[q] = have - take
                if bucket[q] <= 0:
                    del bucket[q]
                left -= take
                if left <= 0:
                    _write_bucket(party_stock, material, bucket)
                    return MatterOk()
            return MatterErr(reason="insufficient material")
        have = int(bucket.get(quality, 0))
        if have < qty:
            return MatterErr(reason=f"insufficient {quality} {material}")
        bucket[quality] = have - qty
        if bucket[quality] <= 0:
            del bucket[quality]
        _write_bucket(party_stock, material, bucket)
        return MatterOk()

    def remove_any_quality_lifo(
        self,
        party: PartyId,
        material: MaterialId,
        qty: int,
    ) -> tuple[MatterResult, dict[str, int]]:
        """Remove ``qty`` units, preferring lowest quality first. Returns per-tier amounts removed."""
        if qty <= 0:
            return MatterOk(), {}
        party_stock = self._ensure_party(party)
        bucket = _normalize_bucket(party_stock.get(material))
        left = int(qty)
        removed: dict[str, int] = {}
        for q in QUALITY_TIERS:
            have = int(bucket.get(q, 0))
            if have <= 0:
                continue
            take = min(left, have)
            bucket[q] = have - take
            if bucket[q] <= 0:
                del bucket[q]
            removed[q] = int(removed.get(q, 0)) + take
            left -= take
            if left <= 0:
                _write_bucket(party_stock, material, bucket)
                return MatterOk(), removed
        return MatterErr(reason="insufficient material"), {}

    def total_units(self) -> int:
        total = 0
        for party_stock in self.stock.values():
            for raw in party_stock.values():
                total += sum(_normalize_bucket(raw).values())
        return total

    def snapshot(self) -> Mapping[PartyId, Mapping[MaterialId, MaterialStock]]:
        return {p: dict(m) for p, m in self.stock.items()}

    def snapshot_for_save(self) -> Mapping[PartyId, Mapping[str, MaterialStock]]:
        """JSON-friendly material keys for persistence."""
        out: dict[PartyId, dict[str, MaterialStock]] = {}
        for party, mats in self.stock.items():
            out[party] = {str(m): raw for m, raw in mats.items()}
        return out
