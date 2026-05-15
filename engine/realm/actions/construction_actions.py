"""Phase 10D — construction market (ConstructionOrder contracts)."""

from __future__ import annotations

from typing import Any, Final

from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.inventory import MatterErr
from realm.core.ledger import MoneyErr, contract_escrow_account, party_cash_account, system_reserve_account
from realm.events.event_log import log_event
from realm.economy.pricing import exchange_ask_cents
from realm.population.employment import DEFAULT_WAGE_PER_GAME_DAY_CENTS
from realm.production.buildings import BUILDINGS, build_on_plot
from realm.world import World

_CONSTRUCTION_KIND: Final[str] = "construction_order"


def _next_construction_id(world: World) -> str:
    world.next_contract_seq += 1
    return f"co-{world.next_contract_seq}"


def _labor_days_for(building_id: str) -> int:
    spec = BUILDINGS.get(building_id) or {}
    return int(spec.get("labor_days", 3))


def _building_self_materials(building_id: str) -> dict[str, int]:
    spec = BUILDINGS.get(building_id) or {}
    raw = spec.get("self_materials") or {}
    return {str(k): int(v) for k, v in raw.items()}


def request_construction_quotes(
    world: World,
    client: PartyId,
    plot_id: PlotId,
    building_id: str,
    material_responsibility: str,
) -> list[dict[str, Any]]:
    """Return quoted prices from active construction businesses (UX helper)."""
    if building_id not in BUILDINGS:
        return []
    if material_responsibility not in ("client", "contractor"):
        return []
    labor_days = _labor_days_for(building_id)
    mats = _building_self_materials(building_id)
    out: list[dict[str, Any]] = []
    from realm.economy.businesses import BusinessEntity

    for biz in world.businesses.values():
        if not isinstance(biz, BusinessEntity):
            continue
        if biz.status != "active":
            continue
        if "construction" not in str(biz.business_type_tag).lower():
            continue
        party = PartyId(str(biz.owner_party))
        n_emp = sum(
            1
            for lab in world.laborers.values()
            if lab.employer == party
        )
        if n_emp <= 0:
            continue
        labor_cost = int(DEFAULT_WAGE_PER_GAME_DAY_CENTS * n_emp * labor_days)
        mat_cost = 0
        if material_responsibility == "contractor":
            for mid, q in mats.items():
                px = exchange_ask_cents(world, MaterialId(mid))
                if px is None or px <= 0:
                    px = 100
                mat_cost += int(px) * int(q)
            mat_cost = int(mat_cost * 1.25)
        margin = int((labor_cost + mat_cost) * 0.20)
        quoted = labor_cost + mat_cost + margin
        out.append(
            {
                "firm_party": str(party),
                "business_id": biz.business_id,
                "quoted_price_cents": quoted,
                "labor_days": labor_days,
                "material_responsibility": material_responsibility,
            }
        )
    return out


