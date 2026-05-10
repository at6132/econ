/** localStorage key — bump if onboarding copy/steps change materially */
export const FRONTIER_ONBOARD_STORAGE_KEY = "realm_frontier_onboard_v8";

/** Map style (terrain / satellite / political) — bump to reset everyone to default */
export const FRONTIER_MAP_STYLE_STORAGE_KEY = "realm_frontier_map_style_v2";

/** Simulation clock: paused when "1" */
export const FRONTIER_SIM_PAUSED_STORAGE_KEY = "realm_frontier_sim_paused_v1";

/** 0 = slow, 1 = normal, 2 = fast (real-time ms between engine ticks) */
export const FRONTIER_SIM_SPEED_STORAGE_KEY = "realm_frontier_sim_speed_v1";

/** Must match `SURVEY_COST_CENTS` in `engine/realm/actions.py` (UI copy + affordance checks). */
export const FRONTIER_SURVEY_COST_CENTS = 50_000;
