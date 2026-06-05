"""Genesis bank — reputation-priced loans for settlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from realm.actions._shared import ActionResult
from realm.core.ids import PartyId
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event
from realm.world import World

_TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY
_DEFAULT_LOAN_WEEKS = 52
_BASE_RATE_BPS = 800
_REPUTATION_RATE_OFFSET_BPS = 1_000
_REPUTATION_RATE_STEP_BPS = 20
_MAX_LOAN_BANK_FRACTION_BPS = 1_000  # 10%
_DEFAULT_INTEREST_MISS_WEEKS = 3

GENESIS_BANK_PARTY_ID = PartyId("genesis_bank")
GENESIS_BANK_DISPLAY_NAME = "Genesis Bank"
GENESIS_BANK_STARTING_CASH_CENTS = 50_000_000


@dataclass(frozen=True, slots=True)
class BankLoan:
    loan_id: str
    borrower: PartyId
    principal_cents: int
    interest_rate_bps: int
    duration_ticks: int
    created_tick: int
    outstanding_cents: int


def _loans_store(world: World) -> list[dict[str, Any]]:
    raw = world.scenario_state.setdefault("bank_loans", [])
    if not isinstance(raw, list):
        world.scenario_state["bank_loans"] = []
        raw = world.scenario_state["bank_loans"]
    return raw


def _next_loan_id(world: World) -> str:
    seq = int(world.scenario_state.setdefault("next_bank_loan_seq", 1))
    world.scenario_state["next_bank_loan_seq"] = seq + 1
    return f"loan-{seq}"


def _loan_to_dict(loan: BankLoan) -> dict[str, Any]:
    return {
        "loan_id": loan.loan_id,
        "borrower": str(loan.borrower),
        "principal_cents": int(loan.principal_cents),
        "interest_rate_bps": int(loan.interest_rate_bps),
        "duration_ticks": int(loan.duration_ticks),
        "created_tick": int(loan.created_tick),
        "outstanding_cents": int(loan.outstanding_cents),
        "missed_interest_weeks": 0,
        "status": "active",
    }


def _interest_rate_bps_for_party(world: World, party: PartyId) -> int:
    honored = int(world.reputation.get(str(party), {}).get("honored", 0))
    rep_component = max(0, _REPUTATION_RATE_OFFSET_BPS - honored * _REPUTATION_RATE_STEP_BPS)
    return _BASE_RATE_BPS + rep_component


def seed_genesis_bank(world: World) -> bool:
    """Seed the genesis bank party with lending capital from the system reserve."""
    if world.scenario_id != "genesis":
        return False
    if GENESIS_BANK_PARTY_ID in world.parties:
        return False
    world.parties.add(GENESIS_BANK_PARTY_ID)
    world.reputation[str(GENESIS_BANK_PARTY_ID)] = {"honored": 0, "breached": 0}
    world.party_display_names[str(GENESIS_BANK_PARTY_ID)] = GENESIS_BANK_DISPLAY_NAME
    bank_acct = party_cash_account(GENESIS_BANK_PARTY_ID)
    world.ledger.ensure_account(bank_acct)
    tr = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=bank_acct,
        amount_cents=GENESIS_BANK_STARTING_CASH_CENTS,
    )
    if isinstance(tr, MoneyErr):
        return False
    log_event(
        world,
        "genesis_bank_seeded",
        f"{GENESIS_BANK_DISPLAY_NAME} funded with ${GENESIS_BANK_STARTING_CASH_CENTS // 100:,}",
        party=str(GENESIS_BANK_PARTY_ID),
        starting_cash_cents=GENESIS_BANK_STARTING_CASH_CENTS,
    )
    return True


def request_loan(world: World, party: PartyId, amount_cents: int) -> ActionResult:
    if amount_cents <= 0:
        return {"ok": False, "reason": "amount must be positive"}
    if party not in world.parties:
        return {"ok": False, "reason": "party missing"}
    if GENESIS_BANK_PARTY_ID not in world.parties:
        return {"ok": False, "reason": "genesis bank unavailable"}

    bank_acct = party_cash_account(GENESIS_BANK_PARTY_ID)
    bank_bal = world.ledger.balance(bank_acct)
    max_loan = min(amount_cents, (bank_bal * _MAX_LOAN_BANK_FRACTION_BPS) // 10_000)
    if max_loan <= 0:
        return {"ok": False, "reason": "bank lending capacity exhausted"}

    borrower_acct = party_cash_account(party)
    tr = world.ledger.transfer(debit=bank_acct, credit=borrower_acct, amount_cents=max_loan)
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}

    rate_bps = _interest_rate_bps_for_party(world, party)
    loan = BankLoan(
        loan_id=_next_loan_id(world),
        borrower=party,
        principal_cents=max_loan,
        interest_rate_bps=rate_bps,
        duration_ticks=_DEFAULT_LOAN_WEEKS * _TICKS_PER_GAME_WEEK,
        created_tick=int(world.tick),
        outstanding_cents=max_loan,
    )
    _loans_store(world).append(_loan_to_dict(loan))
    log_event(
        world,
        "bank_loan_issued",
        f"{party} borrowed ${max_loan / 100:.2f} from genesis bank at {rate_bps / 100:.1f}% APR",
        loan_id=loan.loan_id,
        borrower=str(party),
        principal_cents=max_loan,
        interest_rate_bps=rate_bps,
    )
    return {"ok": True, "loan_id": loan.loan_id, "principal_cents": max_loan}


def tick_loan_repayment(world: World) -> None:
    """Weekly interest charges; force bankruptcy after consecutive missed payments."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_WEEK != 0:
        return

    bank_acct = party_cash_account(GENESIS_BANK_PARTY_ID)
    for row in _loans_store(world):
        if not isinstance(row, dict) or str(row.get("status", "active")) != "active":
            continue
        borrower = PartyId(str(row["borrower"]))
        if borrower not in world.parties:
            row["status"] = "void"
            continue

        outstanding = int(row.get("outstanding_cents", 0))
        if outstanding <= 0:
            row["status"] = "repaid"
            continue

        if int(world.tick) - int(row.get("created_tick", 0)) > int(row.get("duration_ticks", 0)):
            row["status"] = "matured"
            continue

        rate_bps = int(row.get("interest_rate_bps", _BASE_RATE_BPS))
        weekly_interest = max(1, (outstanding * rate_bps) // 10_000 // 52)
        borrower_acct = party_cash_account(borrower)
        if world.ledger.balance(borrower_acct) >= weekly_interest:
            pay = world.ledger.transfer(
                debit=borrower_acct,
                credit=bank_acct,
                amount_cents=weekly_interest,
            )
            if not isinstance(pay, MoneyErr):
                row["missed_interest_weeks"] = 0
                log_event(
                    world,
                    "bank_loan_interest",
                    f"{borrower} paid ${weekly_interest / 100:.2f} interest on {row['loan_id']}",
                    loan_id=str(row["loan_id"]),
                    borrower=str(borrower),
                    interest_cents=weekly_interest,
                )
                continue

        missed = int(row.get("missed_interest_weeks", 0)) + 1
        row["missed_interest_weeks"] = missed
        log_event(
            world,
            "bank_loan_interest_missed",
            f"{borrower} missed interest on {row['loan_id']} ({missed}/{_DEFAULT_INTEREST_MISS_WEEKS})",
            loan_id=str(row["loan_id"]),
            borrower=str(borrower),
            missed_weeks=missed,
        )
        if missed >= _DEFAULT_INTEREST_MISS_WEEKS:
            from realm.genesis.settler_cycle import _retire_party

            row["status"] = "defaulted"
            _retire_party(world, borrower, reason="bankruptcy")
            log_event(
                world,
                "bank_loan_default",
                f"{borrower} defaulted on {row['loan_id']} — forced bankruptcy",
                loan_id=str(row["loan_id"]),
                borrower=str(borrower),
            )
