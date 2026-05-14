"""Assay system — paid mineral analysis that unlocks Tier-2 recipes (discovery, not luck).

Each ``assay_mineral`` attempt costs ``ASSAY_COST_CENTS`` (paid to the system reserve) and
schedules a job in ``world.scenario_state["assay_jobs"]`` that completes after
``ASSAY_DURATION_TICKS`` (one game-day). On completion, ``tick_assay_jobs`` advances the
party's stage by 1 for that mineral; stage 3 unlocks the associated recipes into the
party's ``party_recipe_books`` and emits a ``world_feed`` headline.

Hints are deterministic per stage (no luck), so the dance feels like *intelligence*, not
gambling. The assay job's completion tick is computed from ``world.tick`` at submit time.
"""

from __future__ import annotations

from typing import Any, Final, Iterable

from realm.events.event_log import log_event
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.core.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.world import World, ensure_party_recipe_book

ASSAY_COST_CENTS: Final[int] = 500
ASSAY_DURATION_TICKS: Final[int] = TICKS_PER_GAME_DAY
ASSAY_MIN_SUBSURFACE_GRADE: Final[float] = 0.1
ASSAY_MAX_STAGE: Final[int] = 3

# Mineral id → subsurface grade field name. Only minerals defined here are assayable.
ASSAY_MINERAL_GRADE_FIELDS: Final[dict[str, str]] = {
    "sulfur_ore": "sulfur_grade",
    "saltpeter_ore": "saltpeter_grade",
    "tin_ore": "tin_grade",
    "lead_ore": "lead_grade",
    "phosphate_ore": "phosphate_grade",
    "raw_silica": "silica_grade",
    "platinum_ore": "platinum_grade",
    "oil_shale": "oil_shale_grade",
    "rare_earth_ore": "rare_earth_grade",
}

# What gets unlocked when an assay reaches stage 3 for a given mineral.
ASSAY_MINERAL_RECIPE_UNLOCKS: Final[dict[str, tuple[str, ...]]] = {
    "sulfur_ore": (
        "mine_sulfur_ore",
        "hand_mine_sulfur",
        "refine_sulfur",
        "make_sulfuric_acid",
    ),
    "saltpeter_ore": (
        "mine_saltpeter",
        "refine_saltpeter",
        "make_gunpowder",
    ),
    "tin_ore": (
        "mine_tin_ore",
        "hand_mine_tin",
        "smelt_tin",
        "make_bronze",
    ),
    "lead_ore": (
        "mine_lead_ore",
        "smelt_lead",
    ),
    "phosphate_ore": (
        "mine_phosphate",
        "process_phosphate",
    ),
    "raw_silica": (
        "mine_raw_silica",
        "fuse_silica",
    ),
    # Tier-3 (revealed only via deep_survey); recipes added in Phase 4.
    "platinum_ore": ("mine_platinum", "refine_platinum"),
    "oil_shale": ("mine_oil_shale", "process_shale"),
    "rare_earth_ore": ("mine_rare_earth",),
}

