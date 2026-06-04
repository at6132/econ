"""Persistent settler personality (immutable at spawn) and per-settler world models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from realm.core.ids import PartyId
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.world import World

CashTier = Literal["low", "medium", "high"]
Trend = Literal["+", "-", "flat"]

ParsedEvents = tuple[
    dict[str, int],
    dict[str, int],
    dict[str, dict[str, int]],
    dict[str, set[str]],
    dict[str, list[tuple[int, int]]],
    dict[str, list[tuple[int, int]]],
    dict[str, set[str]],
]

_TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY
_EVENT_KINDS = frozenset({"market_list", "market_buy", "claim", "blueprint_placed"})


@dataclass(frozen=True, slots=True)
class SettlerPersonality:
    risk_tolerance: float
    specialization_loyalty: float
    social_radius: int
    patience: float
    greed_index: float


@dataclass(slots=True)
class SettlerWorldModel:
    known_settlers: dict[str, dict[str, Any]] = field(default_factory=dict)
    material_intel: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_updated_tick: int = 0


def _identity_store(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault("settler_identities", {})
    if not isinstance(raw, dict):
        world.scenario_state["settler_identities"] = {}
        raw = world.scenario_state["settler_identities"]
    return raw


def _party_hash(party: PartyId) -> int:
    acc = 0
    for ch in str(party):
        acc = (acc * 131 + ord(ch)) & 0xFFFFFFFF
    return acc


def _weekly_update_slot(party: PartyId) -> int:
    return _party_hash(party) % _TICKS_PER_GAME_WEEK


def personality_to_dict(p: SettlerPersonality) -> dict[str, Any]:
    return {
        "risk_tolerance": p.risk_tolerance,
        "specialization_loyalty": p.specialization_loyalty,
        "social_radius": p.social_radius,
        "patience": p.patience,
        "greed_index": p.greed_index,
    }


def personality_from_dict(d: dict[str, Any]) -> SettlerPersonality:
    return SettlerPersonality(
        risk_tolerance=float(d["risk_tolerance"]),
        specialization_loyalty=float(d["specialization_loyalty"]),
        social_radius=int(d["social_radius"]),
        patience=float(d["patience"]),
        greed_index=float(d["greed_index"]),
    )


def world_model_to_dict(m: SettlerWorldModel) -> dict[str, Any]:
    return {
        "known_settlers": dict(m.known_settlers),
        "material_intel": dict(m.material_intel),
        "last_updated_tick": int(m.last_updated_tick),
    }


def world_model_from_dict(d: dict[str, Any]) -> SettlerWorldModel:
    return SettlerWorldModel(
        known_settlers=dict(d.get("known_settlers") or {}),
        material_intel=dict(d.get("material_intel") or {}),
        last_updated_tick=int(d.get("last_updated_tick", 0)),
    )


def _generate_personality(world: World, party: PartyId) -> SettlerPersonality:
    rng = world.rng(f"personality:{party}:{world.tick}")
    return SettlerPersonality(
        risk_tolerance=round(rng.random(), 4),
        specialization_loyalty=round(rng.random(), 4),
        social_radius=int(rng.randint(1, 5)),
        patience=round(rng.random(), 4),
        greed_index=round(rng.random(), 4),
    )


def assign_settler_personality(world: World, party: PartyId) -> SettlerPersonality:
    """Generate once at spawn; no-op if this party already has a personality."""
    store = _identity_store(world)
    key = str(party)
    row = store.get(key)
    if isinstance(row, dict) and "personality" in row:
        return personality_from_dict(row["personality"])
    personality = _generate_personality(world, party)
    store[key] = {
        "personality": personality_to_dict(personality),
        "world_model": world_model_to_dict(SettlerWorldModel()),
    }
    return personality


def get_settler_personality(world: World, party: PartyId) -> SettlerPersonality | None:
    row = _identity_store(world).get(str(party))
    if not isinstance(row, dict) or "personality" not in row:
        return None
    return personality_from_dict(row["personality"])


def get_settler_world_model(world: World, party: PartyId) -> SettlerWorldModel:
    row = _identity_store(world).get(str(party))
    if isinstance(row, dict) and "world_model" in row:
        return world_model_from_dict(row["world_model"])
    return SettlerWorldModel()


def _reputation_score(world: World, party: PartyId) -> int:
    rep = world.reputation.get(str(party), {})
    if not isinstance(rep, dict):
        return 0
    return int(rep.get("honored", 0)) - int(rep.get("breached", 0))


def _cash_tier(list_events: int, list_qty: int) -> CashTier:
    score = list_events + list_qty // 20
    if score >= 35:
        return "high"
    if score >= 10:
        return "medium"
    return "low"


def _price_trend(first_prices: list[int], second_prices: list[int]) -> Trend:
    if not first_prices or not second_prices:
        return "flat"
    first_avg = sum(first_prices) / len(first_prices)
    second_avg = sum(second_prices) / len(second_prices)
    if first_avg <= 0:
        return "flat"
    if second_avg >= first_avg * 1.05:
        return "+"
    if second_avg <= first_avg * 0.95:
        return "-"
    return "flat"


def _parse_recent_events(world: World) -> ParsedEvents:
    cutoff = int(world.tick) - _TICKS_PER_GAME_WEEK
    listing_events: dict[str, int] = {}
    listing_qty: dict[str, int] = {}
    primary_material_counts: dict[str, dict[str, int]] = {}
    claim_plots: dict[str, set[str]] = {}
    ask_prices: dict[str, list[tuple[int, int]]] = {}
    bid_prices: dict[str, list[tuple[int, int]]] = {}
    list_parties_by_material: dict[str, set[str]] = {}

    for ev in world.event_log:
        tick = int(ev.get("tick", 0))
        if tick < cutoff:
            continue
        kind = str(ev.get("kind", ""))
        if kind not in _EVENT_KINDS:
            continue

        if kind == "market_list":
            party_s = str(ev.get("party", ""))
            material = str(ev.get("material", ""))
            if not party_s or not material:
                continue
            qty = int(ev.get("qty", 0))
            price = int(ev.get("price_per_unit_cents", 0))
            listing_events[party_s] = listing_events.get(party_s, 0) + 1
            listing_qty[party_s] = listing_qty.get(party_s, 0) + max(qty, 0)
            bucket = primary_material_counts.setdefault(party_s, {})
            bucket[material] = bucket.get(material, 0) + max(qty, 1)
            list_parties_by_material.setdefault(material, set()).add(party_s)
            ask_prices.setdefault(material, []).append((tick, price))
            continue

        if kind == "market_buy":
            material = str(ev.get("material", ""))
            if not material:
                continue
            filled = int(ev.get("filled", 0))
            if filled <= 0:
                continue
            spent = int(ev.get("spent_cents", 0))
            unit = spent // filled if filled else 0
            bid_prices.setdefault(material, []).append((tick, unit))
            sellers = str(ev.get("sellers", "") or ev.get("seller", ""))
            if sellers:
                for seller in sellers.split(","):
                    seller = seller.strip()
                    if seller:
                        listing_events[seller] = listing_events.get(seller, 0)
            continue

        if kind == "claim":
            party_s = str(ev.get("party", ""))
            plot_id = str(ev.get("plot_id", ""))
            if party_s and plot_id:
                claim_plots.setdefault(party_s, set()).add(plot_id)
            continue

        if kind == "blueprint_placed":
            party_s = str(ev.get("party", ""))
            plot_id = str(ev.get("plot_id", ""))
            if party_s and plot_id:
                claim_plots.setdefault(party_s, set()).add(plot_id)

    return (
        listing_events,
        listing_qty,
        primary_material_counts,
        claim_plots,
        ask_prices,
        bid_prices,
        list_parties_by_material,
    )


def _build_world_model_from_parsed(
    world: World,
    observer: PartyId,
    parsed: ParsedEvents,
) -> SettlerWorldModel:
    observer_key = str(observer)
    (
        listing_events,
        listing_qty,
        primary_material_counts,
        claim_plots,
        ask_prices,
        bid_prices,
        list_parties_by_material,
    ) = parsed
    cutoff = int(world.tick) - _TICKS_PER_GAME_WEEK
    mid_tick = cutoff + _TICKS_PER_GAME_WEEK // 2

    known: dict[str, dict[str, Any]] = {}
    for party_s in set(listing_events) | set(primary_material_counts) | set(claim_plots):
        if party_s == observer_key or not party_s.startswith("settler_"):
            continue
        primary_material = ""
        counts = primary_material_counts.get(party_s, {})
        if counts:
            primary_material = max(counts, key=lambda m: counts[m])
        plots = sorted(claim_plots.get(party_s, set()))
        known[party_s] = {
            "estimated_cash_tier": _cash_tier(
                listing_events.get(party_s, 0),
                listing_qty.get(party_s, 0),
            ),
            "primary_material": primary_material,
            "plot_ids": plots,
            "reputation_score": _reputation_score(world, PartyId(party_s)),
        }

    material_intel: dict[str, dict[str, Any]] = {}
    materials = set(ask_prices) | set(bid_prices) | set(list_parties_by_material)
    for material in materials:
        asks = ask_prices.get(material, [])
        bids = bid_prices.get(material, [])
        last_seen_ask = asks[-1][1] if asks else 0
        last_seen_bid = bids[-1][1] if bids else 0
        first_ask = [p for t, p in asks if t < mid_tick]
        second_ask = [p for t, p in asks if t >= mid_tick]
        trend = _price_trend(first_ask, second_ask)
        producers = sorted(list_parties_by_material.get(material, set()))
        material_intel[material] = {
            "last_seen_ask": last_seen_ask,
            "last_seen_bid": last_seen_bid,
            "trend": trend,
            "known_producers": producers,
        }

    return SettlerWorldModel(
        known_settlers=known,
        material_intel=material_intel,
        last_updated_tick=int(world.tick),
    )


def _store_world_model(world: World, party: PartyId, model: SettlerWorldModel) -> None:
    store = _identity_store(world)
    key = str(party)
    row = store.setdefault(key, {})
    if not isinstance(row, dict):
        store[key] = {}
        row = store[key]
    row["world_model"] = world_model_to_dict(model)


def tick_settler_world_models(world: World) -> None:
    """Refresh each settler's world model once per game-week, staggered by party hash."""
    if world.scenario_id != "genesis":
        return
    slot = int(world.tick) % _TICKS_PER_GAME_WEEK
    due: list[PartyId] = []
    for party in world.parties:
        if not str(party).startswith("settler_"):
            continue
        if _weekly_update_slot(party) != slot:
            continue
        model = get_settler_world_model(world, party)
        if model.last_updated_tick > 0 and int(world.tick) - model.last_updated_tick < _TICKS_PER_GAME_WEEK:
            continue
        due.append(party)
    if not due:
        return
    parsed = _parse_recent_events(world)
    for party in due:
        model = _build_world_model_from_parsed(world, party, parsed)
        _store_world_model(world, party, model)
