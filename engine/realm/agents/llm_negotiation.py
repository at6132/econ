"""LLM-mediated bilateral supply contract negotiation (Haiku, non-blocking)."""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, TypedDict

from realm.actions._shared import ActionResult
from realm.agents.llm_haiku import estimate_cost_micro_usd, make_client
from realm.agents.llm_voice import settler_voice_model
from realm.agents.settler_identity import get_settler_personality
from realm.core.ids import MaterialId, PartyId
from realm.core.ledger import party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.deals.bilateral_contracts import propose_bilateral_contract
from realm.economy.markets import best_resting_ask_cents
from realm.economy.pricing import exchange_ask_cents
from realm.events.event_log import log_event
from realm.genesis.settler_cost_basis import settler_output_basis_cents
from realm.world import World

_NEGOTIATION_MODEL_DEFAULT = "claude-haiku-4-5"
_NEGOTIATION_MAX_TOKENS = 150
_MIN_COMBINED_STAKE_CENTS = 10_000
_COOLDOWN_TICKS = 7 * TICKS_PER_GAME_DAY

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="realm_negotiation_llm")


class ProposedTerms(TypedDict):
    material_id: str
    qty_per_week: int
    price_cents_per_unit: int
    duration_weeks: int
    exclusive: bool


def negotiation_model() -> str:
    return (
        os.environ.get("REALM_NEGOTIATION_MODEL", "").strip()
        or os.environ.get("REALM_LLM_MODEL", "").strip()
        or _NEGOTIATION_MODEL_DEFAULT
    )


def _nego_state(world: World) -> dict[str, Any]:
    raw = world.scenario_state.setdefault("llm_negotiation", {})
    if not isinstance(raw, dict):
        world.scenario_state["llm_negotiation"] = {}
        raw = world.scenario_state["llm_negotiation"]
    return raw


def _display_name(world: World, party: PartyId) -> str:
    return world.party_display_names.get(str(party), str(party))


def _pair_cooldown_key(seller: PartyId, buyer: PartyId, material: MaterialId) -> str:
    return f"{seller}|{buyer}|{material}"


def _on_negotiation_cooldown(world: World, seller: PartyId, buyer: PartyId, material: MaterialId) -> bool:
    st = _nego_state(world)
    cd = st.get("cooldowns")
    if not isinstance(cd, dict):
        return False
    until = int(cd.get(_pair_cooldown_key(seller, buyer, material), 0))
    return int(world.tick) < until


def _set_negotiation_cooldown(world: World, seller: PartyId, buyer: PartyId, material: MaterialId) -> None:
    st = _nego_state(world)
    cd = st.setdefault("cooldowns", {})
    if not isinstance(cd, dict):
        st["cooldowns"] = {}
        cd = st["cooldowns"]
    cd[_pair_cooldown_key(seller, buyer, material)] = int(world.tick) + _COOLDOWN_TICKS


def _combined_stake_cents(world: World, seller: PartyId, buyer: PartyId) -> int:
    return world.ledger.balance(party_cash_account(seller)) + world.ledger.balance(
        party_cash_account(buyer)
    )


def _append_seller_note(world: World, seller: PartyId, note: str) -> None:
    display = _display_name(world, seller)
    text = note.strip()
    if not text:
        return
    world.npc_messages_to_player.append(
        {
            "tick": world.tick,
            "from_party": str(seller),
            "display_name": display,
            "text": text,
        }
    )
    if len(world.npc_messages_to_player) > 96:
        world.npc_messages_to_player = world.npc_messages_to_player[-96:]
    log_event(
        world,
        "npc_message",
        f"{display}: {text}",
        from_party=str(seller),
        party=str(seller),
        source="negotiation_note",
    )


def _build_system_prompt(
    world: World,
    seller: PartyId,
    buyer: PartyId,
    material: MaterialId,
    terms: ProposedTerms,
) -> str:
    seller_p = get_settler_personality(world, seller)
    buyer_p = get_settler_personality(world, buyer)
    if seller_p is None or buyer_p is None:
        raise ValueError("missing personality")

    exchange_price = best_resting_ask_cents(world, material)
    if exchange_price is None or exchange_price <= 0:
        exchange_price = exchange_ask_cents(material, world=world)
    seller_basis = settler_output_basis_cents(world, seller, material)
    if seller_basis is None or seller_basis <= 0:
        seller_basis = exchange_price

    return (
        "You are simulating a negotiation between two frontier economy settlers.\n"
        f"Seller: {_display_name(world, seller)} — personality: "
        f"risk_tolerance={seller_p.risk_tolerance:.1f}, greed_index={seller_p.greed_index:.1f}\n"
        f"Buyer: {_display_name(world, buyer)} — personality: "
        f"risk_tolerance={buyer_p.risk_tolerance:.1f}, patience={buyer_p.patience:.1f}\n"
        f"Material: {material}, proposed qty/week: {terms['qty_per_week']}, "
        f"proposed price: {terms['price_cents_per_unit']}¢/unit, "
        f"proposed duration: {terms['duration_weeks']} weeks\n"
        f"Current exchange price: {exchange_price}¢\n"
        f"Seller cost basis: {seller_basis}¢\n"
        f"Buyer's alternative: buy from exchange at {exchange_price}¢\n\n"
        "Return ONLY a JSON object:\n"
        '{"agreed": true/false, "final_price_cents": int, "final_duration_weeks": int, '
        '"exclusivity": bool, "note": "one sentence on why"}'
    )


def _parse_negotiation_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if m is None:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return data


