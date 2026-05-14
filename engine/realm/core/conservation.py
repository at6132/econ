"""Conservation invariant — Law 1.

The total cents in the ledger and the total material units in the inventory
are conserved across every legal action. These helpers make it cheap to
assert that invariant from tests and from runtime checks (e.g. dev-mode
assertions or the API ``GET /world/health`` endpoint).

NOTE: there is no production code path that *enforces* conservation by
re-running the check after every transfer (that would be O(n) per tick).
The transactional layers in :mod:`realm.core.ledger` and
:mod:`realm.core.inventory` are responsible for *not* introducing money or
matter outside designed channels. These helpers are for verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from realm.core.inventory import Inventory
    from realm.core.ledger import Ledger


@dataclass(frozen=True, slots=True)
class ConservationSnapshot:
    """A point-in-time view of conserved quantities."""

    ledger_total_cents: int
    inventory_total_units: int

    @classmethod
    def of(cls, ledger: Ledger, inventory: Inventory) -> ConservationSnapshot:
        return cls(
            ledger_total_cents=ledger.total_cents(),
            inventory_total_units=inventory.total_units(),
        )


def assert_money_conserved(
    ledger: Ledger,
    expected_total_cents: int,
    *,
    label: str = "",
) -> None:
    """Raise ``AssertionError`` with a descriptive message if money was created/destroyed."""
    actual = ledger.total_cents()
    if actual != expected_total_cents:
        delta = actual - expected_total_cents
        prefix = f"[{label}] " if label else ""
        raise AssertionError(
            f"{prefix}conservation violated: "
            f"started with {expected_total_cents} cents, ended with {actual} "
            f"(delta {delta:+d})"
        )


def assert_matter_conserved(
    inventory: Inventory,
    expected_total_units: int,
    *,
    label: str = "",
) -> None:
    """Raise ``AssertionError`` with a descriptive message if matter was created/destroyed.

    NOTE: matter is NOT conserved across production (recipes consume inputs and emit
    outputs of different materials), nor across spoilage / decay / consumption. Use
    this only for tests of pure transfer paths (markets, p2p trades, contract delivery).
    """
    actual = inventory.total_units()
    if actual != expected_total_units:
        delta = actual - expected_total_units
        prefix = f"[{label}] " if label else ""
        raise AssertionError(
            f"{prefix}matter conservation violated: "
            f"started with {expected_total_units} units, ended with {actual} "
            f"(delta {delta:+d})"
        )
