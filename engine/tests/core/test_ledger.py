import pytest

from realm.core.ids import PartyId
from realm.core.ledger import Ledger, MoneyErr, party_cash_account, system_reserve_account


def test_transfer_conserves_total() -> None:
    ledger = Ledger()
    assert ledger.seed_system_reserve(1_000_000).ok is True
    alice = party_cash_account(PartyId("alice"))
    bob = party_cash_account(PartyId("bob"))
    assert ledger.transfer(
        debit=system_reserve_account(),
        credit=alice,
        amount_cents=100_000,
    ).ok is True
    total_after_alice = ledger.total_cents()
    assert ledger.transfer(debit=alice, credit=bob, amount_cents=40_000).ok is True
    assert ledger.total_cents() == total_after_alice


def test_transfer_rejects_overdraft() -> None:
    ledger = Ledger()
    assert ledger.seed_system_reserve(10_000).ok is True
    alice = party_cash_account(PartyId("alice"))
    assert (
        ledger.transfer(
            debit=system_reserve_account(),
            credit=alice,
            amount_cents=5_000,
        ).ok
        is True
    )
    r = ledger.transfer(debit=alice, credit=party_cash_account(PartyId("bob")), amount_cents=9_000)
    assert isinstance(r, MoneyErr)
