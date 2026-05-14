"""Sub-accounts and per-account P&L tracking (Sprint 5 — Phase B).

Every party has an implicit primary account ``cash:{party}`` (the canonical
``party_cash_account``). Sub-accounts are additional labelled buckets the
party can move money in and out of for their own bookkeeping — e.g.
``player:reserve`` or ``player:shipping``. They live on the same
authoritative ledger so conservation is preserved.

State storage (in ``world.scenario_state``):
  * ``party_sub_accounts`` — ``{party_id: [label, ...]}`` ordered list of
    custom labels the party created. ``cash`` is always implicit primary,
    not listed here.
  * ``sub_account_history`` — ``{account_id: [{"tick","delta_cents",
    "kind","counterparty"}]}`` capped per-account. Updated by
    ``transfer_own`` and by external callers that want to track flows on a
    specific account (production loop / maintenance hooks are free to opt
    in by calling ``log_sub_account_tx``).
"""

from __future__ import annotations

from typing import Any

from realm.event_log import log_event
from realm.core.ids import PartyId
from realm.core.ledger import AccountId, MoneyErr, party_cash_account
from realm.world import World


__all__ = [
    "PRIMARY_LABEL",
    "TICKS_PER_GAME_DAY",
    "PNL_WINDOW_TICKS",
    "SUB_ACCOUNT_HISTORY_CAP",
    "SUB_ACCOUNT_LABEL_MIN_LEN",
    "SUB_ACCOUNT_LABEL_MAX_LEN",
    "account_id_for",
    "party_sub_account_labels",
    "ensure_primary_account",
    "create_sub_account",
    "transfer_own",
    "log_sub_account_tx",
    "sub_account_history",
    "sub_account_pnl_7day",
    "party_accounts_view",
]


PRIMARY_LABEL: str = "cash"
TICKS_PER_GAME_DAY: int = 1440
PNL_WINDOW_TICKS: int = 7 * TICKS_PER_GAME_DAY
SUB_ACCOUNT_HISTORY_CAP: int = 240  # per account; keeps memory bounded
SUB_ACCOUNT_LABEL_MIN_LEN: int = 2
SUB_ACCOUNT_LABEL_MAX_LEN: int = 24


def _labels_map(world: World) -> dict[str, list[str]]:
    raw = world.scenario_state.setdefault("party_sub_accounts", {})
    if not isinstance(raw, dict):
        world.scenario_state["party_sub_accounts"] = {}
        raw = world.scenario_state["party_sub_accounts"]
    return raw


def _history_map(world: World) -> dict[str, list[dict]]:
    raw = world.scenario_state.setdefault("sub_account_history", {})
    if not isinstance(raw, dict):
        world.scenario_state["sub_account_history"] = {}
        raw = world.scenario_state["sub_account_history"]
    return raw


def account_id_for(party: PartyId, label: str) -> AccountId:
    """Return the canonical ledger ``AccountId`` for ``(party, label)``.

    ``label == "cash"`` collapses to the legacy primary account
    ``cash:{party}`` so existing code paths keep working.
    """
    lbl = label.strip()
    if lbl == PRIMARY_LABEL:
        return party_cash_account(party)
    return AccountId(f"{party}:{lbl}")


def party_sub_account_labels(world: World, party: PartyId) -> list[str]:
    """Custom labels owned by ``party`` (does not include the primary)."""
    raw = _labels_map(world)
    return list(raw.get(str(party)) or [])


def ensure_primary_account(world: World, party: PartyId) -> None:
    """Make sure the primary ``cash:{party}`` account exists on the ledger."""
    world.ledger.ensure_account(party_cash_account(party))


def _is_valid_sub_account_label(label: str) -> bool:
    if not isinstance(label, str):
        return False
    if label.strip() != label:
        return False
    if not (SUB_ACCOUNT_LABEL_MIN_LEN <= len(label) <= SUB_ACCOUNT_LABEL_MAX_LEN):
        return False
    for ch in label:
        if ch.isalnum() or ch in ("_", "-"):
            continue
        return False
    return True


def create_sub_account(world: World, party: PartyId, account_label: str) -> dict:
    """Create a new labelled sub-account for ``party`` (Sprint 5 — Phase B).

    Returns ``{"ok": True, "account_id": str, "label": str, "balance_cents": 0}``
    on success. Idempotent: re-creating an existing label returns
    ``already_exists=True`` without error.
    """
    if party not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    lbl = (account_label or "").strip()
    if lbl == PRIMARY_LABEL:
        return {"ok": False, "reason": "'cash' is the primary account; cannot be re-created"}
    if not _is_valid_sub_account_label(lbl):
        return {
            "ok": False,
            "reason": (
                f"label must be {SUB_ACCOUNT_LABEL_MIN_LEN}\u2013"
                f"{SUB_ACCOUNT_LABEL_MAX_LEN} chars: letters, digits, '_' or '-'"
            ),
        }
    labels = _labels_map(world)
    existing = labels.get(str(party)) or []
    if lbl in existing:
        return {
            "ok": True,
            "already_exists": True,
            "account_id": str(account_id_for(party, lbl)),
            "label": lbl,
            "balance_cents": int(world.ledger.balance(account_id_for(party, lbl))),
        }
    acct = account_id_for(party, lbl)
    world.ledger.ensure_account(acct)
    labels.setdefault(str(party), []).append(lbl)
    log_event(
        world,
        "sub_account_created",
        f"{party} opened sub-account '{lbl}'",
        party=str(party),
        label=lbl,
        account_id=str(acct),
    )
    return {
        "ok": True,
        "account_id": str(acct),
        "label": lbl,
        "balance_cents": 0,
    }


