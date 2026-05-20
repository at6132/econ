"""Insurance, secondary loan market, and land-lease contracts."""

from __future__ import annotations

from typing import Any, Final

from realm.events.event_log import log_event
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import MoneyErr, party_cash_account
from realm.infrastructure.power_grid import plot_has_grid_capacity
from realm.population.laborers import TICKS_PER_GAME_DAY
from realm.world import World

TICKS_PER_7_GAME_DAYS: Final[int] = 7 * TICKS_PER_GAME_DAY

VALID_INSURANCE_EVENTS: frozenset[str] = frozenset(
    {
        "mine_collapse",
        "building_degraded",
        "epidemic",
        "storm",
        "drought",
        "seismic_event",
        "flood",
        "route_blocked",
    }
)


def propose_insurance(
    world: World,
    insurer: PartyId,
    insured: PartyId,
    covered_event_kind: str,
    covered_plot_id: str | None,
    payout_cents: int,
    premium_per_7days_cents: int,
    duration_ticks: int,
) -> dict:
    if covered_event_kind not in VALID_INSURANCE_EVENTS:
        return {
            "ok": False,
            "reason": f"unknown covered_event_kind; valid: {sorted(VALID_INSURANCE_EVENTS)}",
        }
    if payout_cents <= 0 or premium_per_7days_cents <= 0 or duration_ticks < TICKS_PER_7_GAME_DAYS:
        return {"ok": False, "reason": "invalid payout, premium, or duration"}
    if insurer not in world.parties or insured not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if insurer == insured:
        return {"ok": False, "reason": "insurer and insured must differ"}
    world.next_contract_seq += 1
    cid = f"c-{world.next_contract_seq}"
    world.contracts.append(
        {
            "id": cid,
            "kind": "insurance",
            "status": "proposed",
            "insurer": str(insurer),
            "insured": str(insured),
            "covered_event_kind": str(covered_event_kind),
            "covered_plot_id": str(covered_plot_id) if covered_plot_id else None,
            "payout_cents": int(payout_cents),
            "premium_per_7days_cents": int(premium_per_7days_cents),
            "duration_ticks": int(duration_ticks),
            "proposed_at_tick": int(world.tick),
        }
    )
    log_event(world, "insurance_propose", f"Insurance {cid} proposed", contract_id=cid)
    return {"ok": True, "contract_id": cid}


def accept_insurance(world: World, insured: PartyId, contract_id: str) -> dict:
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "insurance" or c.get("status") != "proposed":
            return {"ok": False, "reason": "not a proposed insurance contract"}
        if PartyId(str(c["insured"])) != insured:
            return {"ok": False, "reason": "not the insured party"}
        prem = int(c["premium_per_7days_cents"])
        ins = PartyId(str(c["insurer"]))
        ic = party_cash_account(insured)
        oc = party_cash_account(ins)
        tr = world.ledger.transfer(debit=ic, credit=oc, amount_cents=prem)
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}
        c["status"] = "active"
        c["expires_tick"] = int(world.tick) + int(c["duration_ticks"])
        c["next_premium_tick"] = int(world.tick) + TICKS_PER_7_GAME_DAYS
        log_event(world, "insurance_accept", f"Insurance {contract_id} active", contract_id=contract_id)
        return {"ok": True, "expires_tick": c["expires_tick"]}
    return {"ok": False, "reason": "contract not found"}


def tick_insurance_contracts(world: World) -> None:
    """Collect periodic premiums and expire policies."""
    t = int(world.tick)
    for c in world.contracts:
        if c.get("kind") != "insurance" or c.get("status") != "active":
            continue
        exp = int(c.get("expires_tick", t + 1))
        if t >= exp:
            c["status"] = "expired"
            log_event(world, "insurance_expired", f"Insurance {c['id']} expired", contract_id=c["id"])
            continue
        nxt = int(c.get("next_premium_tick", t + 1))
        if t < nxt:
            continue
        ins = PartyId(str(c["insured"]))
        insr = PartyId(str(c["insurer"]))
        prem = int(c["premium_per_7days_cents"])
        ic = party_cash_account(ins)
        oc = party_cash_account(insr)
        tr = world.ledger.transfer(debit=ic, credit=oc, amount_cents=prem)
        if isinstance(tr, MoneyErr):
            c["status"] = "breached"
            log_event(
                world,
                "insurance_breach_nonpay",
                f"Insurance {c['id']}: premium unpaid",
                contract_id=c["id"],
            )
            continue
        c["next_premium_tick"] = t + TICKS_PER_7_GAME_DAYS


