"""Seasonal calendar (Phase 8 / Sub-phase 8A).

The simulation year is 365 game-days = ``365 * TICKS_PER_GAME_DAY = 525_600``
ticks. The year is divided into four seasons that gate agricultural output,
modulate fuel demand on laborers, and emit world-feed narration on transitions.

Public surface
--------------
* ``Season`` enum
* ``current_season(world)``                       — which season we're in right now
* ``current_game_day_of_year(world)``             — 1..365
* ``current_game_year(world)``                    — 0, 1, 2, ... (year 0 starts at tick 0)
* ``yield_modifier(world, recipe_id, plot)``      — output multiplier (1.0 = no effect)
* ``recipe_blocked_by_season(world, recipe_id, plot)`` — (blocked: bool, reason: str)
* ``fuel_decay_per_day_for_season(season)``       — replaces the constant in laborers.py
* ``tick_seasons(world)``                         — emit world-feed entries on day boundaries

Design notes
------------
* Determinism: nothing here samples RNG. Modifiers and season look-ups are pure
  functions of ``world.tick``. Tick-time state changes (the "did we already emit
  the transition for this year?" guard) live in
  ``world.scenario_state["seasons"]``.
* Island geography: per Phase 8 brief, the four canonical islands are
  A=0 (northern), B=1 (tropical, year-round grain at half rate), C=2 (southern),
  D=3 (northern, arid). Worlds with more islands fall back to ``SOUTHERN``
  defaults — they still get fishing in winter, just no special tropical bonus.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from realm.core.time_scale import TICKS_PER_GAME_DAY
from realm.events.event_log import log_event

if TYPE_CHECKING:  # pragma: no cover
    from realm.world.world import Plot, World


# ─────────────────────────────────────────────────────────────────────────
# Calendar constants
# ─────────────────────────────────────────────────────────────────────────

DAYS_PER_YEAR = 365
TICKS_PER_GAME_YEAR = TICKS_PER_GAME_DAY * DAYS_PER_YEAR  # 525_600

# Day-of-year (1-indexed) at which each season *begins*.
SPRING_START = 1
SUMMER_START = 91
AUTUMN_START = 241
HARVEST_DECLINE_START = 271
WINTER_START = 301


class Season(str, Enum):
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"


# Island role hard-coded for the 4-island Genesis layout per Phase 8 brief.
# ``int(island_id)`` -> role. Unknown islands default to "southern".
NORTHERN_ISLAND_IDS: frozenset[int] = frozenset({0, 3})  # A, D
TROPICAL_ISLAND_IDS: frozenset[int] = frozenset({1})  # B
SOUTHERN_ISLAND_IDS: frozenset[int] = frozenset({2})  # C


# Recipe-class buckets. Maintained as small explicit lists rather than
# pattern-matching so accidentally renaming a recipe doesn't silently break
# the seasonal gate.
AGRICULTURAL_RECIPES: frozenset[str] = frozenset({"grow_grain"})
TIMBER_RECIPES: frozenset[str] = frozenset({"chop_timber", "hand_chop"})
FISHING_RECIPES: frozenset[str] = frozenset({"fishing"})


# ─────────────────────────────────────────────────────────────────────────
# Time look-ups
# ─────────────────────────────────────────────────────────────────────────


def current_game_year(world: "World") -> int:
    """Game year (0-indexed). Year 0 starts at tick 0."""
    return int(world.tick) // TICKS_PER_GAME_YEAR


def current_game_day_of_year(world: "World") -> int:
    """1..365 inclusive — day 1 is the first day of Spring."""
    tick_in_year = int(world.tick) % TICKS_PER_GAME_YEAR
    return (tick_in_year // TICKS_PER_GAME_DAY) + 1


def current_season(world: "World") -> Season:
    """Which season ``world.tick`` falls in."""
    return _season_for_day_of_year(current_game_day_of_year(world))


def _season_for_day_of_year(day: int) -> Season:
    if day < SUMMER_START:
        return Season.SPRING
    if day < AUTUMN_START:
        return Season.SUMMER
    if day < WINTER_START:
        return Season.AUTUMN
    return Season.WINTER


# ─────────────────────────────────────────────────────────────────────────
# Modifiers — agriculture / timber / fishing
# ─────────────────────────────────────────────────────────────────────────


def _island_role(world: "World", plot: "Plot | None") -> str:
    """Return ``"northern" | "tropical" | "southern"`` for the plot's island.

    Islands are stored as a side-mapping in ``world.scenario_state["plot_islands"]``
    (``str(plot_id) -> int``) rather than on the ``Plot`` dataclass directly.
    Worlds without that mapping (older Frontier saves, ad-hoc test worlds)
    fall back to ``"southern"``.
    """
    if plot is None:
        return "southern"
    mapping = world.scenario_state.get("plot_islands") if hasattr(world, "scenario_state") else None
    if not mapping:
        return "southern"
    isl_raw = mapping.get(str(plot.plot_id))
    if isl_raw is None:
        return "southern"
    try:
        isl = int(isl_raw)
    except (TypeError, ValueError):
        return "southern"
    if isl in TROPICAL_ISLAND_IDS:
        return "tropical"
    if isl in NORTHERN_ISLAND_IDS:
        return "northern"
    return "southern"


def yield_modifier(world: "World", recipe_id: str, plot: "Plot | None" = None) -> float:
    """Multiplicative output modifier for completion-time output computation.

    1.0 is "no effect". 0.0 means the recipe produces nothing this run.
    Composes multiplicatively with maintenance / labor / terrain modifiers
    already in ``effective_outputs_for_completion``.
    """
    season = current_season(world)
    role = _island_role(world, plot)
    day = current_game_day_of_year(world)

    if recipe_id in AGRICULTURAL_RECIPES:
        return _agriculture_modifier(season, role, day)
    if recipe_id in TIMBER_RECIPES:
        return _timber_modifier(season)
    if recipe_id in FISHING_RECIPES:
        return _fishing_modifier(season, role)
    return 1.0


def _agriculture_modifier(season: Season, role: str, day: int) -> float:
    if season is Season.SPRING:
        return 1.0
    if season is Season.SUMMER:
        return 1.2
    if season is Season.AUTUMN:
        # Harvest window (day 241..270) surges, then declines (271..300).
        if day < HARVEST_DECLINE_START:
            return 1.5
        return 0.7
    # Winter — only tropical islands grow, at half rate.
    if role == "tropical":
        return 0.5
    return 0.0


def _timber_modifier(season: Season) -> float:
    if season is Season.WINTER:
        return 0.6
    return 1.0


def _fishing_modifier(season: Season, role: str) -> float:
    if season is not Season.WINTER:
        return 1.0
    if role == "northern":
        return 0.0  # frozen waters
    return 0.7  # southern + tropical fish slower in winter


# ─────────────────────────────────────────────────────────────────────────
# Start-time blocks (refuse to *start* a recipe whose season modifier is 0)
# ─────────────────────────────────────────────────────────────────────────


def recipe_blocked_by_season(
    world: "World", recipe_id: str, plot: "Plot | None" = None
) -> tuple[bool, str]:
    """Should ``start_production`` refuse this recipe right now?

    Returns ``(blocked, reason)``. ``blocked=False`` means the recipe is
    seasonally permitted — output may still be reduced via ``yield_modifier``
    but the run is allowed to begin.
    """
    if yield_modifier(world, recipe_id, plot) > 0.0:
        return False, ""
    season = current_season(world)
    if recipe_id in AGRICULTURAL_RECIPES:
        return True, f"grain growth suspended in {season.value} on this island"
    if recipe_id in FISHING_RECIPES:
        return True, f"fishing suspended in {season.value} on this island (frozen waters)"
    return True, f"{recipe_id} unavailable in {season.value}"


# ─────────────────────────────────────────────────────────────────────────
# Fuel decay modulation (consumed by laborers._apply_needs_decay)
# ─────────────────────────────────────────────────────────────────────────


def fuel_decay_per_day_for_season(season: Season) -> float:
    """Per Sub-phase 8A.A3: fuel need decays faster as it gets colder.

    Season multipliers are applied to :data:`~realm.population.laborers.FUEL_DECAY_PER_DAY`
    so tuning the base rate in ``laborers.py`` propagates here automatically.
    """
    from realm.population.laborers import FUEL_DECAY_PER_DAY

    if season is Season.WINTER:
        return FUEL_DECAY_PER_DAY * (7.0 / 3.0)
    if season is Season.AUTUMN:
        return FUEL_DECAY_PER_DAY * (4.0 / 3.0)
    return FUEL_DECAY_PER_DAY  # Spring + Summer baseline


# ─────────────────────────────────────────────────────────────────────────
# World-feed narration on season boundaries
# ─────────────────────────────────────────────────────────────────────────


SEASON_TRANSITION_MESSAGES: dict[int, str] = {
    SPRING_START: "Growing season begins — agricultural yields are improving.",
    SUMMER_START: "Peak production season. Grain and timber output at maximum.",
    AUTUMN_START: "Harvest window open. Grain yields surging for the next 30 days.",
    HARVEST_DECLINE_START: (
        "Harvest complete. Agricultural output declining into winter."
    ),
    WINTER_START: (
        "Winter has arrived. Fuel demand rising. Grain production "
        "suspended on most islands."
    ),
}


def tick_seasons(world: "World") -> None:
    """Emit world-feed entries when crossing a season boundary.

    The guard is stored as ``(year, day)`` in ``world.scenario_state["seasons"]
    ["last_announced"]`` so repeated calls within the same day are idempotent
    and reloading a save doesn't re-announce events that already fired.
    """
    day = current_game_day_of_year(world)
    msg = SEASON_TRANSITION_MESSAGES.get(day)
    if msg is None:
        return
    year = current_game_year(world)
    state = world.scenario_state.setdefault("seasons", {})
    last = state.get("last_announced")
    key = [year, day]
    if last == key:
        return
    state["last_announced"] = key
    log_event(
        world,
        "world_feed",
        msg,
        event_class="season_transition",
        year=year,
        day_of_year=day,
        season=_season_for_day_of_year(day).value,
    )
