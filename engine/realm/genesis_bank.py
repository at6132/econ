"""First Bank of the Frontier — NPC bank with reputation-tiered loans.

Sprint 5 — Phase C. The bank is a physical entity on the map: a plot near
the median land coordinate (Phase 7A; was previously anchored near
``pop_hub_e`` before hubs were removed) with a pre-built ``bank_building``.
It never messages the player, never proposes anything; the player clicks
the bank and gets a rates table. Defaults are the only NPC-initiated
action in the whole game and only happen because the player signed a
contract that said so.

Loans are stored as standard contract rows on ``world.contracts`` with
``kind="bank_loan"``. The same data shape is used by Meridian Capital (Phase
D Financier archetype): only the ``lender`` field differs.
"""

from __future__ import annotations

from typing import Final

from realm.event_log import log_event
from realm.ids import PartyId, PlotId
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.world import World


__all__ = [
    "FIRST_BANK_PARTY_ID",
    "FIRST_BANK_DISPLAY_NAME",
    "BANK_STARTING_CASH_CENTS",
    "LOAN_CYCLE_TICKS",
    "BANK_RATE_TIERS",
    "rate_tier_for_reputation",
    "seed_first_bank",
    "apply_bank_loan",
    "repay_bank_loan",
    "tick_bank_loans",
    "active_loans_for_borrower",
    "bank_rates_view",
]


FIRST_BANK_PARTY_ID: Final[PartyId] = PartyId("first_bank")
FIRST_BANK_DISPLAY_NAME: Final[str] = "First Bank of the Frontier"
BANK_STARTING_CASH_CENTS: Final[int] = 50_000_000  # $500,000.00
LOAN_CYCLE_TICKS: Final[int] = 43_200  # 30 game-days


BANK_RATE_TIERS: list[dict] = [
    {
        "tier": "starter",
        "min_honored": 0,
        "max_honored": 2,
        "rate_bps_per_cycle": 1200,
        "max_principal_cents": 200_000,
        "requires_collateral": False,
    },
    {
        "tier": "established",
        "min_honored": 3,
        "max_honored": 9,
        "rate_bps_per_cycle": 800,
        "max_principal_cents": 800_000,
        "requires_collateral": False,
    },
    {
        "tier": "trusted",
        "min_honored": 10,
        "max_honored": None,
        "rate_bps_per_cycle": 600,
        "max_principal_cents": 2_000_000,
        "requires_collateral": False,
    },
]


def rate_tier_for_reputation(honored: int) -> dict:
    """Return the highest-applicable tier for ``honored`` honored contracts."""
    chosen = BANK_RATE_TIERS[0]
    for tier in BANK_RATE_TIERS:
        lo = int(tier["min_honored"])
        hi = tier["max_honored"]
        if honored >= lo and (hi is None or honored <= int(hi)):
            chosen = tier
    return chosen


def bank_rates_view(world: World, party: PartyId | None = None) -> dict:
    """Public rates table for the bank UI."""
    rep = world.reputation.get(str(party) if party else "player", {}) or {}
    honored = int(rep.get("honored", 0))
    current = rate_tier_for_reputation(honored)
    return {
        "tiers": [
            {
                "tier": t["tier"],
                "min_honored": int(t["min_honored"]),
                "max_honored": t["max_honored"],
                "rate_bps_per_cycle": int(t["rate_bps_per_cycle"]),
                "rate_pct_per_cycle": int(t["rate_bps_per_cycle"]) / 100.0,
                "max_principal_cents": int(t["max_principal_cents"]),
                "current_for_party": t["tier"] == current["tier"],
            }
            for t in BANK_RATE_TIERS
        ],
        "cycle_ticks": LOAN_CYCLE_TICKS,
        "honored_for_party": honored,
        "current_tier": current["tier"],
    }