def tick_insurance_payouts(world: World) -> None:
    """Match recent feed lines to active policies once per game-day."""
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return
    t = int(world.tick)
    recent: list[dict[str, Any]] = [
        e for e in world.event_log if t - int(e.get("tick", 0)) <= TICKS_PER_GAME_DAY
    ]
    for c in list(world.contracts):
        if c.get("kind") != "insurance" or c.get("status") != "active":
            continue
        covered = str(c.get("covered_event_kind", ""))
        plot_filter = c.get("covered_plot_id")
        insured_s = str(c.get("insured", ""))
        for e in recent:
            if str(e.get("kind", "")) == "world_feed":
                et = str(e.get("event_type", ""))
            else:
                et = str(e.get("kind", ""))
            if et != covered:
                continue
            party_hit = str(e.get("party", "") or "")
            if party_hit and party_hit != insured_s:
                continue
            if plot_filter:
                ep = str(e.get("plot_id", "") or "")
                if ep and ep != str(plot_filter):
                    continue
            payout = int(c["payout_cents"])
            src = party_cash_account(PartyId(str(c["insurer"])))
            dst = party_cash_account(PartyId(insured_s))
            tr = world.ledger.transfer(debit=src, credit=dst, amount_cents=payout)
            if not isinstance(tr, MoneyErr):
                c["status"] = "paid_out"
                log_event(
                    world,
                    "insurance_payout",
                    f"Insurance {c['id']}: paid {payout}¢ after {covered}",
                    contract_id=c["id"],
                    payout_cents=payout,
                )
            break


def list_loan_for_sale(world: World, seller: PartyId, contract_id: str, ask_cents: int) -> dict:
    if ask_cents <= 0:
        return {"ok": False, "reason": "ask_cents must be positive"}
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "loan" or c.get("status") != "active":
            return {"ok": False, "reason": "loan not active"}
        if PartyId(str(c["lender"])) != seller:
            return {"ok": False, "reason": "not your loan"}
        lm = world.scenario_state.setdefault("loan_market", [])
        if not isinstance(lm, list):
            world.scenario_state["loan_market"] = []
            lm = world.scenario_state["loan_market"]
        lm.append(
            {
                "contract_id": contract_id,
                "seller": str(seller),
                "face_value_cents": int(c["repay_cents"]),
                "ask_cents": int(ask_cents),
                "listed_at_tick": int(world.tick),
            }
        )
        log_event(world, "loan_listed_for_sale", f"Loan {contract_id} listed", contract_id=contract_id)
        return {"ok": True}
    return {"ok": False, "reason": "loan not found"}


def buy_loan(world: World, buyer: PartyId, contract_id: str) -> dict:
    lm = world.scenario_state.get("loan_market", [])
    if not isinstance(lm, list):
        return {"ok": False, "reason": "loan not on secondary market"}
    listing = next((x for x in lm if str(x.get("contract_id")) == contract_id), None)
    if listing is None:
        return {"ok": False, "reason": "loan not on secondary market"}
    ask = int(listing["ask_cents"])
    seller = PartyId(str(listing["seller"]))
    bc = party_cash_account(buyer)
    sc = party_cash_account(seller)
    tr = world.ledger.transfer(debit=bc, credit=sc, amount_cents=ask)
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    for c in world.contracts:
        if c.get("id") == contract_id and c.get("kind") == "loan":
            c["lender"] = str(buyer)
            break
    lm.remove(listing)
    log_event(world, "loan_sold", f"Loan {contract_id} sold to {buyer}", contract_id=contract_id, buyer=str(buyer))
    return {"ok": True, "paid_cents": ask}


def propose_land_lease(
    world: World,
    lessor: PartyId,
    lessee: PartyId,
    plot_id: PlotId,
    rent_per_7days_cents: int,
    duration_ticks: int,
) -> dict:
    plot = world.plots.get(plot_id)
    if plot is None or plot.owner != lessor:
        return {"ok": False, "reason": "not your plot"}
    if rent_per_7days_cents <= 0 or duration_ticks < TICKS_PER_7_GAME_DAYS:
        return {"ok": False, "reason": "invalid rent or duration"}
    if lessor not in world.parties or lessee not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    for c in world.contracts:
        if c.get("kind") == "land_lease" and str(c.get("plot_id")) == str(plot_id):
            if c.get("status") == "active":
                return {"ok": False, "reason": "plot already leased"}
    world.next_contract_seq += 1
    cid = f"c-{world.next_contract_seq}"
    world.contracts.append(
        {
            "id": cid,
            "kind": "land_lease",
            "status": "proposed",
            "lessor": str(lessor),
            "lessee": str(lessee),
            "plot_id": str(plot_id),
            "rent_per_7days_cents": int(rent_per_7days_cents),
            "duration_ticks": int(duration_ticks),
            "proposed_at_tick": int(world.tick),
        }
    )
    return {"ok": True, "contract_id": cid}