# Deterministic, mineral-specific hints (3 stages each).
ASSAY_STAGE_HINTS: Final[dict[str, tuple[str, str, str]]] = {
    "sulfur_ore": (
        "Sulfur ore melts at low temperature and has a sharp odour — associated with heat and carbon "
        "in old refining processes.",
        "Roasting sulfur ore with charcoal under high heat yields a reactive gas. Industrial uses involve "
        "acid production.",
        "Recipe discovered: refine_sulfur + sulfuric_acid chain — assay lab notes confirmed. "
        "Your recipe book has been updated.",
    ),
    "saltpeter_ore": (
        "Saltpeter ore crystallises after dry seasons; it deflagrates when struck with a flame.",
        "Mixed with sulfur and carbon under fast heat it releases gas in a controlled burst.",
        "Recipe discovered: saltpeter refining + gunpowder chain — your recipe book has been updated.",
    ),
    "tin_ore": (
        "Tin ore is heavy, dull, and surrenders metal at modest furnace temperatures.",
        "Tin alloys readily with copper to form a harder, more castable bronze.",
        "Recipe discovered: tin smelting + bronze alloy — your recipe book has been updated.",
    ),
    "lead_ore": (
        "Lead ore is unusually dense and fuses at low heat — a smelter quirk worth noting.",
        "Drosses cleanly when heated with coal; the metal pours into ingots without violent slag.",
        "Recipe discovered: lead smelting — your recipe book has been updated.",
    ),
    "phosphate_ore": (
        "Phosphate ore reacts vigorously with strong acid, suggesting an agricultural workup.",
        "When digested in sulfuric acid the result is a slow-release plant-grade meal.",
        "Recipe discovered: phosphate processing — your recipe book has been updated.",
    ),
    "raw_silica": (
        "Raw silica is glassy and refractory — it survives temperatures other stones cannot.",
        "Under prolonged heat with coal flux it fuses into a clear, hard form useful in optics and lining.",
        "Recipe discovered: silica fusion — your recipe book has been updated.",
    ),
    "platinum_ore": (
        "Heavy, unreactive nodules in the deep drill core — they resist ordinary acid baths.",
        "High-temperature work in a foundry leaves a bright, dense bead that takes no oxidation.",
        "Recipe discovered: platinum mining + refining — your recipe book has been updated.",
    ),
    "oil_shale": (
        "Deep drill core contains layered shale that burns slowly with a heavy, smoky flame.",
        "Slow heat in a chemical retort drives a viscous oil out of the rock matrix.",
        "Recipe discovered: oil shale extraction + processing — your recipe book has been updated.",
    ),
    "rare_earth_ore": (
        "Trace rare-earth concentrations in the deep core — a distinctive spectral signature.",
        "Separation chemistry will take real industrial work; the deposit itself is enough to value.",
        "Recipe discovered: rare earth mining — your recipe book has been updated.",
    ),
}


def _scen_assay(world: World) -> dict[str, Any]:
    """Top-level assay scratchpad: ``{"progress": {party: {mineral: stage}}, "jobs": [...]}``."""
    st = world.scenario_state.setdefault("assay", {})
    if not isinstance(st, dict):
        world.scenario_state["assay"] = {}
        st = world.scenario_state["assay"]
    st.setdefault("progress", {})
    st.setdefault("jobs", [])
    return st


def _assay_progress(world: World) -> dict[str, dict[str, int]]:
    st = _scen_assay(world)
    prog = st["progress"]
    if not isinstance(prog, dict):
        st["progress"] = {}
        prog = st["progress"]
    return prog


def get_assay_stage(world: World, party: PartyId, mineral: MaterialId) -> int:
    """Stage 0..3 for ``party`` on ``mineral``. 3 means recipes were unlocked."""
    pp = _assay_progress(world).get(str(party), {})
    if not isinstance(pp, dict):
        return 0
    return int(pp.get(str(mineral), 0))


def _set_assay_stage(world: World, party: PartyId, mineral: MaterialId, stage: int) -> None:
    prog = _assay_progress(world)
    pp = prog.setdefault(str(party), {})
    if not isinstance(pp, dict):
        prog[str(party)] = {}
        pp = prog[str(party)]
    pp[str(mineral)] = int(stage)


def _party_has_operational_lab(world: World, party: PartyId, plot_id: PlotId | None = None) -> bool:
    """True if the party has an ``assay_lab`` building on ``plot_id`` (or anywhere if ``plot_id`` is None)."""
    from realm.decay import building_effective_for_bonuses
    from realm.core.time_scale import building_operational

    for b in world.plot_buildings:
        if b.get("party") != str(party):
            continue
        if b.get("building_id") != "assay_lab":
            continue
        if plot_id is not None and b.get("plot_id") != str(plot_id):
            continue
        if not building_operational(b, at_tick=world.tick):
            continue
        if not building_effective_for_bonuses(b):
            continue
        return True
    return False


def _plot_grade_for_mineral(world: World, plot_id: PlotId, mineral: MaterialId) -> float:
    plot = world.plots.get(plot_id)
    if plot is None:
        return 0.0
    field = ASSAY_MINERAL_GRADE_FIELDS.get(str(mineral))
    if field is None:
        return 0.0
    return float(getattr(plot.subsurface, field, 0.0))