def seed_first_bank(world: World) -> bool:
    """Spawn the bank party + pre-built bank_building near the median land coord."""
    if world.scenario_id != "genesis":
        return False
    if FIRST_BANK_PARTY_ID in world.parties:
        return False
    world.parties.add(FIRST_BANK_PARTY_ID)
    world.reputation[str(FIRST_BANK_PARTY_ID)] = {"honored": 0, "breached": 0}
    world.party_display_names[str(FIRST_BANK_PARTY_ID)] = FIRST_BANK_DISPLAY_NAME
    acct = party_cash_account(FIRST_BANK_PARTY_ID)
    world.ledger.ensure_account(acct)
    tr = world.ledger.transfer(
        debit=system_reserve_account(),
        credit=acct,
        amount_cents=BANK_STARTING_CASH_CENTS,
    )
    if isinstance(tr, MoneyErr):
        return False
    _place_bank_building(world)
    log_event(
        world,
        "first_bank_seeded",
        f"{FIRST_BANK_DISPLAY_NAME} opened with ${BANK_STARTING_CASH_CENTS // 100:,} capital",
        party=str(FIRST_BANK_PARTY_ID),
        starting_cash_cents=int(BANK_STARTING_CASH_CENTS),
    )
    return True


def _place_bank_building(world: World) -> None:
    """Claim an unowned land plot for the bank near the map's geometric centre.

    Phase 7A: the bank used to be placed near ``pop_hub_e``; with hubs removed
    we anchor it on a deterministic point (median land coordinate) so it lands
    in the middle of the populated region without depending on any party.
    """
    from realm.islands import is_ocean_plot

    land_plots = [
        (int(p.x), int(p.y), pid)
        for pid, p in world.plots.items()
        if not is_ocean_plot(world, pid)
    ]
    if not land_plots:
        return
    xs = sorted(c[0] for c in land_plots)
    ys = sorted(c[1] for c in land_plots)
    cx = xs[len(xs) // 2]
    cy = ys[len(ys) // 2]
    nearest: PlotId | None = None
    best_d = 10**9
    for x, y, pid in land_plots:
        p = world.plots[pid]
        if p.owner is not None:
            continue
        d = abs(x - cx) + abs(y - cy)
        if d < best_d:
            best_d = d
            nearest = pid
    if nearest is None:
        return
    plot = world.plots[nearest]
    plot.owner = FIRST_BANK_PARTY_ID
    world.next_building_instance_seq += 1
    instance_id = f"b{world.next_building_instance_seq:06d}"
    world.plot_buildings.append(
        {
            "instance_id": instance_id,
            "condition_bps": 10000,
            "plot_id": str(nearest),
            "party": str(FIRST_BANK_PARTY_ID),
            "building_id": "bank_building",
            "label": "First Bank of the Frontier",
            "cost_cents": 0,
            "build_mode": "simple",
            "completes_at_tick": int(world.tick),
        }
    )
    world.scenario_state.setdefault("bank_plot", str(nearest))


def _principal_share_cents(loan: dict) -> int:
    """Equal-amortising principal share per cycle (rounded; last cycle squares up)."""
    principal = int(loan.get("principal_cents", 0))
    cycles = max(1, int(loan.get("num_cycles", 1)))
    return max(0, principal // cycles)


def cycle_payment_cents(loan: dict) -> int:
    """Per-cycle payment: principal share + flat interest on original principal."""
    rate_bps = int(loan.get("interest_rate_bps", 0))
    principal = int(loan.get("principal_cents", 0))
    interest = (principal * rate_bps) // 10000
    share = _principal_share_cents(loan)
    remaining_principal = principal - share * int(loan.get("payments_made", 0))
    if int(loan.get("payments_made", 0)) + 1 == int(loan.get("num_cycles", 1)):
        share = max(0, remaining_principal)
    return share + interest


def _loan_id(world: World) -> str:
    world.next_contract_seq += 1
    return f"c-{world.next_contract_seq}"


def apply_bank_loan(
    world: World,
    borrower: PartyId,
    principal_cents: int,
    num_cycles: int,
    collateral_plot_id: PlotId | None = None,
    *,
    lender: PartyId | None = None,
    rate_bps_override: int | None = None,
    max_principal_override: int | None = None,
    cycle_ticks: int | None = None,
) -> dict:
    """Apply for a loan from ``lender`` (default: ``first_bank``).

    Approval is automatic if the borrower's reputation tier permits the
    requested principal. The cash moves lender → borrower immediately and a
    standard ``bank_loan`` contract row is created on ``world.contracts``.
    """
    lender_pid = lender or FIRST_BANK_PARTY_ID
    if borrower not in world.parties or lender_pid not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if borrower == lender_pid:
        return {"ok": False, "reason": "borrower and lender must differ"}
    if principal_cents <= 0:
        return {"ok": False, "reason": "principal must be positive"}
    if num_cycles < 1 or num_cycles > 12:
        return {"ok": False, "reason": "num_cycles must be between 1 and 12"}
    rep = world.reputation.get(str(borrower), {}) or {}
    honored = int(rep.get("honored", 0))
    tier = rate_tier_for_reputation(honored)
    max_principal = (
        int(max_principal_override)
        if max_principal_override is not None
        else int(tier["max_principal_cents"])
    )
    if principal_cents > max_principal:
        return {
            "ok": False,
            "reason": (
                f"principal exceeds tier '{tier['tier']}' cap of "
                f"${max_principal / 100:,.2f}"
            ),
        }
    if collateral_plot_id is not None:
        plot = world.plots.get(collateral_plot_id)
        if plot is None or plot.owner != borrower:
            return {"ok": False, "reason": "collateral plot must be owned by borrower"}
    lender_cash = party_cash_account(lender_pid)
    if world.ledger.balance(lender_cash) < principal_cents:
        return {"ok": False, "reason": "lender has insufficient capital"}
    borrower_cash = party_cash_account(borrower)
    world.ledger.ensure_account(borrower_cash)
    tr = world.ledger.transfer(
        debit=lender_cash,
        credit=borrower_cash,
        amount_cents=int(principal_cents),
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    rate_bps = (
        int(rate_bps_override)
        if rate_bps_override is not None
        else int(tier["rate_bps_per_cycle"])
    )
    cy_ticks = int(cycle_ticks) if cycle_ticks is not None else LOAN_CYCLE_TICKS
    loan_id = _loan_id(world)
    loan = {
        "id": loan_id,
        "kind": "bank_loan",
        "status": "active",
        "lender": str(lender_pid),
        "borrower": str(borrower),
        "principal_cents": int(principal_cents),
        "interest_rate_bps": int(rate_bps),
        "cycle_ticks": int(cy_ticks),
        "num_cycles": int(num_cycles),
        "payments_made": 0,
        "missed_payments": 0,
        "next_due_tick": int(world.tick) + cy_ticks,
        "originated_at_tick": int(world.tick),
        "collateral_plot_id": str(collateral_plot_id) if collateral_plot_id else None,
        "tier_at_origination": tier["tier"],
    }
    world.contracts.append(loan)
    log_event(
        world,
        "bank_loan_apply",
        f"{lender_pid} disbursed ${principal_cents / 100:,.2f} loan {loan_id} "
        f"to {borrower} at {rate_bps / 100:.2f}%/cycle × {num_cycles}",
        contract_id=loan_id,
        lender=str(lender_pid),
        borrower=str(borrower),
        principal_cents=int(principal_cents),
        rate_bps=int(rate_bps),
        num_cycles=int(num_cycles),
    )
    return {
        "ok": True,
        "loan_id": loan_id,
        "principal_cents": int(principal_cents),
        "rate_bps_per_cycle": int(rate_bps),
        "num_cycles": int(num_cycles),
        "cycle_ticks": int(cy_ticks),
        "next_due_tick": int(loan["next_due_tick"]),
        "tier": tier["tier"],
        "payment_per_cycle_cents": cycle_payment_cents(loan),
    }


def _find_loan(world: World, loan_id: str) -> dict | None:
    for c in world.contracts:
        if c.get("kind") == "bank_loan" and c.get("id") == loan_id:
            return c
    return None


def repay_bank_loan(world: World, borrower: PartyId, loan_id: str) -> dict:
    """Pay one cycle's interest + principal share."""
    loan = _find_loan(world, loan_id)
    if loan is None:
        return {"ok": False, "reason": "unknown loan"}
    if str(loan.get("borrower")) != str(borrower):
        return {"ok": False, "reason": "not your loan"}
    if loan.get("status") != "active":
        return {"ok": False, "reason": f"loan is {loan.get('status')}"}
    payment = cycle_payment_cents(loan)
    borrower_cash = party_cash_account(borrower)
    if world.ledger.balance(borrower_cash) < payment:
        return {"ok": False, "reason": "insufficient cash for repayment"}
    lender_pid = PartyId(str(loan["lender"]))
    tr = world.ledger.transfer(
        debit=borrower_cash,
        credit=party_cash_account(lender_pid),
        amount_cents=int(payment),
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    loan["payments_made"] = int(loan.get("payments_made", 0)) + 1
    loan["missed_payments"] = max(0, int(loan.get("missed_payments", 0)) - 1)
    if int(loan["payments_made"]) >= int(loan["num_cycles"]):
        loan["status"] = "repaid"
        loan["closed_at_tick"] = int(world.tick)
        rep = world.reputation.setdefault(
            str(borrower), {"honored": 0, "breached": 0}
        )
        rep["honored"] = int(rep.get("honored", 0)) + 1
        log_event(
            world,
            "bank_loan_repaid",
            f"{borrower} repaid loan {loan_id} in full",
            contract_id=loan_id,
            borrower=str(borrower),
            lender=str(loan["lender"]),
        )
    else:
        loan["next_due_tick"] = int(world.tick) + int(loan.get("cycle_ticks", LOAN_CYCLE_TICKS))
        log_event(
            world,
            "bank_loan_payment",
            f"{borrower} paid cycle {loan['payments_made']}/{loan['num_cycles']} on {loan_id}",
            contract_id=loan_id,
            borrower=str(borrower),
            payment_cents=int(payment),
        )
    return {
        "ok": True,
        "loan_id": loan_id,
        "payment_cents": int(payment),
        "payments_made": int(loan["payments_made"]),
        "status": loan["status"],
    }


def tick_bank_loans(world: World) -> None:
    """Detect missed payments, apply reputation damage, claim collateral after 2 misses."""
    for loan in list(world.contracts):
        if loan.get("kind") != "bank_loan":
            continue
        if loan.get("status") != "active":
            continue
        due_at = int(loan.get("next_due_tick", 0))
        if int(world.tick) < due_at:
            continue
        loan["missed_payments"] = int(loan.get("missed_payments", 0)) + 1
        loan["next_due_tick"] = due_at + int(loan.get("cycle_ticks", LOAN_CYCLE_TICKS))
        borrower = str(loan["borrower"])
        rep = world.reputation.setdefault(borrower, {"honored": 0, "breached": 0})
        rep["breached"] = int(rep.get("breached", 0)) + 1
        log_event(
            world,
            "bank_loan_missed",
            f"{borrower} missed payment on {loan['id']} "
            f"(miss #{loan['missed_payments']})",
            contract_id=str(loan["id"]),
            borrower=borrower,
            missed=int(loan["missed_payments"]),
        )
        if int(loan["missed_payments"]) >= 2:
            loan["status"] = "defaulted"
            loan["closed_at_tick"] = int(world.tick)
            coll_id = loan.get("collateral_plot_id")
            if coll_id:
                plot = world.plots.get(PlotId(str(coll_id)))
                lender_pid = PartyId(str(loan["lender"]))
                if plot is not None and str(plot.owner) == borrower:
                    plot.owner = lender_pid
                    log_event(
                        world,
                        "bank_loan_collateral_claimed",
                        f"{lender_pid} claimed collateral plot {coll_id} from {borrower} "
                        f"after default on {loan['id']}",
                        contract_id=str(loan["id"]),
                        borrower=borrower,
                        lender=str(lender_pid),
                        plot_id=str(coll_id),
                    )
                    world.world_feed_log.append(
                        {
                            "tick": int(world.tick),
                            "kind": "world_feed",
                            "feed_source": "bank_loan_default",
                            "message": (
                                f"{lender_pid} claimed plot {coll_id} as collateral "
                                f"after a defaulted loan."
                            ),
                        }
                    )


def active_loans_for_borrower(world: World, borrower: PartyId) -> list[dict]:
    out: list[dict] = []
    for c in world.contracts:
        if c.get("kind") != "bank_loan":
            continue
        if str(c.get("borrower")) != str(borrower):
            continue
        out.append(dict(c))
    return out
