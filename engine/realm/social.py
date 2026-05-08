"""Contract + reputation stubs (Primitive 8 / Law 7)."""

from __future__ import annotations

from realm.event_log import log_event
from realm.ids import PartyId
from realm.world import World


def propose_contract_stub(world: World, party_a: PartyId, party_b: PartyId, kind: str) -> dict:
    world.next_contract_seq += 1
    cid = f"c-{world.next_contract_seq}"
    world.contracts.append(
        {
            "id": cid,
            "party_a": str(party_a),
            "party_b": str(party_b),
            "kind": kind,
            "status": "open",
        }
    )
    log_event(
        world,
        "contract_propose",
        f"Contract {cid}: {party_a} ↔ {party_b} ({kind})",
        contract_id=cid,
        party_a=str(party_a),
        party_b=str(party_b),
        contract_kind=kind,
    )
    return {"ok": True, "contract_id": cid}


def honor_contract_stub(world: World, contract_id: str) -> dict:
    for c in world.contracts:
        if c.get("id") != contract_id:
            continue
        if c.get("status") != "open":
            return {"ok": False, "reason": "contract not open"}
        c["status"] = "honored"
        for k in ("party_a", "party_b"):
            p = PartyId(c[k])
            r = world.reputation.setdefault(str(p), {"honored": 0, "breached": 0})
            r["honored"] += 1
        log_event(world, "contract_honor", f"Contract {contract_id} honored", contract_id=contract_id)
        return {"ok": True}
    return {"ok": False, "reason": "contract not found"}
