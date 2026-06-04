"""Market fog — decaying settler knowledge, paid scouting, and occasional false rumors."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from realm.agents.settler_identity import (
    get_settler_personality,
    get_settler_world_model,
    world_model_to_dict,
)
from realm.core.ids import PartyId, PlotId
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event
from realm.world import World
_TICKS_PER_GAME_WEEK = 7 * TICKS_PER_GAME_DAY
_TICKS_PER_SCOUT_CYCLE = 5 * TICKS_PER_GAME_DAY
_TICKS_PER_RUMOR_CYCLE = 14 * TICKS_PER_GAME_DAY

SCOUT_COST_CENTS = 200
RUMOR_TRIGGER_PROB = 0.15
RUMOR_RECIPIENT_FRACTION = 0.30
RUMOR_FALSE_GRADE = 0.82

_GRADE_FIELD_TO_MATERIAL: dict[str, str] = {
    "iron_ore_grade": "iron_ore",
    "copper_ore_grade": "copper_ore",
    "clay_grade": "clay",
    "coal_grade": "coal",
    "sulfur_grade": "sulfur_ore",
    "saltpeter_grade": "saltpeter_ore",
    "tin_grade": "tin_ore",
    "lead_grade": "lead_ore",
    "phosphate_grade": "phosphate_ore",
    "silica_grade": "raw_silica",
}

_RUMOR_MATERIALS: tuple[str, ...] = tuple(_GRADE_FIELD_TO_MATERIAL.values())


def _party_hash(party: PartyId) -> int:
    acc = 0
    for ch in str(party):
        acc = (acc * 131 + ord(ch)) & 0xFFFFFFFF
    return acc


def _scout_cycle_slot(party: PartyId) -> int:
    return _party_hash(party) % _TICKS_PER_SCOUT_CYCLE


def _identity_store(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault("settler_identities", {})
    if not isinstance(raw, dict):
        world.scenario_state["settler_identities"] = {}
        raw = world.scenario_state["settler_identities"]
    return raw


def _store_world_model(world: World, party: PartyId, model) -> None:
    store = _identity_store(world)
    key = str(party)
    row = store.setdefault(key, {})
    if not isinstance(row, dict):
        store[key] = {}
        row = store[key]
    row["world_model"] = world_model_to_dict(model)


def _settler_parties(world: World) -> list[PartyId]:
    return [p for p in world.parties if str(p).startswith("settler_")]


def _subsurface_grades_dict(plot) -> dict[str, float]:
    grades: dict[str, float] = {}
    for fld in fields(plot.subsurface):
        if not fld.name.endswith("_grade"):
            continue
        grades[fld.name] = float(getattr(plot.subsurface, fld.name, 0.0))
    return grades


def _settler_intel_store(world: World) -> dict[str, dict[str, Any]]:
    raw = world.scenario_state.setdefault("settler_intel", {})
    if not isinstance(raw, dict):
        world.scenario_state["settler_intel"] = {}
        raw = world.scenario_state["settler_intel"]
    return raw


def listing_uncertainty_for_material(
    world: World, party: PartyId, material: str
) -> float:
    """Uncertainty in ``[0, 1]`` for how well a settler knows their listing competitiveness."""
    intel = get_settler_world_model(world, party).material_intel.get(str(material), {})
    try:
        return float(intel.get("uncertainty", 0.0))
    except (TypeError, ValueError):
        return 0.0


def tick_knowledge_decay(world: World) -> None:
    """Weekly: stale market observations grow uncertain; pricing gets noisier."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_GAME_WEEK != 0:
        return
    now = int(world.tick)
    for party in _settler_parties(world):
        model = get_settler_world_model(world, party)
        if not model.material_intel:
            continue
        updated = False
        new_intel: dict[str, dict[str, Any]] = {}
        for material, entry in model.material_intel.items():
            row = dict(entry)
            last_obs = int(row.get("last_observed_tick", model.last_updated_tick or 0))
            if now - last_obs >= _TICKS_PER_GAME_WEEK:
                unc = float(row.get("uncertainty", 0.0))
                row["uncertainty"] = min(1.0, unc + 0.1)
                updated = True
            if "uncertainty" not in row:
                row["uncertainty"] = 0.0
            new_intel[str(material)] = row
        if updated:
            model.material_intel = new_intel
            _store_world_model(world, party, model)


def _competitor_plots(world: World, scout: PartyId) -> list[PlotId]:
    out: list[PlotId] = []
    scout_s = str(scout)
    for plot in world.plots.values():
        owner = plot.owner
        if owner is None:
            continue
        owner_s = str(owner)
        if owner_s == scout_s:
            continue
        if not owner_s.startswith("settler_"):
            continue
        out.append(plot.plot_id)
    return out


