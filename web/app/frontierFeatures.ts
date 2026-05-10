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
    id: "manual_tick",
    title: "Manual turns",
    detail: "Time advances only when you press Advance tick — solo pacing, no idle sim.",
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
    detail: "Snapshot world to saves/realm_dev.sqlite (engine path).",
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
    detail: "Spend cash, record structure on plot — no throughput bonus yet.",
    lane: "stub",
    jumpTab: "world",
  },
  {
    id: "hire_stub",
    title: "NPC hire (signing bonus)",
    detail: "Stub employment record; each production run pays 40% of recipe labor to hired parties (split evenly).",
    lane: "live",
    jumpTab: "contracts",
  },
  {
    id: "supply_stub",
    title: "Supply contracts (deadline + fulfill)",
    detail: "Propose → accept → fulfill; miss deliver_by_tick and supplier is breached (buyer reputation unchanged).",
    lane: "live",
    jumpTab: "contracts",
  },
  {
    id: "building_fx",
    title: "Building modifiers",
    detail: "Structures affecting recipes, storage caps, or energy — engine TBD.",
    lane: "planned",
  },
  {
    id: "labor_output",
    title: "Hired labor in production",
    detail: "40% of recipe labor_cents routed to employees on stub_hires (see contracts tab).",
    lane: "live",
    jumpTab: "contracts",
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
    title: "Plot schematic view",
    detail: "Flowchart of boxes/arrows per realm_docs plot view.",
    lane: "planned",
    jumpTab: "world",
  },
  {
    id: "lua_services",
    title: "Programmable services (Lua)",
    detail: "Primitive 9 sandbox — Phase 4+ in roadmap.",
    lane: "planned",
  },
];
