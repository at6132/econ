"""Business registration action.

Functions:
  * ``register_business`` — pay registration fee and claim a business name
"""

from __future__ import annotations

from realm.core.ids import PartyId
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.events.event_log import log_event
from realm.world import BusinessRecord, World

BUSINESS_REGISTRATION_FEE_CENTS = 1_000  # $10.00 — Sprint 5 — Phase A
BUSINESS_NAME_MIN_LEN = 3
BUSINESS_NAME_MAX_LEN = 40

_BUSINESS_NAME_ALLOWED_PUNCT = frozenset(" '.&-,")


def _is_valid_business_name(name: str) -> bool:
    """3–40 chars, alphanumeric + spaces + apostrophes only.

    No leading/trailing whitespace; collapsed-but-not-empty internal chars.
    """
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


def _business_name_taken(world: World, name: str) -> bool:
    target = name.casefold().strip()
    for rec in world.business_registry.values():
        if rec.business_name.casefold().strip() == target:
            return True
    return False


def register_business(
    world: World, party: PartyId, name: str, description: str = ""
) -> dict:
    """Register ``party``'s business identity (Sprint 5 — Phase A).

    Charges ``BUSINESS_REGISTRATION_FEE_CENTS`` to the system reserve and
    promotes ``name`` to the authoritative display label via
    ``world.party_display_names``. Idempotent only against the same party
    re-registering the same name; collisions across parties are rejected.
    """
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
