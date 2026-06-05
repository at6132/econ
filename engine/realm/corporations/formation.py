"""Partnership formation — settlers pool capital and issue equity."""

from __future__ import annotations

from typing import Any

from realm.actions._shared import ActionResult
from realm.agents.settler_identity import (
    SettlerPersonality,
    _party_hash,
    get_settler_personality,
    get_settler_world_model,
)
from realm.core.ids import PartyId
from realm.core.ledger import MoneyErr, party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.corporations.company import (
    Company,
    company_cash_account,
    company_for_party,
    merge_company_eras,
    next_company_id,
    party_plot_ids,
    store_company,
)
from realm.events.event_log import log_event
from realm.world import World

_TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY
PARTNERSHIP_MIN_COMBINED_CASH_CENTS = 500_000
PROPOSER_MIN_CASH_CENTS = 400_000
GREED_THRESHOLD = 0.6
REPUTATION_THRESHOLD = 0.6
FOUNDER_SHARES_EACH = 500

# Primary output material → materials/buildings that benefit from upstream supply.
_MATERIAL_COMPLEMENTS: dict[str, frozenset[str]] = {
    "coal": frozenset({"iron_ingot", "steel_ingot", "iron_ore", "charcoal"}),
    "iron_ore": frozenset({"coal", "iron_ingot", "steel_ingot"}),
    "iron_ingot": frozenset({"coal", "lumber", "iron_ore"}),
    "steel_ingot": frozenset({"coal", "iron_ingot"}),
    "lumber": frozenset({"iron_ingot", "brick", "flour", "coal"}),
    "flour": frozenset({"coal", "lumber"}),
    "brick": frozenset({"lumber", "coal"}),
    "charcoal": frozenset({"iron_ingot", "steel_ingot"}),
}


def _normalized_reputation(world: World, party: PartyId) -> float:
    rep = world.reputation.get(str(party), {})
    if not isinstance(rep, dict):
        return 0.5
    honored = int(rep.get("honored", 0))
    breached = int(rep.get("breached", 0))
    total = honored + breached
    if total <= 0:
        return 0.5
    return honored / total


def _partnership_store(world: World) -> dict[str, Any]:
    raw = world.scenario_state.setdefault("corporations", {})
    if not isinstance(raw, dict):
        world.scenario_state["corporations"] = {}
        raw = world.scenario_state["corporations"]
    pending = raw.setdefault("partnership_pending", [])
    if not isinstance(pending, list):
        raw["partnership_pending"] = []
        pending = raw["partnership_pending"]
    return raw


def _partnership_pair_key(a: PartyId, b: PartyId) -> str:
    sa, sb = sorted((str(a), str(b)))
    return f"{sa}|{sb}"


def _already_partners(world: World, party_a: PartyId, party_b: PartyId) -> bool:
    if company_for_party(world, party_a) is not None and company_for_party(world, party_b) is not None:
        co_a = company_for_party(world, party_a)
        co_b = company_for_party(world, party_b)
        if co_a is not None and co_b is not None and co_a.company_id == co_b.company_id:
            return True
    pending = _partnership_store(world).get("partnership_pending", [])
    key = _partnership_pair_key(party_a, party_b)
    if isinstance(pending, list):
        for row in pending:
            if isinstance(row, dict) and row.get("pair_key") == key:
                return True
    return False


def _knows_with_reputation(
    world: World,
    observer: PartyId,
    other: PartyId,
) -> bool:
    model = get_settler_world_model(world, observer)
    entry = model.known_settlers.get(str(other))
    if entry is None:
        return False
    return _normalized_reputation(world, other) > REPUTATION_THRESHOLD


def _combined_cash_cents(world: World, party_a: PartyId, party_b: PartyId) -> int:
    return world.ledger.balance(party_cash_account(party_a)) + world.ledger.balance(
        party_cash_account(party_b)
    )


def _display_name(world: World, party: PartyId) -> str:
    return world.party_display_names.get(str(party), str(party))


def _company_name(world: World, party_a: PartyId, party_b: PartyId) -> str:
    return f"{_display_name(world, party_a)} & {_display_name(world, party_b)} Co."


def _production_line(world: World, party: PartyId) -> str:
    counts: dict[str, int] = {}
    ps = str(party)
    for b in world.plot_buildings:
        if str(b.get("party", "")) != ps:
            continue
        bid = str(b.get("building_id", ""))
        counts[bid] = counts.get(bid, 0) + 1
    if not counts:
        return ""
    return max(counts, key=lambda k: counts[k])


def _lines_complementary(line_a: str, line_b: str) -> bool:
    if not line_a or not line_b or line_a == line_b:
        return False
    comp_a = _MATERIAL_COMPLEMENTS.get(line_a, frozenset())
    comp_b = _MATERIAL_COMPLEMENTS.get(line_b, frozenset())
    return line_b in comp_a or line_a in comp_b or bool(comp_a & {line_b}) or bool(comp_b & {line_a})


def _acceptance_probability(personality: SettlerPersonality) -> float:
    # Higher risk tolerance → more willing to join a partnership.
    return min(0.95, max(0.05, 0.25 + personality.risk_tolerance * 0.65))


