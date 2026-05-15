"""Business registration — Sprint 5 name registry + Phase 10C business entities."""

from __future__ import annotations

from realm.core.ids import PartyId, PlotId
from realm.core.ledger import (
    MoneyErr,
    business_cash_account,
    party_cash_account,
    system_reserve_account,
)
from realm.events.event_log import log_event
from realm.world import BusinessRecord, World

BUSINESS_REGISTRATION_FEE_CENTS = 1_000  # $10.00 — Sprint 5 — Phase A
BUSINESS_NAME_MIN_LEN = 3
BUSINESS_NAME_MAX_LEN = 40

_BUSINESS_NAME_ALLOWED_PUNCT = frozenset(" '.&-,")


def _is_valid_business_name(name: str) -> bool:
    if not isinstance(name, str):
        return False
    stripped = name.strip()
    if stripped != name:
        return False
    if not (BUSINESS_NAME_MIN_LEN <= len(name) <= BUSINESS_NAME_MAX_LEN):
        return False
    for ch in name:
        if ch.isalnum() or ch in _BUSINESS_NAME_ALLOWED_PUNCT:
            continue
        return False
    return True


def _business_name_taken(world: World, name: str, exclude_party: PartyId | None = None) -> bool:
    target = name.casefold().strip()
    for rec in world.business_registry.values():
        if exclude_party is not None and rec.party_id == exclude_party:
            continue
        if rec.business_name.casefold().strip() == target:
            return True
    return False


def register_business(
    world: World,
    party: PartyId,
    name: str,
    description: str = "",
    *,
    template_id: str | None = None,
    registered_plot_ids: tuple[str, ...] | None = None,
) -> dict:
    """Register a business name (Sprint 5) and optionally a Phase 10C entity."""
    if party not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    if not _is_valid_business_name(name):
        return {
            "ok": False,
            "reason": (
                f"name must be {BUSINESS_NAME_MIN_LEN}\u2013{BUSINESS_NAME_MAX_LEN} "
                "characters and contain only letters, digits, spaces, or apostrophes"
            ),
        }
    if not isinstance(description, str) or len(description) > 240:
        return {"ok": False, "reason": "description must be a string \u2264 240 characters"}

    if template_id is not None:
        from realm.economy.businesses import BUSINESS_TEMPLATES, BusinessEntity

        tpl = BUSINESS_TEMPLATES.get(str(template_id))
        if tpl is None:
            return {"ok": False, "reason": "unknown template_id"}
        if not registered_plot_ids:
            return {"ok": False, "reason": "registered_plot_ids required for entity registration"}
        pids: list[PlotId] = []
        for raw in registered_plot_ids:
            pid = PlotId(str(raw))
            plot = world.plots.get(pid)
            if plot is None:
                return {"ok": False, "reason": f"unknown plot {raw}"}
            if plot.owner != party:
                return {"ok": False, "reason": f"party does not own plot {raw}"}
            pids.append(pid)
        for biz in world.businesses.values():
            if biz.owner_party == party and biz.business_name == name:
                return {
                    "ok": True,
                    "party_id": str(party),
                    "business_id": biz.business_id,
                    "business_name": biz.business_name,
                    "already_registered": True,
                }
        if _business_name_taken(world, name, exclude_party=None):
            return {"ok": False, "reason": "business name already taken"}
        cash = party_cash_account(party)
        world.ledger.ensure_account(cash)
        if world.ledger.balance(cash) < BUSINESS_REGISTRATION_FEE_CENTS:
            return {"ok": False, "reason": "insufficient cash for registration fee"}
        tr = world.ledger.transfer(
            debit=cash,
            credit=system_reserve_account(),
            amount_cents=BUSINESS_REGISTRATION_FEE_CENTS,
        )
        if isinstance(tr, MoneyErr):
            return {"ok": False, "reason": tr.reason}
        world.next_business_seq += 1
        bid = f"biz-{world.next_business_seq:05d}"
        world.ledger.ensure_account(business_cash_account(bid))
        ent = BusinessEntity(
            business_id=bid,
            owner_party=party,
            business_name=name,
            business_type_tag=str(tpl.type_tag),
            description=str(description or tpl.description),
            registered_at_tick=int(world.tick),
            registered_plot_ids=tuple(pids),
            sub_account_label="main",
            status="active",
            suspension_reason=None,
            public_profile=True,
            last_viability_check_tick=int(world.tick),
            equity_contract_ids=[],
        )
        world.businesses[bid] = ent
        record = BusinessRecord(
            party_id=party,
            business_name=name,
            description=str(description or tpl.description),
            registered_at_tick=int(world.tick),
        )
        world.business_registry[str(party)] = record
        world.party_display_names[str(party)] = name
        log_event(
            world,
            "business_entity_registered",
            f"Business entity {bid} ({name}) template={template_id}.",
            party=str(party),
            business_id=bid,
        )
        return {
            "ok": True,
            "party_id": str(party),
            "business_id": bid,
            "business_name": name,
            "template_id": str(template_id),
            "registered_plot_ids": [str(x) for x in pids],
            "fee_cents": BUSINESS_REGISTRATION_FEE_CENTS,
        }

    existing = world.business_registry.get(str(party))
    if existing is not None and existing.business_name == name:
        return {
            "ok": True,
            "party_id": str(party),
            "business_name": existing.business_name,
            "description": existing.description,
            "registered_at_tick": int(existing.registered_at_tick),
            "already_registered": True,
        }
    if _business_name_taken(world, name):
        return {"ok": False, "reason": "business name already taken"}
    cash = party_cash_account(party)
    world.ledger.ensure_account(cash)
    if world.ledger.balance(cash) < BUSINESS_REGISTRATION_FEE_CENTS:
        return {"ok": False, "reason": "insufficient cash for registration fee"}
    tr = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=BUSINESS_REGISTRATION_FEE_CENTS,
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    record = BusinessRecord(
        party_id=party,
        business_name=name,
        description=description,
        registered_at_tick=int(world.tick),
    )
    world.business_registry[str(party)] = record
    world.party_display_names[str(party)] = name
    log_event(
        world,
        "business_registered",
        f"A new enterprise registered on the frontier: '{name}'.",
        party=str(party),
        business_name=name,
        fee_cents=BUSINESS_REGISTRATION_FEE_CENTS,
    )
    world.world_feed_log.append(
        {
            "tick": int(world.tick),
            "kind": "world_feed",
            "feed_source": "business_registered",
            "message": f"A new enterprise registered on the frontier: '{name}'.",
            "party": str(party),
            "business_name": name,
        }
    )
    return {
        "ok": True,
        "party_id": str(party),
        "business_name": name,
        "description": description,
        "registered_at_tick": int(world.tick),
        "fee_cents": BUSINESS_REGISTRATION_FEE_CENTS,
    }