def tick_scout_actions(world: World) -> None:
    """Every five game-days per settler: risk-tolerant scouts may buy competitor subsurface intel."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0:
        return
    slot = int(world.tick) % _TICKS_PER_SCOUT_CYCLE
    intel_root = _settler_intel_store(world)
    for party in _settler_parties(world):
        if _scout_cycle_slot(party) != slot:
            continue
        personality = get_settler_personality(world, party)
        if personality is None or personality.risk_tolerance <= 0.5:
            continue
        targets = _competitor_plots(world, party)
        if not targets:
            continue
        cash_acct = party_cash_account(party)
        if world.ledger.balance(cash_acct) < SCOUT_COST_CENTS:
            continue
        rng = world.rng(f"scout:{party}:{world.tick}")
        target_plot = targets[rng.randrange(len(targets))]
        plot = world.plots.get(target_plot)
        if plot is None:
            continue
        tr = world.ledger.transfer(
            debit=cash_acct,
            credit=system_reserve_account(),
            amount_cents=SCOUT_COST_CENTS,
        )
        if isinstance(tr, MoneyErr):
            continue
        grades = _subsurface_grades_dict(plot)
        intel_root.setdefault(str(party), {})[str(target_plot)] = {
            "grades": grades,
            "uncertainty": 0.0,
            "tick": int(world.tick),
        }
        model = get_settler_world_model(world, party)
        for field_name, grade in grades.items():
            if grade < 0.15:
                continue
            material = _GRADE_FIELD_TO_MATERIAL.get(field_name)
            if material is None:
                continue
            row = dict(model.material_intel.get(material, {}))
            row["grade"] = float(grade)
            row["uncertainty"] = 0.0
            row["plot_id"] = str(target_plot)
            row["last_observed_tick"] = int(world.tick)
            model.material_intel[material] = row
        _store_world_model(world, party, model)
        log_event(
            world,
            "intel_purchased",
            f"{party} scouted plot {target_plot} for {SCOUT_COST_CENTS}¢",
            party=str(party),
            plot_id=str(target_plot),
            cost_cents=SCOUT_COST_CENTS,
        )


def _island_ids(world: World) -> list[int]:
    islands_map = world.scenario_state.get("plot_islands")
    if not isinstance(islands_map, dict):
        return [0]
    ids: set[int] = set()
    for val in islands_map.values():
        try:
            ids.add(int(val))
        except (TypeError, ValueError):
            continue
    return sorted(ids) if ids else [0]


def tick_market_rumors(world: World) -> None:
    """Every fourteen game-days: occasional unconfirmed deposit rumors fog the market."""
    if world.scenario_id != "genesis":
        return
    if int(world.tick) <= 0 or int(world.tick) % _TICKS_PER_RUMOR_CYCLE != 0:
        return
    rng = world.rng(f"rumor:{world.tick}")
    if rng.random() >= RUMOR_TRIGGER_PROB:
        return
    material = _RUMOR_MATERIALS[rng.randrange(len(_RUMOR_MATERIALS))]
    islands = _island_ids(world)
    island_id = islands[rng.randrange(len(islands))]
    settlers = _settler_parties(world)
    if not settlers:
        return
    recipient_count = max(1, int(len(settlers) * RUMOR_RECIPIENT_FRACTION + 0.999))
    recipients = rng.sample(settlers, min(recipient_count, len(settlers)))
    for party in recipients:
        model = get_settler_world_model(world, party)
        row = dict(model.material_intel.get(material, {}))
        row["grade"] = RUMOR_FALSE_GRADE
        row["uncertainty"] = 0.0
        row["island_id"] = int(island_id)
        row["last_observed_tick"] = int(world.tick)
        model.material_intel[material] = row
        _store_world_model(world, party, model)
    log_event(
        world,
        "world_feed",
        f"Prospectors report unusually rich {material} deposits on island {island_id} — unconfirmed.",
        feed_source="market_rumor",
        material=material,
        island_id=int(island_id),
    )


def merge_material_intel_entry(
    *,
    observed: bool,
    tick: int,
    previous: dict[str, Any] | None,
    market_fields: dict[str, Any],
) -> dict[str, Any]:
    """Build one ``material_intel`` row, preserving rumor/scout fields when appropriate."""
    row: dict[str, Any] = dict(previous or {})
    row.update(market_fields)
    if observed:
        row["uncertainty"] = 0.0
        row["last_observed_tick"] = int(tick)
    else:
        row.setdefault("uncertainty", 0.0)
        row.setdefault("last_observed_tick", int(previous.get("last_observed_tick", 0)) if previous else 0)
    return row
