/** localStorage key — bump if onboarding copy/steps change materially */
export const FRONTIER_ONBOARD_STORAGE_KEY = "realm_frontier_onboard_v9";

/** Map style (terrain / satellite / political) — bump to reset everyone to default */
export const FRONTIER_MAP_STYLE_STORAGE_KEY = "realm_frontier_map_style_v2";

/** Simulation clock: paused when "1" */
export const FRONTIER_SIM_PAUSED_STORAGE_KEY = "realm_frontier_sim_paused_v1";

/** 0 = slow, 1 = normal, 2 = fast (real-time ms between engine ticks) */
export const FRONTIER_SIM_SPEED_STORAGE_KEY = "realm_frontier_sim_speed_v1";

/** Last dev-reset scenario (frontier | bootstrapper | speculator | cartel | millrace | archive) */
export const FRONTIER_SCENARIO_STORAGE_KEY = "realm_frontier_scenario_v1";

/** Must match `engine/realm/actions.py` SURVEY_COST_CENTS */
export const FRONTIER_SURVEY_COST_CENTS = 50_000;

/** Map mesh renderer: `svg` (default) or WebGL `pixi` — bump to reset */
export const FRONTIER_MAP_RENDERER_STORAGE_KEY = "realm_map_renderer_v1";

/** localStorage: `${prefix}${plotId}` → JSON string[] of recipe ids */
export const PLOT_SCHEMATIC_STORAGE_PREFIX = "realm_plot_schematic_v1:";
