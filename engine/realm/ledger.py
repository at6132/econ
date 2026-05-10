"""Money ledger — Primitive 5 / Law 1. All balance changes go through here."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Union

from realm.ids import AccountId, PartyId


@dataclass(frozen=True, slots=True)
class MoneyOk:
    ok: Literal[True] = True


@dataclass(frozen=True, slots=True)
class MoneyErr:
    reason: str
    ok: Literal[False] = False


MoneyResult = Union[MoneyOk, MoneyErr]


@dataclass
class Ledger:
    """Integer cents in every account; no floats in money paths."""

    balances: dict[AccountId, int] = field(default_factory=dict)

    def balance(self, account: AccountId) -> int:
        return self.balances.get(account, 0)

    def ensure_account(self, account: AccountId) -> None:
        if account not in self.balances:
            self.balances[account] = 0

    def seed_system_reserve(self, amount_cents: int) -> MoneyResult:
        """
        One-time bootstrap: system reserve holds all not-yet-allocated currency.

        After this, only transfers move money until other designed channels are added.
        """
        if amount_cents <= 0:
            return MoneyErr(reason="system reserve must be positive")
        sys = system_reserve_account()
        if self.balance(sys) != 0 and sys in self.balances:
            return MoneyErr(reason="system reserve already seeded")
        self.balances[sys] = amount_cents
        return MoneyOk()

    def transfer(
        self,
        *,
        debit: AccountId,
        credit: AccountId,
        amount_cents: int,
    ) -> MoneyResult:
        if amount_cents < 0:
            return MoneyErr(reason="transfer amount must be non-negative")
        if amount_cents == 0:
            return MoneyOk()
        self.ensure_account(debit)
        self.ensure_account(credit)
        if self.balances[debit] < amount_cents:
            return MoneyErr(reason="insufficient funds")
        self.balances[debit] -= amount_cents
        self.balances[credit] += amount_cents
        return MoneyOk()

    def total_cents(self) -> int:
        return sum(self.balances.values())

    def snapshot(self) -> Mapping[AccountId, int]:
        return dict(self.balances)


def party_cash_account(party: PartyId) -> AccountId:
    return AccountId(f"cash:{party}")


def system_reserve_account() -> AccountId:
    return AccountId("system:reserve")


def market_escrow_account() -> AccountId:
    """Holds cash locked for open limit bids (released on fill or cancel)."""
    return AccountId("system:market_escrow")


def contract_escrow_account(contract_id: str) -> AccountId:
    """Holds buyer deposits for active supply contracts until fulfill or breach."""
    return AccountId(f"system:contract_escrow:{contract_id}")