def accept_land_lease(world: World, lessee: PartyId, contract_id: str) -> dict:
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("kind") != "land_lease" or c.get("status") != "proposed":
            return {"ok": False, "reason": "lease not awaiting acceptance"}
        if PartyId(str(c["lessee"])) != lessee:
            return {"ok": False, "reason": "not the lessee"}
        c["status"] = "active"
        c["expires_tick"] = int(world.tick) + int(c["duration_ticks"])
        c["next_rent_tick"] = int(world.tick) + TICKS_PER_7_GAME_DAYS
        rights = world.scenario_state.setdefault("plot_lease_rights", {})
        if not isinstance(rights, dict):
            world.scenario_state["plot_lease_rights"] = {}
            rights = world.scenario_state["plot_lease_rights"]
        rights[str(c["plot_id"])] = {
            "lessee": str(lessee),
            "expires_tick": int(c["expires_tick"]),
        }
        log_event(world, "land_lease_accepted", f"Lease {contract_id} active", contract_id=contract_id)
        return {"ok": True, "expires_tick": c["expires_tick"]}
    return {"ok": False, "reason": "lease not found"}


def tick_land_lease_contracts(world: World) -> None:
    t = int(world.tick)
    rights = world.scenario_state.setdefault("plot_lease_rights", {})
    if not isinstance(rights, dict):
        world.scenario_state["plot_lease_rights"] = {}
        rights = world.scenario_state["plot_lease_rights"]
    for c in list(world.contracts):
        if c.get("kind") != "land_lease" or c.get("status") != "active":
            continue
        pid = str(c.get("plot_id", ""))
        exp = int(c.get("expires_tick", t + 1))
        if t >= exp:
            c["status"] = "expired"
            if pid in rights:
                del rights[pid]
            log_event(world, "land_lease_expired", f"Lease {c['id']} ended", contract_id=c["id"])
            continue
        nxt = int(c.get("next_rent_tick", t + 1))
        if t < nxt:
            continue
        rent = int(c["rent_per_7days_cents"])
        lessee = PartyId(str(c["lessee"]))
        lessor = PartyId(str(c["lessor"]))
        lc = party_cash_account(lessee)
        oc = party_cash_account(lessor)
        tr = world.ledger.transfer(debit=lc, credit=oc, amount_cents=rent)
        if isinstance(tr, MoneyErr):
            c["status"] = "breached"
            if pid in rights:
                del rights[pid]
            log_event(world, "land_lease_breach", f"Lease {c['id']}: rent unpaid", contract_id=c["id"])
            continue
        c["next_rent_tick"] = t + TICKS_PER_7_GAME_DAYS


def tick_secondary_instruments(world: World) -> None:
    tick_insurance_contracts(world)
    tick_insurance_payouts(world)
    tick_land_lease_contracts(world)


def validate_service_delivery(world: World, c: dict[str, Any]) -> str | None:
    """Return breach reason if provider cannot deliver, else None."""
    service_id = str(c.get("service_id", ""))
    provider = PartyId(str(c["provider"]))
    params: dict[str, Any] = dict(c.get("service_params") or {})
    if service_id == "route_access":
        route_key = str(params.get("route_key", ""))
        if route_key:
            ops = world.scenario_state.get("route_operators", {})
            if not isinstance(ops, dict):
                return "provider no longer operates this route"
            entries = ops.get(route_key) or []
            if not any(str(e.get("operator_party")) == str(provider) for e in entries if isinstance(e, dict)):
                return "provider no longer operates this route"
    elif service_id == "power_supply":
        plot_id_s = str(params.get("plot_id", ""))
        if plot_id_s:
            if not plot_has_grid_capacity(world, PlotId(plot_id_s)):
                return "plot is no longer powered by provider"
    elif service_id == "labor_supply":
        min_count = int(params.get("min_laborers", 1))
        actual = sum(1 for lab in world.laborers.values() if str(lab.employer) == str(provider))
        if actual < min_count:
            return f"provider has {actual} laborers, promised {min_count}"
    return None