def party_active_assay_jobs(world: World, party: PartyId) -> list[dict[str, Any]]:
    """All in-flight jobs for one party (sorted oldest first)."""
    out: list[dict[str, Any]] = []
    for job in _scen_assay(world).get("jobs", []):
        if isinstance(job, dict) and str(job.get("party", "")) == str(party):
            out.append(dict(job))
    out.sort(key=lambda j: int(j.get("completes_at_tick", 0)))
    return out


def party_recipe_book_summary(world: World, party: PartyId) -> dict[str, Any]:
    """Recipe book + per-mineral assay progress for the UI.

    Output:
        {
            "known": [...sorted recipe ids...],
            "progress": [{"mineral": id, "stage": int, "max_stage": 3, "last_hint": str}, ...],
            "active_jobs": [...party_active_assay_jobs entries...],
        }
    """
    ensure_party_recipe_book(world, party)
    book = sorted(world.party_recipe_books.get(str(party), set()))
    progress_rows: list[dict[str, Any]] = []
    pp = _assay_progress(world).get(str(party), {})
    if not isinstance(pp, dict):
        pp = {}
    for mineral in sorted(ASSAY_MINERAL_GRADE_FIELDS.keys()):
        stage = int(pp.get(mineral, 0))
        if stage <= 0:
            continue
        hints = ASSAY_STAGE_HINTS.get(mineral, ("", "", ""))
        last_hint = hints[min(stage, len(hints)) - 1] if stage >= 1 else ""
        progress_rows.append(
            {
                "mineral": mineral,
                "stage": stage,
                "max_stage": ASSAY_MAX_STAGE,
                "last_hint": last_hint,
            }
        )
    return {
        "known": book,
        "progress": progress_rows,
        "active_jobs": party_active_assay_jobs(world, party),
    }


def assay_mineral(world: World, party: PartyId, plot_id: PlotId, mineral: MaterialId) -> dict[str, Any]:
    """Submit a paid assay attempt — schedules a job that completes after one game-day.

    Returns ``{ok: True, job_id, completes_at_tick, stage_at_submit}`` or ``{ok: False, reason}``.
    """
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    if not plot.surveyed:
        return {"ok": False, "reason": "plot not surveyed"}
    if not _party_has_operational_lab(world, party, plot_id):
        return {"ok": False, "reason": "no operational assay_lab on plot"}
    if str(mineral) not in ASSAY_MINERAL_GRADE_FIELDS:
        return {"ok": False, "reason": "not an assayable mineral"}
    if str(mineral) in ("platinum_ore", "oil_shale", "rare_earth_ore") and not getattr(
        plot, "deep_surveyed", False
    ):
        return {"ok": False, "reason": "Tier-3 mineral — deep_survey required first"}
    grade = _plot_grade_for_mineral(world, plot_id, mineral)
    if grade < ASSAY_MIN_SUBSURFACE_GRADE:
        return {
            "ok": False,
            "reason": f"subsurface grade too low for assay ({grade:.2f} < {ASSAY_MIN_SUBSURFACE_GRADE:.2f})",
        }
    current = get_assay_stage(world, party, mineral)
    if current >= ASSAY_MAX_STAGE:
        return {"ok": False, "reason": "assay already complete for this mineral"}
    # Reject duplicate in-flight job on same (party, mineral) — one at a time.
    for j in _scen_assay(world).get("jobs", []):
        if (
            isinstance(j, dict)
            and j.get("party") == str(party)
            and j.get("mineral") == str(mineral)
        ):
            return {"ok": False, "reason": "assay already in progress for this mineral"}
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < ASSAY_COST_CENTS:
        return {"ok": False, "reason": "insufficient cash for assay fee"}
    tr = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=ASSAY_COST_CENTS,
    )
    if isinstance(tr, MoneyErr):
        return {"ok": False, "reason": tr.reason}
    st = _scen_assay(world)
    next_seq = int(st.get("next_job_seq", 0)) + 1
    st["next_job_seq"] = next_seq
    job_id = f"assay-{next_seq:06d}"
    completes_at = int(world.tick) + ASSAY_DURATION_TICKS
    job = {
        "id": job_id,
        "party": str(party),
        "plot_id": str(plot_id),
        "mineral": str(mineral),
        "stage_at_submit": int(current),
        "started_at_tick": int(world.tick),
        "completes_at_tick": int(completes_at),
    }
    st["jobs"].append(job)
    log_event(
        world,
        "assay_started",
        f"{party} began an assay of {mineral} on {plot_id} (completes around tick {completes_at})",
        party=str(party),
        plot_id=str(plot_id),
        mineral=str(mineral),
        job_id=job_id,
        cost_cents=ASSAY_COST_CENTS,
    )
    return {
        "ok": True,
        "job_id": job_id,
        "completes_at_tick": completes_at,
        "stage_at_submit": int(current),
        "cost_cents": ASSAY_COST_CENTS,
    }