def log_sub_account_tx(
    world: World,
    account_id: AccountId | str,
    *,
    delta_cents: int,
    kind: str,
    counterparty: str | None = None,
) -> None:
    """Append a transaction row for ``account_id`` (Sprint 5 — Phase B).

    ``delta_cents > 0`` is a credit (money in), ``< 0`` is a debit (money out).
    Capped at ``SUB_ACCOUNT_HISTORY_CAP`` entries per account.
    """
    if int(delta_cents) == 0:
        return
    hist = _history_map(world)
    rows = hist.setdefault(str(account_id), [])
    rows.append(
        {
            "tick": int(world.tick),
            "delta_cents": int(delta_cents),
            "kind": str(kind),
            "counterparty": str(counterparty) if counterparty is not None else None,
        }
    )
    if len(rows) > SUB_ACCOUNT_HISTORY_CAP:
        del rows[: len(rows) - SUB_ACCOUNT_HISTORY_CAP]


def transfer_own(
    world: World,
    party: PartyId,
    from_label: str,
    to_label: str,
    cents: int,
) -> dict:
    """Free, instant transfer between two of ``party``'s own accounts."""
    if cents <= 0:
        return {"ok": False, "reason": "amount must be positive"}
    if from_label == to_label:
        return {"ok": False, "reason": "source and destination must differ"}
    if party not in world.parties:
        return {"ok": False, "reason": "unknown party"}
    labels = _labels_map(world).get(str(party)) or []
    for lbl in (from_label, to_label):
        if lbl == PRIMARY_LABEL:
            continue
        if lbl not in labels:
            return {"ok": False, "reason": f"unknown sub-account '{lbl}'"}
    src = account_id_for(party, from_label)
    dst = account_id_for(party, to_label)
    world.ledger.ensure_account(src)
    world.ledger.ensure_account(dst)
    if world.ledger.balance(src) < cents:
        return {"ok": False, "reason": "insufficient funds"}
    tr = world.ledger.transfer(debit=src, credit=dst, amount_cents=int(cents))
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    log_sub_account_tx(
        world,
        src,
        delta_cents=-int(cents),
        kind="transfer_own",
        counterparty=str(dst),
    )
    log_sub_account_tx(
        world,
        dst,
        delta_cents=int(cents),
        kind="transfer_own",
        counterparty=str(src),
    )
    log_event(
        world,
        "transfer_own",
        f"{party} moved ${cents / 100:.2f} from '{from_label}' to '{to_label}'",
        party=str(party),
        from_label=from_label,
        to_label=to_label,
        amount_cents=int(cents),
    )
    return {
        "ok": True,
        "from_label": from_label,
        "to_label": to_label,
        "amount_cents": int(cents),
        "from_balance_cents": int(world.ledger.balance(src)),
        "to_balance_cents": int(world.ledger.balance(dst)),
    }


def sub_account_history(
    world: World, party: PartyId, label: str, *, limit: int = 10
) -> list[dict]:
    """Recent transactions for ``(party, label)`` (newest first)."""
    acct = account_id_for(party, label)
    rows = _history_map(world).get(str(acct), []) or []
    return list(reversed(rows[-int(limit) :]))


def sub_account_pnl_7day(
    world: World, party: PartyId, label: str
) -> dict[str, int]:
    """Rolling 7-day credits / debits / net for the named sub-account."""
    acct = account_id_for(party, label)
    rows = _history_map(world).get(str(acct), []) or []
    cutoff = int(world.tick) - PNL_WINDOW_TICKS
    credits = 0
    debits = 0
    for row in rows:
        if int(row.get("tick", 0)) < cutoff:
            continue
        delta = int(row.get("delta_cents", 0))
        if delta >= 0:
            credits += delta
        else:
            debits += -delta
    return {"credits_cents": credits, "debits_cents": debits, "net_cents": credits - debits}


def party_accounts_view(world: World, party: PartyId) -> list[dict]:
    """All accounts for ``party`` (primary + sub-accounts) with balances + 7-day P&L."""
    ensure_primary_account(world, party)
    out: list[dict] = []
    primary_id = account_id_for(party, PRIMARY_LABEL)
    out.append(
        {
            "label": PRIMARY_LABEL,
            "account_id": str(primary_id),
            "balance_cents": int(world.ledger.balance(primary_id)),
            "is_primary": True,
            "pnl_7day": sub_account_pnl_7day(world, party, PRIMARY_LABEL),
        }
    )
    for lbl in party_sub_account_labels(world, party):
        acct = account_id_for(party, lbl)
        out.append(
            {
                "label": lbl,
                "account_id": str(acct),
                "balance_cents": int(world.ledger.balance(acct)),
                "is_primary": False,
                "pnl_7day": sub_account_pnl_7day(world, party, lbl),
            }
        )
    return out
