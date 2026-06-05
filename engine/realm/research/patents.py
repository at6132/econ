"""Patents, global era advancement, licensing, and research competition."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Final

from realm.core.ids import PartyId
from realm.core.ledger import party_cash_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event
from realm.production.recipes import RECIPES
from realm.research.tech_tree import ERAS, TECH_NODES, era_node_ids, node_spec
from realm.world import World, ensure_party_recipe_book

PATENT_EXCLUSIVITY_DAYS: Final[int] = 30
PATENT_EXCLUSIVITY_TICKS: Final[int] = PATENT_EXCLUSIVITY_DAYS * TICKS_PER_GAME_DAY
LICENSE_FEE_CENTS_PER_DAY: Final[int] = 500

_ERA_ORDER: Final[tuple[str, ...]] = (
    "industrial",
    "electrical",
    "chemical",
    "digital",
    "advanced_mats",
    "post_scarcity",
)

_TICKS_PER_GAME_WEEK: Final[int] = 7 * TICKS_PER_GAME_DAY


@dataclass(frozen=True, slots=True)
class Patent:
    patent_id: str
    node_id: str
    holder_party: str
    granted_tick: int
    expires_tick: int
    licensed_to: list[str] = field(default_factory=list)


def _era_rank(era_id: str) -> int:
    try:
        return _ERA_ORDER.index(era_id)
    except ValueError:
        return -1


def _global_first(world: World) -> dict[str, str]:
    raw = world.scenario_state.setdefault("research_global_first", {})
    if not isinstance(raw, dict):
        world.scenario_state["research_global_first"] = {}
        raw = world.scenario_state["research_global_first"]
    return raw


def _patents_store(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault("patents", {})
    if not isinstance(raw, dict):
        world.scenario_state["patents"] = {}
        raw = world.scenario_state["patents"]
    return raw  # type: ignore[return-value]


def _patent_from_row(row: dict[str, Any]) -> Patent:
    licensed = row.get("licensed_to", [])
    if not isinstance(licensed, list):
        licensed = []
    return Patent(
        patent_id=str(row["patent_id"]),
        node_id=str(row["node_id"]),
        holder_party=str(row["holder_party"]),
        granted_tick=int(row["granted_tick"]),
        expires_tick=int(row["expires_tick"]),
        licensed_to=[str(x) for x in licensed],
    )


def _patent_to_row(patent: Patent) -> dict[str, Any]:
    return asdict(patent)


def _ensure_global_era_state(world: World) -> None:
    world.scenario_state.setdefault("current_global_era", "industrial")
    unlocked = world.scenario_state.setdefault("global_eras_unlocked", ["industrial"])
    if not isinstance(unlocked, list):
        world.scenario_state["global_eras_unlocked"] = ["industrial"]


def _global_eras_unlocked(world: World) -> set[str]:
    _ensure_global_era_state(world)
    raw = world.scenario_state.get("global_eras_unlocked", ["industrial"])
    if not isinstance(raw, list):
        return {"industrial"}
    out = {str(x) for x in raw}
    out.add("industrial")
    return out


def _set_global_eras_unlocked(world: World, eras: set[str]) -> None:
    eras.add("industrial")
    world.scenario_state["global_eras_unlocked"] = sorted(eras, key=_era_rank)


def era_globally_unlocked(world: World, era_id: str) -> bool:
    """True when the era is available for new research world-wide."""
    spec = ERAS.get(era_id)
    if spec is None:
        return False
    if spec.get("unlocked_at_boot"):
        return True
    return era_id in _global_eras_unlocked(world)


def _globally_completed_nodes(world: World) -> set[str]:
    root = world.scenario_state.get("research_completed")
    if not isinstance(root, dict):
        return set()
    done: set[str] = set()
    for raw in root.values():
        if isinstance(raw, list):
            done.update(str(x) for x in raw)
        elif isinstance(raw, set):
            done.update(str(x) for x in raw)
    return done


def _party_completed_nodes(world: World, party: PartyId) -> set[str]:
    root = world.scenario_state.get("research_completed")
    if not isinstance(root, dict):
        return set()
    raw = root.get(str(party), [])
    if isinstance(raw, list):
        return {str(x) for x in raw}
    if isinstance(raw, set):
        return {str(x) for x in raw}
    return set()


def _party_highest_era(world: World, party: PartyId) -> str:
    completed = _party_completed_nodes(world, party)
    best = "industrial"
    for nid in completed:
        node = node_spec(nid)
        if node is None:
            continue
        era = str(node["era"])
        if _era_rank(era) > _era_rank(best):
            best = era
    for era_id in _global_eras_unlocked(world):
        if _era_rank(era_id) > _era_rank(best):
            best = era_id
    return best


def patent_for_node(world: World, node_id: str) -> Patent | None:
    row = _patents_store(world).get(f"patent:{node_id}")
    if not isinstance(row, dict):
        return None
    return _patent_from_row(row)


def active_patent_for_node(world: World, node_id: str) -> Patent | None:
    patent = patent_for_node(world, node_id)
    if patent is None:
        return None
    if int(world.tick) >= patent.expires_tick:
        return None
    return patent


def grant_patent(world: World, party: PartyId, node_id: str) -> bool:
    """Record a global-first patent with 30-day exclusivity on unlocked recipes."""
    first = _global_first(world)
    if node_id in first:
        return False
    node = node_spec(node_id)
    if node is None:
        return False
    first[node_id] = str(party)
    granted_tick = int(world.tick)
    expires_tick = granted_tick + PATENT_EXCLUSIVITY_TICKS
    patent_id = f"patent:{node_id}"
    patent = Patent(
        patent_id=patent_id,
        node_id=node_id,
        holder_party=str(party),
        granted_tick=granted_tick,
        expires_tick=expires_tick,
        licensed_to=[],
    )
    _patents_store(world)[patent_id] = _patent_to_row(patent)
    log_event(
        world,
        "world_feed",
        f"{party} was granted the first patent on {node_id} — "
        f"{PATENT_EXCLUSIVITY_DAYS}-day exclusivity period begins",
        feed_source="research_patent",
        party=str(party),
        node_id=node_id,
        era=str(node.get("era", "")),
    )
    log_event(
        world,
        "research_patent",
        f"{party} awarded patent for {node_id}",
        party=str(party),
        node_id=node_id,
        expires_tick=expires_tick,
    )
    if str(party).startswith("settler_"):
        from realm.agents.llm_voice import generate_settler_voice

        label = world.party_display_names.get(str(party), str(party))
        generate_settler_voice(
            world,
            party,
            "patent_granted",
            {"party_display_name": label, "node_id": node_id},
        )
    return True


def try_award_patent(world: World, party: PartyId, node_id: str) -> bool:
    """Back-compat alias for :func:`grant_patent`."""
    return grant_patent(world, party, node_id)


def party_patent_ids(world: World, party: PartyId) -> list[str]:
    """Node ids for which ``party`` holds an active or expired global-first patent."""
    party_s = str(party)
    out: list[str] = []
    for row in _patents_store(world).values():
        if not isinstance(row, dict):
            continue
        if str(row.get("holder_party")) == party_s:
            out.append(str(row.get("node_id", "")))
    return sorted(nid for nid in out if nid)


def party_has_patent_license(world: World, party: PartyId, node_id: str) -> bool:
    patent = patent_for_node(world, node_id)
    if patent is None:
        return False
    return str(party) in patent.licensed_to


def _recipes_for_node(node_id: str) -> frozenset[str]:
    node = node_spec(node_id)
    if node is None:
        return frozenset()
    return frozenset(str(r) for r in node.get("unlocks_recipes", []) if str(r) in RECIPES)


def has_active_patent_exclusivity(world: World) -> bool:
    """Fast guard for hot paths (settler recipe pick) when no live patents exist."""
    store = world.scenario_state.get("patents")
    if not isinstance(store, dict) or not store:
        return False
    tick = int(world.tick)
    for row in store.values():
        if not isinstance(row, dict):
            continue
        if tick < int(row.get("expires_tick", 0)):
            return True
    return False


def recipe_blocked_by_patent(
    world: World,
    party: PartyId,
    recipe_id: str,
) -> tuple[bool, str | None]:
    """True when an unexpired patent blocks ``party`` from running ``recipe_id``."""
    if not has_active_patent_exclusivity(world):
        return False, None
    party_s = str(party)
    for row in _patents_store(world).values():
        if not isinstance(row, dict):
            continue
        patent = _patent_from_row(row)
        if int(world.tick) >= patent.expires_tick:
            continue
        if recipe_id not in _recipes_for_node(patent.node_id):
            continue
        if patent.holder_party == party_s:
            continue
        if party_s in patent.licensed_to:
            continue
        return (
            True,
            f"patent held by {patent.holder_party} on {patent.node_id} "
            f"(exclusive until tick {patent.expires_tick})",
        )
    return False, None


def _apply_cascade_bonuses(world: World) -> None:
    """Parties in later eras inherit efficiency bonuses from globally completed nodes."""
    global_done = _globally_completed_nodes(world)
    if not global_done:
        return
    root = world.scenario_state.setdefault("research_bonuses", {})
    if not isinstance(root, dict):
        world.scenario_state["research_bonuses"] = {}
        root = world.scenario_state["research_bonuses"]
    for party in world.parties:
        party_s = str(party)
        ceiling = _party_highest_era(world, party)
        ceiling_rank = _era_rank(ceiling)
        own_done = _party_completed_nodes(world, party)
        existing = root.get(party_s, {})
        if not isinstance(existing, dict):
            existing = {}
        merged = {str(k): float(v) for k, v in existing.items()}
        changed = False
        for nid in global_done:
            if nid in own_done:
                continue
            node = node_spec(nid)
            if node is None:
                continue
            if _era_rank(str(node["era"])) > ceiling_rank:
                continue
            for key, val in dict(node.get("efficiency_bonus", {})).items():
                merged[str(key)] = float(merged.get(str(key), 0.0)) + float(val)
                changed = True
        if changed:
            root[party_s] = merged


def tick_patents_and_eras(world: World) -> None:
    """Genesis hook — daily era/competition + weekly licensing (single modulo pass)."""
    tick = int(world.tick)
    if tick <= 0:
        return
    if tick % TICKS_PER_GAME_DAY == 0:
        _tick_era_advancement_body(world)
        _tick_research_competition_body(world)
    if tick % _TICKS_PER_GAME_WEEK == 0:
        _tick_patent_licensing_body(world)


def tick_era_advancement(world: World) -> None:
    """Daily: unlock eras globally when prerequisite nodes are each completed somewhere."""
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return
    _tick_era_advancement_body(world)


def _tick_era_advancement_body(world: World) -> None:
    _ensure_global_era_state(world)
    global_done = _globally_completed_nodes(world)
    unlocked = _global_eras_unlocked(world)
    for era_id, spec in ERAS.items():
        if spec.get("unlocked_at_boot"):
            continue
        if era_id in unlocked:
            continue
        prereq = spec.get("prereq")
        if prereq is None:
            continue
        prereq_nodes = era_node_ids(str(prereq))
        if not prereq_nodes or not all(nid in global_done for nid in prereq_nodes):
            continue
        unlocked.add(era_id)
        _set_global_eras_unlocked(world, unlocked)
        world.scenario_state["current_global_era"] = era_id
        label = era_id.replace("_", " ").title()
        log_event(
            world,
            "world_feed",
            f"BREAKTHROUGH: The {label} era has dawned. New technologies are now researchable.",
            feed_source="era_unlock",
            era_id=era_id,
        )
        log_event(
            world,
            "era_unlock",
            f"Global era unlocked: {era_id}",
            era_id=era_id,
        )
    _apply_cascade_bonuses(world)


def tick_patent_licensing(world: World) -> None:
    """Weekly: generous patent holders license blocked recipes to settlers who can pay."""
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_WEEK != 0:
        return
    _tick_patent_licensing_body(world)


def _tick_patent_licensing_body(world: World) -> None:
    from realm.agents.settler_identity import get_settler_personality

    for row in list(_patents_store(world).values()):
        if not isinstance(row, dict):
            continue
        patent = _patent_from_row(row)
        if int(world.tick) >= patent.expires_tick:
            continue
        holder = PartyId(patent.holder_party)
        personality = get_settler_personality(world, holder)
        if personality is None or personality.greed_index >= 0.5:
            continue
        node = node_spec(patent.node_id)
        if node is None:
            continue
        fee = int(node["research_cost_days"]) * LICENSE_FEE_CENTS_PER_DAY
        if fee <= 0:
            continue
        recipes = _recipes_for_node(patent.node_id)
        if not recipes:
            continue
        for party in world.parties:
            party_s = str(party)
            if not party_s.startswith("settler_"):
                continue
            if party_s == patent.holder_party:
                continue
            if party_s in patent.licensed_to:
                continue
            book = ensure_party_recipe_book(world, party)
            needs = any(rid not in book for rid in recipes)
            if not needs:
                continue
            cash_acct = party_cash_account(party)
            if world.ledger.balance(cash_acct) < fee:
                continue
            holder_acct = party_cash_account(holder)
            from realm.core.ledger import MoneyErr

            xfer = world.ledger.transfer(
                debit=cash_acct,
                credit=holder_acct,
                amount_cents=fee,
            )
            if isinstance(xfer, MoneyErr):
                continue
            licensed = list(patent.licensed_to)
            licensed.append(party_s)
            updated = Patent(
                patent_id=patent.patent_id,
                node_id=patent.node_id,
                holder_party=patent.holder_party,
                granted_tick=patent.granted_tick,
                expires_tick=patent.expires_tick,
                licensed_to=licensed,
            )
            _patents_store(world)[patent.patent_id] = _patent_to_row(updated)
            for rid in recipes:
                if rid in RECIPES and rid not in book:
                    book.add(rid)
            log_event(
                world,
                "license_granted",
                f"{party} licensed {patent.node_id} recipes from {holder} for {fee}c",
                party=party_s,
                holder=patent.holder_party,
                node_id=patent.node_id,
                fee_cents=fee,
            )


def tick_research_competition(world: World) -> None:
    """Daily: hint when multiple labs race the same tech node."""
    if int(world.tick) <= 0 or int(world.tick) % TICKS_PER_GAME_DAY != 0:
        return
    _tick_research_competition_body(world)


def _tick_research_competition_body(world: World) -> None:
    active = world.scenario_state.get("active_research")
    if not isinstance(active, dict) or not active:
        return
    by_node: dict[str, list[str]] = {}
    for party_s, job in active.items():
        if not isinstance(job, dict):
            continue
        node_id = str(job.get("node_id", ""))
        if not node_id:
            continue
        by_node.setdefault(node_id, []).append(str(party_s))
    for node_id, racers in by_node.items():
        if len(racers) < 2:
            continue
        log_event(
            world,
            "world_feed",
            f"Multiple labs racing toward {node_id}...",
            feed_source="research_competition",
            node_id=node_id,
            racers=",".join(sorted(racers)),
        )


def era_efficiency_score(
    world: World,
    party: PartyId,
    recipe_id: str,
    *,
    plot_id: object = None,
) -> float:
    """Multiplier from research bonuses (for settler recipe ranking)."""
    from realm.research.bonuses import research_output_multiplier

    return research_output_multiplier(
        world,
        party,
        recipe_id,
        plot_id=plot_id,  # type: ignore[arg-type]
    )
