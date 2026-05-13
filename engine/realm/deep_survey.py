"""Deep survey — drill_rig + drill_bit ($20) reveals Tier-3 mineral grades on a plot.

Tier-3 grades are rolled at world gen but invisible to the standard survey/API. A successful
deep_survey:
- Consumes 1 ``drill_bit`` from the party's inventory.
- Charges ``DEEP_SURVEY_COST_CENTS`` to the system reserve.
- Schedules a job in ``world.scenario_state["deep_survey_jobs"]`` for ``DEEP_SURVEY_DURATION_TICKS``.
- On completion, flips ``plot.deep_surveyed`` to True so subsequent ``/world`` views expose
  ``platinum_grade``, ``oil_shale_grade``, ``rare_earth_grade``.
- If any Tier-3 grade is at or above ``DEEP_SURVEY_NOTABLE_GRADE``, emits a ``world_feed`` row
  so the headline panel highlights the find.
"""

from __future__ import annotations

from typing import Any, Final

from realm.event_log import log_event
from realm.ids import MaterialId, PartyId, PlotId
from realm.inventory import MatterErr
from realm.ledger import MoneyErr, party_cash_account, system_reserve_account
from realm.time_scale import TICKS_PER_GAME_DAY
from realm.world import World

DEEP_SURVEY_COST_CENTS: Final[int] = 2_000
DEEP_SURVEY_DURATION_TICKS: Final[int] = 2 * TICKS_PER_GAME_DAY
DEEP_SURVEY_NOTABLE_GRADE: Final[float] = 0.1


def _scen_deep(world: World) -> dict[str, Any]:
    st = world.scenario_state.setdefault("deep_survey_jobs", {})
    if not isinstance(st, dict):
        world.scenario_state["deep_survey_jobs"] = {}
        st = world.scenario_state["deep_survey_jobs"]
    st.setdefault("jobs", [])
    return st


def _party_has_operational_drill_rig(world: World, party: PartyId, plot_id: PlotId) -> bool:
    from realm.decay import building_effective_for_bonuses
    from realm.time_scale import building_operational

    for b in world.plot_buildings:
        if b.get("party") != str(party):
            continue
        if b.get("plot_id") != str(plot_id):
            continue
        if b.get("building_id") != "drill_rig":
            continue
        if not building_operational(b, at_tick=world.tick):
            continue
        if not building_effective_for_bonuses(b):
            continue
        return True
    return False


def party_active_deep_survey_jobs(world: World, party: PartyId) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for job in _scen_deep(world).get("jobs", []):
        if isinstance(job, dict) and str(job.get("party", "")) == str(party):
            out.append(dict(job))
    out.sort(key=lambda j: int(j.get("completes_at_tick", 0)))
    return out


