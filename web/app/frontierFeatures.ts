import type { TabId } from "./frontierMenu";

/** Surface area for players — extend rows as systems land in the engine. */
export type FeatureLane = "live" | "stub" | "planned";

export type FrontierFeature = {
  id: string;
  title: string;
  detail: string;
  lane: FeatureLane;
  /** Optional: jump from Atlas card */
  jumpTab?: TabId;
};

export const FRONTIER_FEATURES: FrontierFeature[] = [
  {
    id: "map_god_view",
    title: "Pan / zoom frontier map",
    detail:
      "Large frontier (48×36 plots): coherent biomes from engine noise; UI draws irregular regions (shared vertex jitter) with pan/zoom and terrain / satellite / political styles.",
    lane: "live",
    jumpTab: "world",
  },
  {
    id: "worldbox_sprites",
    title: "Custom sprites & walk cycles",
    detail: "No bespoke sprite sheets or unit walk cycles yet — that is art plus atlas work.",
    lane: "planned",
    jumpTab: "codex",
  },
  {
    id: "worldbox_sfx_assets",
    title: "Per-action SFX (asset pack)",
    detail: "Prototype uses simple synthesized stings; no per-action sampled SFX until Audio plus an asset pack.",
    lane: "planned",
    jumpTab: "codex",
  },
  {
    id: "worldbox_particles_engine",
    title: "Heavy particles / WebGL",
    detail: "FX are 2D DOM plus motion and light canvas bursts — enough for prototype; smoke, lightning, etc. can move to canvas/WebGL later.",
    lane: "planned",
    jumpTab: "codex",
  },
  {
    id: "sim_clock",
    title: "Running sim clock",
    detail:
      "Engine ticks advance on a client timer (pause and speed presets). Solo pacing only — multiplayer wall-clock comes later.",
    lane: "live",
    jumpTab: "world",
  },
  {
    id: "claim_survey",
    title: "Claim & survey",
    detail: "Claim empty plots; survey owned land for subsurface grades (ore/clay/coal hints).",
    lane: "live",
    jumpTab: "world",
  },
  {
    id: "production",
    title: "Recipes & production runs",
    detail: "Start runs on surveyed plots; ticks count down in active production.",
    lane: "live",
    jumpTab: "world",
  },
  {
    id: "market_book",
    title: "Market asks + depth chart",
    detail: "List asks, snapshot best prices per tick into history for Recharts.",
    lane: "live",
    jumpTab: "market",
  },
  {
    id: "shipping",
    title: "Caravan shipping",
    detail: "Pay fees, goods in transit by tick distance between owned plots.",
    lane: "live",
    jumpTab: "logistics",
  },
  {
    id: "persistence",
    title: "SQLite save / load",
    detail: "Write a SQLite snapshot from the Chronicle tab and reload it later in the same browser session.",
    lane: "live",
    jumpTab: "log",
  },
  {
    id: "event_log",
    title: "Action chronicle",
    detail: "Engine events appended each action for debugging and vibe.",
    lane: "live",
    jumpTab: "log",
  },
  {
    id: "buildings",
    title: "Plot buildings",
    detail:
      "Spend cash to place field stockade (+party storage units), tool cache (−10% recipe labor cash on plot), or watch hut (−3% labor on plot).",
    lane: "live",
    jumpTab: "world",
  },
  {
    id: "hire_stub",
    title: "Hire & payroll",
    detail:
      "Signing bonus opens employment; optional recurring wage every N ticks. Each production run routes 40% of recipe labor cash to hires (split evenly).",
    lane: "live",
    jumpTab: "hire",
  },
  {
    id: "supply_stub",
    title: "Supply contracts",
    detail:
      "Propose → accept → fulfill by deadline tick; breach marks supplier reputation. Deposits / liquidated damages when terms say so.",
    lane: "live",
    jumpTab: "pacts",
  },
  {
    id: "building_fx",
    title: "More building effects",
    detail: "Additional structure types (energy, throughput multipliers) beyond the three catalog buildings — not shipped yet.",
    lane: "planned",
  },
  {
    id: "labor_output",
    title: "Hired labor in production",
    detail: "40% of each recipe's labor cash goes to employed parties on that payroll (split evenly); remainder to system reserve.",
    lane: "live",
    jumpTab: "hire",
  },
  {
    id: "order_book_full",
    title: "Bids + matching engine",
    detail: "Limit bids, escrow, crossing, sell-into-bids — Phase 1 depth.",
    lane: "live",
    jumpTab: "market",
  },
  {
    id: "p2p_trade",
    title: "Direct player trades",
    detail: "P2P atomic exchange in Bazaar — multiplayer scale later.",
    lane: "live",
    jumpTab: "market",
  },
  {
    id: "schematic_plot",
    title: "Plot schematic (recipe chain)",
    detail:
      "Per surveyed plot: build an ordered recipe pipeline with drag-reorder; validate against your current inventory as if runs complete in sequence (solo planning aid).",
    lane: "live",
    jumpTab: "schematic",
  },
  {
    id: "lua_services",
    title: "Programmable services (Lua)",
    detail: "Primitive 9 sandbox — Phase 4+ in roadmap.",
    lane: "planned",
  },
];