def _enqueue_player_discovery_announcement(
    world: World, party: PartyId, mineral: MaterialId, unlocked: Iterable[str]
) -> None:
    """Tell Margaux the player just unlocked a Tier-2 chain (consumed by genesis_margaux_scripts)."""
    if world.scenario_id != "genesis":
        return
    if str(party) != "player":
        return
    gst = world.scenario_state.setdefault("genesis", {})
    if not isinstance(gst, dict):
        return
    pending = gst.setdefault("pending_margaux_discovery", [])
    if not isinstance(pending, list):
        gst["pending_margaux_discovery"] = []
        pending = gst["pending_margaux_discovery"]
    pending.append(
        {
            "mineral": str(mineral),
            "recipe_count": int(len(tuple(unlocked))),
            "tick": int(world.tick),
        }
    )


def _complete_assay_job(world: World, job: dict[str, Any]) -> None:
    party_s = str(job.get("party", ""))
    mineral_s = str(job.get("mineral", ""))
    if not party_s or not mineral_s:
        return
    party = PartyId(party_s)
    mineral = MaterialId(mineral_s)
    current = get_assay_stage(world, party, mineral)
    new_stage = min(ASSAY_MAX_STAGE, current + 1)
    _set_assay_stage(world, party, mineral, new_stage)
    hints = ASSAY_STAGE_HINTS.get(mineral_s, ("", "", ""))
    hint = hints[new_stage - 1] if 0 < new_stage <= len(hints) else ""
    world.npc_messages_to_player.append(
        {
            "tick": world.tick,
            "from_party": "assay_lab",
            "display_name": "Assay lab",
            "text": f"[{mineral_s}] {hint}",
        }
    )
    if len(world.npc_messages_to_player) > 96:
        world.npc_messages_to_player = world.npc_messages_to_player[-96:]
    log_event(
        world,
        "assay_stage",
        f"{party} assay of {mineral} reached stage {new_stage}/{ASSAY_MAX_STAGE}",
        party=party_s,
        mineral=mineral_s,
        stage=new_stage,
    )
    if new_stage >= ASSAY_MAX_STAGE:
        from realm.recipes import RECIPES

        unlocked = [
            rid
            for rid in ASSAY_MINERAL_RECIPE_UNLOCKS.get(mineral_s, ())
            if rid in RECIPES
        ]
        book = ensure_party_recipe_book(world, party)
        new_for_party = [rid for rid in unlocked if rid not in book]
        for rid in new_for_party:
            book.add(rid)
        log_event(
            world,
            "recipe_discovered",
            f"{party} unlocked {len(new_for_party)} recipe(s) for {mineral} ({', '.join(new_for_party) or 'no-op'})",
            party=party_s,
            mineral=mineral_s,
            recipes=",".join(new_for_party),
            recipe_count=len(new_for_party),
        )
        log_event(
            world,
            "world_feed",
            f"DISCOVERY: {mineral_s} chain unlocked — {len(new_for_party)} new recipes available "
            f"({party_s}).",
            feed_source="recipe_discovery",
            party=party_s,
            mineral=mineral_s,
            recipe_count=len(new_for_party),
        )
        _enqueue_player_discovery_announcement(world, party, mineral, new_for_party)


def tick_assay_jobs(world: World) -> None:
    """Advance any in-flight assay jobs; complete jobs whose ``completes_at_tick`` has arrived."""
    st = _scen_assay(world)
    jobs = st.get("jobs", [])
    if not isinstance(jobs, list) or not jobs:
        return
    still: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if int(job.get("completes_at_tick", 0)) <= int(world.tick):
            _complete_assay_job(world, job)
        else:
            still.append(job)
    st["jobs"] = still