def _haiku_negotiate(system: str) -> tuple[dict[str, Any] | None, dict[str, int]]:
    empty = {"input_tokens": 0, "output_tokens": 0, "cost_micro_usd": 0}
    client = make_client()
    if client is None:
        return None, empty
    try:
        resp = client.messages.create(
            model=negotiation_model(),
            max_tokens=_NEGOTIATION_MAX_TOKENS,
            temperature=0.4,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": "Simulate the negotiation and return the JSON object only.",
                }
            ],
        )
    except Exception:
        return None, empty
    parts: list[str] = []
    total_in = 0
    total_out = 0
    use = getattr(resp, "usage", None)
    if use is not None:
        total_in = int(getattr(use, "input_tokens", 0) or 0)
        total_out = int(getattr(use, "output_tokens", 0) or 0)
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    parsed = _parse_negotiation_json("\n".join(parts))
    usage = {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cost_micro_usd": estimate_cost_micro_usd(input_tokens=total_in, output_tokens=total_out),
    }
    return parsed, usage


def _apply_negotiation_result(
    world: World,
    seller: PartyId,
    buyer: PartyId,
    material: MaterialId,
    terms: ProposedTerms,
    data: dict[str, Any],
) -> ActionResult:
    agreed = bool(data.get("agreed"))
    note = str(data.get("note", "")).strip()
    if note:
        _append_seller_note(world, seller, note)

    if not agreed:
        _set_negotiation_cooldown(world, seller, buyer, material)
        return {"ok": False, "reason": "negotiation declined"}

    try:
        final_price = max(1, int(data.get("final_price_cents", terms["price_cents_per_unit"])))
        final_weeks = max(1, int(data.get("final_duration_weeks", terms["duration_weeks"])))
        exclusivity = bool(data.get("exclusivity", terms["exclusive"]))
    except (TypeError, ValueError):
        _set_negotiation_cooldown(world, seller, buyer, material)
        return {"ok": False, "reason": "invalid negotiation json"}

    return propose_bilateral_contract(
        world,
        seller,
        buyer,
        material,
        terms["qty_per_week"],
        final_price,
        final_weeks,
        exclusivity,
        force_accept=True,
    )


def negotiate_bilateral_contract(
    world: World,
    seller: PartyId,
    buyer: PartyId,
    proposed_terms: ProposedTerms,
) -> ActionResult:
    """Queue Haiku negotiation; result applied on ``tick_llm_negotiation``."""
    material = MaterialId(proposed_terms["material_id"])
    if _on_negotiation_cooldown(world, seller, buyer, material):
        return {"ok": False, "reason": "negotiation cooldown"}
    if _combined_stake_cents(world, seller, buyer) <= _MIN_COMBINED_STAKE_CENTS:
        return {"ok": False, "reason": "stake too small for llm negotiation"}
    if make_client() is None:
        return {"ok": False, "reason": "no_anthropic_client"}

    st = _nego_state(world)
    inflight = st.setdefault("inflight", {})
    if not isinstance(inflight, dict):
        st["inflight"] = {}
        inflight = st["inflight"]
    key = _pair_cooldown_key(seller, buyer, material)
    if key in inflight:
        return {"ok": True, "queued": True}

    try:
        system = _build_system_prompt(world, seller, buyer, material, proposed_terms)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc)}

    def _run() -> tuple[dict[str, Any] | None, dict[str, int]]:
        return _haiku_negotiate(system)

    fut: Future[tuple[dict[str, Any] | None, dict[str, int]]] = _executor.submit(_run)
    inflight[key] = {
        "seller": str(seller),
        "buyer": str(buyer),
        "material": str(material),
        "terms": dict(proposed_terms),
        "queued_tick": int(world.tick),
        "_future": fut,
    }
    return {"ok": True, "queued": True}


def tick_llm_negotiation(world: World) -> None:
    """Apply completed negotiation futures without blocking."""
    if world.scenario_id != "genesis":
        return
    st = _nego_state(world)
    inflight = st.get("inflight")
    if not inflight:
        return
    if not isinstance(inflight, dict):
        return

    cutoff = int(world.tick) - TICKS_PER_GAME_DAY
    done: list[str] = []
    for key, row in list(inflight.items()):
        if not isinstance(row, dict):
            done.append(key)
            continue
        fut = row.get("_future")
        if not isinstance(fut, Future):
            done.append(key)
            continue
        queued = int(row.get("queued_tick", 0))
        if queued < cutoff and not fut.done():
            fut.cancel()
            done.append(key)
            continue
        if not fut.done():
            continue
        seller = PartyId(str(row.get("seller", "")))
        buyer = PartyId(str(row.get("buyer", "")))
        material = MaterialId(str(row.get("material", "")))
        terms_raw = row.get("terms")
        try:
            parsed, usage = fut.result(timeout=0)
        except Exception:
            _set_negotiation_cooldown(world, seller, buyer, material)
            done.append(key)
            continue
        st["session_cost_micro_usd"] = int(st.get("session_cost_micro_usd", 0)) + int(
            usage.get("cost_micro_usd", 0)
        )
        if (
            seller in world.parties
            and buyer in world.parties
            and isinstance(terms_raw, dict)
        ):
            if parsed is None:
                _set_negotiation_cooldown(world, seller, buyer, material)
            else:
                _apply_negotiation_result(
                    world,
                    seller,
                    buyer,
                    material,
                    terms_raw,  # type: ignore[arg-type]
                    parsed,
                )
        done.append(key)

    for key in done:
        inflight.pop(key, None)