def deep_survey(world: World, party: PartyId, plot_id: PlotId) -> dict[str, Any]:
    """Start a deep survey on a player-owned plot with a drill_rig and ≥1 drill_bit."""
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "unknown plot"}
    if plot.owner != party:
        return {"ok": False, "reason": "not your plot"}
    if not plot.surveyed:
        return {"ok": False, "reason": "plot must be surveyed first"}
    if getattr(plot, "deep_surveyed", False):
        return {"ok": False, "reason": "plot already deep-surveyed"}
    if not _party_has_operational_drill_rig(world, party, plot_id):
        return {"ok": False, "reason": "no operational drill_rig on plot"}
    drill = MaterialId("drill_bit")
    if world.inventory.qty(party, drill) < 1:
        return {"ok": False, "reason": "drill_bit required (1 unit consumed)"}
    for j in _scen_deep(world).get("jobs", []):
        if isinstance(j, dict) and j.get("party") == str(party) and j.get("plot_id") == str(plot_id):
            return {"ok": False, "reason": "deep survey already in progress for this plot"}
    cash = party_cash_account(party)
    if world.ledger.balance(cash) < DEEP_SURVEY_COST_CENTS:
        return {"ok": False, "reason": "insufficient cash for deep survey fee"}
    rm = world.inventory.remove(party, drill, 1)
    if isinstance(rm, MatterErr):
        return {"ok": False, "reason": rm.reason}
    tr = world.ledger.transfer(
        debit=cash,
        credit=system_reserve_account(),
        amount_cents=DEEP_SURVEY_COST_CENTS,
    )
    if isinstance(tr, MoneyErr):
        ad = world.inventory.add(party, drill, 1)
        if isinstance(ad, MatterErr):
            raise RuntimeError(f"failed to rollback drill_bit: {ad.reason}")
        return {"ok": False, "reason": tr.reason}
    st = _scen_deep(world)
    next_seq = int(st.get("next_job_seq", 0)) + 1
    st["next_job_seq"] = next_seq
    job_id = f"deep-{next_seq:06d}"
    completes_at = int(world.tick) + DEEP_SURVEY_DURATION_TICKS
    job = {
        "id": job_id,
        "party": str(party),
        "plot_id": str(plot_id),
        "started_at_tick": int(world.tick),
        "completes_at_tick": int(completes_at),
    }
    st["jobs"].append(job)
    log_event(
        world,
        "deep_survey_started",
        f"{party} started a deep survey of {plot_id} (drill_bit consumed; completes around tick {completes_at})",
        party=str(party),
        plot_id=str(plot_id),
        job_id=job_id,
        cost_cents=DEEP_SURVEY_COST_CENTS,
    )
    return {
        "ok": True,
        "job_id": job_id,
        "completes_at_tick": completes_at,
        "cost_cents": DEEP_SURVEY_COST_CENTS,
    }


def _complete_deep_survey_job(world: World, job: dict[str, Any]) -> None:
    plot_id = PlotId(str(job.get("plot_id", "")))
    party_s = str(job.get("party", ""))
    plot = world.plots.get(plot_id)
    if plot is None:
        return
    plot.deep_surveyed = True
    from realm.actions import create_survey_report

    if party_s:
        create_survey_report(world, PartyId(party_s), plot_id, is_deep=True)
    grades = {
        "platinum_grade": plot.subsurface.platinum_grade,
        "oil_shale_grade": plot.subsurface.oil_shale_grade,
        "rare_earth_grade": plot.subsurface.rare_earth_grade,
    }
    notable = {k: v for k, v in grades.items() if v >= DEEP_SURVEY_NOTABLE_GRADE}
    log_event(
        world,
        "deep_survey_complete",
        f"{party_s} deep survey of {plot_id} complete (notable: {sorted(notable.keys()) or 'none'})",
        party=party_s,
        plot_id=str(plot_id),
        notable=",".join(sorted(notable.keys())),
        platinum_grade=float(grades["platinum_grade"]),
        oil_shale_grade=float(grades["oil_shale_grade"]),
        rare_earth_grade=float(grades["rare_earth_grade"]),
    )
    if notable:
        log_event(
            world,
            "world_feed",
            f"FIND: Deep survey at {plot_id} hit something. Check your survey results "
            f"({', '.join(sorted(notable.keys()))}).",
            feed_source="deep_survey_find",
            party=party_s,
            plot_id=str(plot_id),
        )
    world.npc_messages_to_player.append(
        {
            "tick": world.tick,
            "from_party": "drill_rig",
            "display_name": "Drill rig",
            "text": (
                f"Deep survey at {plot_id} complete — "
                + (
                    "found "
                    + ", ".join(f"{k} {v:.2f}" for k, v in sorted(notable.items()))
                    if notable
                    else "no notable Tier-3 deposits."
                )
            ),
        }
    )
    if len(world.npc_messages_to_player) > 96:
        world.npc_messages_to_player = world.npc_messages_to_player[-96:]


def tick_deep_survey_jobs(world: World) -> None:
    """Complete any deep survey jobs whose ``completes_at_tick`` has arrived."""
    st = _scen_deep(world)
    jobs = st.get("jobs", [])
    if not isinstance(jobs, list) or not jobs:
        return
    still: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if int(job.get("completes_at_tick", 0)) <= int(world.tick):
            _complete_deep_survey_job(world, job)
        else:
            still.append(job)
    st["jobs"] = still