def accept_construction_quote(
    world: World,
    client: PartyId,
    contractor: PartyId,
    plot_id: PlotId,
    building_id: str,
    quoted_price_cents: int,
    material_responsibility: str,
) -> dict[str, Any]:
    if client not in world.parties or contractor not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    plot = world.plots.get(plot_id)
    if plot is None or plot.owner != client:
        return {"ok": False, "reason": "client must own plot"}
    if building_id not in BUILDINGS:
        return {"ok": False, "reason": "unknown building"}
    if material_responsibility not in ("client", "contractor"):
        return {"ok": False, "reason": "invalid material_responsibility"}
    if quoted_price_cents <= 0:
        return {"ok": False, "reason": "invalid quote"}
    deposit = max(1, int(quoted_price_cents * 25 // 100))
    cid = _next_construction_id(world)
    esc = contract_escrow_account(cid)
    world.ledger.ensure_account(esc)
    cash_c = party_cash_account(client)
    world.ledger.ensure_account(cash_c)
    tr = world.ledger.transfer(debit=cash_c, credit=esc, amount_cents=deposit)
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    deadline = int(world.tick) + 14 * 1440
    world.contracts.append(
        {
            "id": cid,
            "kind": _CONSTRUCTION_KIND,
            "client_party": str(client),
            "contractor_party": str(contractor),
            "plot_id": str(plot_id),
            "building_id": building_id,
            "quoted_price_cents": int(quoted_price_cents),
            "deposit_cents": int(deposit),
            "material_responsibility": material_responsibility,
            "deadline_tick": deadline,
            "status": "pending",
            "started_at_tick": None,
            "completed_at_tick": None,
        }
    )
    log_event(
        world,
        "construction_order_created",
        f"{client} hired {contractor} for {building_id} on {plot_id}",
        contract_id=cid,
    )
    return {"ok": True, "contract_id": cid, "deposit_cents": deposit, "deadline_tick": deadline}


def validate_construction_order_for_contractor_build(
    world: World,
    contractor: PartyId,
    plot_id: PlotId,
    building_id: str,
    construction_order_id: str,
) -> tuple[bool, str | None]:
    for c in world.contracts:
        if str(c.get("id")) != str(construction_order_id):
            continue
        if c.get("kind") != _CONSTRUCTION_KIND:
            return (False, "not a construction order")
        if str(c.get("contractor_party")) != str(contractor):
            return (False, "not the contractor on this order")
        if str(c.get("plot_id")) != str(plot_id):
            return (False, "plot mismatch")
        if str(c.get("building_id")) != str(building_id):
            return (False, "building mismatch")
        if str(c.get("status", "")) not in ("pending", "in_progress"):
            return (False, "order not active")
        return (True, None)
    return (False, "order not found")


def complete_construction_job(
    world: World, contractor: PartyId, order_id: str
) -> dict[str, Any]:
    for c in world.contracts:
        if str(c.get("id")) != str(order_id):
            continue
        if c.get("kind") != _CONSTRUCTION_KIND:
            return {"ok": False, "reason": "not a construction order"}
        if str(c.get("contractor_party")) != str(contractor):
            return {"ok": False, "reason": "not the contractor"}
        if str(c.get("status", "")) not in ("pending", "in_progress"):
            return {"ok": False, "reason": "invalid status"}
        client = PartyId(str(c["client_party"]))
        plot_id = PlotId(str(c["plot_id"]))
        building_id = str(c["building_id"])
        quoted = int(c["quoted_price_cents"])
        deposit = int(c["deposit_cents"])
        mode = str(c["material_responsibility"])
        mats = _building_self_materials(building_id)
        if mode == "contractor":
            for mid, q in mats.items():
                if world.inventory.qty(contractor, MaterialId(mid)) < int(q):
                    return {"ok": False, "reason": f"contractor missing {mid}"}
            for mid, q in mats.items():
                rm = world.inventory.remove(contractor, MaterialId(mid), int(q))
                if isinstance(rm, MatterErr):
                    return {"ok": False, "reason": rm.reason}
        else:
            for mid, q in mats.items():
                if world.inventory.qty(client, MaterialId(mid)) < int(q):
                    return {"ok": False, "reason": f"client missing {mid}"}
            for mid, q in mats.items():
                rm = world.inventory.remove(client, MaterialId(mid), int(q))
                if isinstance(rm, MatterErr):
                    return {"ok": False, "reason": rm.reason}
        res = build_on_plot(
            world,
            contractor,
            plot_id,
            building_id,
            build_mode="self_contract",
            construction_order_id=str(order_id),
        )
        if not res.get("ok"):
            return res
        remainder = max(0, quoted - deposit)
        esc = contract_escrow_account(str(order_id))
        cc = party_cash_account(client)
        fc = party_cash_account(contractor)
        world.ledger.ensure_account(fc)
        if remainder > 0:
            tr1 = world.ledger.transfer(debit=cc, credit=fc, amount_cents=remainder)
            if isinstance(tr1, MoneyErr):
                return {"ok": False, "reason": tr1.reason}
        tr2 = world.ledger.transfer(debit=esc, credit=fc, amount_cents=deposit)
        if isinstance(tr2, MoneyErr):
            return {"ok": False, "reason": tr2.reason}
        c["status"] = "complete"
        c["completed_at_tick"] = int(world.tick)
        log_event(
            world,
            "construction_complete",
            f"{contractor} completed {building_id} for {client}",
            contract_id=str(order_id),
        )
        return {"ok": True, "contract_id": str(order_id)}
    return {"ok": False, "reason": "order not found"}


def tick_construction_orders(world: World) -> None:
    """Default missed-deadline: deposit returns to client."""
    t = int(world.tick)
    for c in world.contracts:
        if c.get("kind") != _CONSTRUCTION_KIND:
            continue
        if str(c.get("status", "")) not in ("pending", "in_progress"):
            continue
        if t <= int(c.get("deadline_tick", t)):
            continue
        cid = str(c.get("id", ""))
        deposit = int(c.get("deposit_cents", 0))
        client = PartyId(str(c["client_party"]))
        esc = contract_escrow_account(cid)
        cc = party_cash_account(client)
        if deposit > 0 and world.ledger.balance(esc) >= deposit:
            world.ledger.transfer(debit=esc, credit=cc, amount_cents=deposit)
        c["status"] = "defaulted"
        log_event(
            world,
            "construction_defaulted",
            f"Construction {cid} missed deadline — deposit returned to {client}",
            contract_id=cid,
        )


def tick_construction_firms(world: World) -> None:
    """Daily: construction-type businesses try to complete one pending order."""
    if int(world.tick) <= 0:
        return
    if int(world.tick) % 1440 != 0:
        return
    from realm.economy.businesses import BusinessEntity

    for biz in world.businesses.values():
        if not isinstance(biz, BusinessEntity):
            continue
        if biz.status != "active":
            continue
        if "construction" not in str(biz.business_type_tag).lower():
            continue
        party = PartyId(str(biz.owner_party))
        pending = [
            x
            for x in world.contracts
            if x.get("kind") == _CONSTRUCTION_KIND
            and str(x.get("contractor_party")) == str(party)
            and str(x.get("status", "")) == "pending"
        ]
        if not pending:
            continue
        job = max(pending, key=lambda o: int(o.get("quoted_price_cents", 0)))
        done = complete_construction_job(world, party, str(job["id"]))
        if not done.get("ok"):
            continue