def _form_company(world: World, party_a: PartyId, party_b: PartyId) -> Company:
    company_id = next_company_id(world)
    acct = company_cash_account(company_id)
    world.ledger.ensure_account(acct)

    for party in (party_a, party_b):
        cash_acct = party_cash_account(party)
        bal = world.ledger.balance(cash_acct)
        contrib = bal // 2
        if contrib > 0:
            tr = world.ledger.transfer(debit=cash_acct, credit=acct, amount_cents=contrib)
            if isinstance(tr, MoneyErr):
                raise RuntimeError(f"partnership cash transfer failed: {tr.reason}")

    plots = sorted(set(party_plot_ids(world, party_a)) | set(party_plot_ids(world, party_b)))
    hq = plots[0] if plots else None
    founding = str(party_a)
    company = Company(
        company_id=company_id,
        name=_company_name(world, party_a, party_b),
        founded_tick=int(world.tick),
        founding_party=founding,
        share_registry={str(party_a): FOUNDER_SHARES_EACH, str(party_b): FOUNDER_SHARES_EACH},
        total_shares=FOUNDER_SHARES_EACH * 2,
        managed_plots=plots,
        cash_account=str(acct),
        hq_plot_id=hq,
        era_unlocked=merge_company_eras(world, party_a, party_b),
    )
    store_company(world, company)
    log_event(
        world,
        "company_formed",
        f"{company.name} formed ({party_a}, {party_b})",
        company_id=company_id,
        party_a=str(party_a),
        party_b=str(party_b),
    )
    from realm.agents.llm_voice import generate_settler_voice

    def _dn(p: PartyId) -> str:
        return world.party_display_names.get(str(p), str(p))

    generate_settler_voice(
        world,
        party_a,
        "company_formed",
        {
            "party_display_name": _dn(party_a),
            "partner_display_name": _dn(party_b),
        },
    )
    return company


def propose_partnership(world: World, party_a: PartyId, party_b: PartyId) -> ActionResult:
    if party_a == party_b:
        return {"ok": False, "reason": "cannot partner with self"}
    if party_a not in world.parties or party_b not in world.parties:
        return {"ok": False, "reason": "party missing"}
    if not str(party_a).startswith("settler_") or not str(party_b).startswith("settler_"):
        return {"ok": False, "reason": "partnerships are settler-only"}
    if company_for_party(world, party_a) is not None or company_for_party(world, party_b) is not None:
        return {"ok": False, "reason": "party already in a company"}
    if _already_partners(world, party_a, party_b):
        return {"ok": False, "reason": "partnership already exists or pending"}
    if not _knows_with_reputation(world, party_a, party_b):
        return {"ok": False, "reason": "insufficient mutual reputation intel"}
    if not _knows_with_reputation(world, party_b, party_a):
        return {"ok": False, "reason": "insufficient mutual reputation intel"}
    if _combined_cash_cents(world, party_a, party_b) < PARTNERSHIP_MIN_COMBINED_CASH_CENTS:
        return {"ok": False, "reason": "combined cash below threshold"}

    personality_b = get_settler_personality(world, party_b)
    if personality_b is None:
        return {"ok": False, "reason": "missing personality"}

    rng = world.rng(f"partnership:{party_a}:{party_b}:{world.tick}")
    if rng.random() >= _acceptance_probability(personality_b):
        _partnership_store(world).setdefault("partnership_pending", []).append(
            {"pair_key": _partnership_pair_key(party_a, party_b), "tick": int(world.tick), "status": "declined"}
        )
        return {"ok": False, "reason": "proposal declined"}

    company = _form_company(world, party_a, party_b)
    return {"ok": True, "company_id": company.company_id}


def tick_partnership_proposals(world: World) -> None:
    """Weekly per-settler scan for complementary partnership opportunities."""
    if world.scenario_id != "genesis":
        return
    slot = int(world.tick) % _TICKS_PER_GAME_WEEK
    for party in world.parties:
        ps = str(party)
        if not ps.startswith("settler_"):
            continue
        if _party_hash(party) % _TICKS_PER_GAME_WEEK != slot:
            continue
        if company_for_party(world, party) is not None:
            continue
        personality = get_settler_personality(world, party)
        if personality is None or personality.greed_index <= GREED_THRESHOLD:
            continue
        cash = world.ledger.balance(party_cash_account(party))
        if cash <= PROPOSER_MIN_CASH_CENTS:
            continue

        world_model = get_settler_world_model(world, party)
        my_line = _production_line(world, party)
        candidates: list[PartyId] = []
        for other_s, intel in world_model.known_settlers.items():
            if other_s == ps:
                continue
            if not other_s.startswith("settler_"):
                continue
            other = PartyId(other_s)
            if other not in world.parties:
                continue
            if company_for_party(world, other) is not None:
                continue
            if _already_partners(world, party, other):
                continue
            if not _knows_with_reputation(world, party, other):
                continue
            other_line = str(intel.get("primary_material", "")) or _production_line(world, other)
            if not _lines_complementary(my_line, other_line):
                continue
            candidates.append(other)

        if not candidates:
            continue
        rng = world.rng(f"partnership_scan:{party}:{world.tick}")
        target = candidates[int(rng.random() * len(candidates))]
        propose_partnership(world, party, target)
