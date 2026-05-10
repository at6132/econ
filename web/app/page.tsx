"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { FRONTIER_FEATURES } from "./frontierFeatures";
import {
  displayMaterial,
  displayParty,
  formatDeliverBy,
  formatQtyTimesMaterial,
  formatRelativeTicksFromNow,
  formatUsdFromCents,
  formatUsdPerUnitFromCentsPerUnit,
  manhattanPlotIds,
  parseDollarsToCents,
  prettifyChronicleMessage,
  previewShipArriveTick,
  previewShipFeeCents,
} from "./formatters";
import {
  FRONTIER_MAP_RENDERER_STORAGE_KEY,
  FRONTIER_MAP_STYLE_STORAGE_KEY,
  FRONTIER_ONBOARD_STORAGE_KEY,
  FRONTIER_SIM_PAUSED_STORAGE_KEY,
  FRONTIER_SIM_SPEED_STORAGE_KEY,
  FRONTIER_SCENARIO_STORAGE_KEY,
  FRONTIER_SURVEY_COST_CENTS,
} from "./frontierConstants";
import { getFrontierMenu, getFrontierTabCycleOrder, type TabId } from "./frontierMenu";
import { FrontierCommandPalette } from "./FrontierCommandPalette";
import { FrontierSettingsModal } from "./FrontierSettingsModal";
import { FrontierTopNav } from "./FrontierTopNav";
import { playFrontierSfx, resumeFrontierAudio } from "./frontierSfx";
import { collectBazaarSymbolIds, normalizeBazaarSymbolId } from "./bazaarSymbols";
import { PlotSchematicPanel } from "./PlotSchematicPanel";
import type { SchematicRecipe } from "./plotSchematic";
import { buildOrganicMesh } from "./mapOrganicMesh";
import { computeStarterHintPlotIds } from "./mapStarterHints";
import type { MapFxEvent, MapFxKind } from "./mapFxTypes";
import { bookMidpointCentsPerUnit } from "./marketPriceHints";
import { MarketHistoryChart, type MarketHistorySnap } from "./MarketHistoryChart";
import { OnboardingModal } from "./OnboardingModal";
import { RealmMapFxOverlay } from "./RealmMapFxOverlay";
import { RealmMapMeshPixi } from "./RealmMapMeshPixi";
import { RealmMapMeshSvg } from "./RealmMapMeshSvg";
import { RealmMapParticlesCanvas } from "./RealmMapParticlesCanvas";
import { SHOW_INTERNAL_ATLAS_AND_DEV_CONTRACTS } from "./realmUiFlags";
import { useRealmToast } from "./realmToast";

const MAP_PAD = 4;

const DEV_RESET_SCENARIOS = ["frontier", "bootstrapper", "speculator", "cartel"] as const;
type DevResetScenarioId = (typeof DEV_RESET_SCENARIOS)[number];

/** Real-time gap between engine ticks when the sim is running (solo pacing; not wall-clock canon). */
const SIM_SPEEDS_MS: readonly [number, number, number] = [2800, 1400, 700];
const SIM_SPEED_LABELS = ["Slow", "Normal", "Fast"] as const;

const FX_HUE: Record<MapFxKind, number> = {
  claim: 52,
  survey: 188,
  build: 38,
  trade: 132,
  produce: 24,
  tick: 270,
  ship: 210,
  hire: 285,
  contract: 0,
};

function panelHeadline(tab: TabId): string {
  for (const g of getFrontierMenu()) {
    const it = g.items.find((i) => i.tab === tab);
    if (it) return it.label;
  }
  return tab;
}

type PlotDto = {
  id: string;
  x: number;
  y: number;
  terrain: string;
  owner: string | null;
  surveyed: boolean;
  subsurface?: Record<string, number>;
  /** Surveyed plots: recipe ids the engine allows on this terrain (omitted until surveyed). */
  recipe_ids?: string[];
};

type RecipeDto = {
  id: string;
  display_name: string;
  inputs: Record<string, number>;
  outputs: Record<string, number>;
  duration_ticks: number;
  labor_cents: number;
};

type ActiveProductionDto = {
  run_id: string;
  party: string;
  plot_id: string;
  recipe_id: string;
  ticks_remaining: number;
};

type InTransitDto = {
  id: string;
  party: string;
  material: string;
  qty: number;
  dest_plot_id: string;
  arrive_tick: number;
};

type MarketAskDto = {
  order_id: string;
  party: string;
  material: string;
  qty: number;
  price_per_unit_cents: number;
  side?: string;
};

type MarketBidDto = {
  order_id: string;
  party: string;
  material: string;
  qty: number;
  max_price_per_unit_cents: number;
  side?: string;
};

function liveBestAskForMaterial(asks: MarketAskDto[] | undefined, m: string): number | null {
  let best: number | null = null;
  for (const a of asks ?? []) {
    if (a.material !== m) continue;
    if (best == null || a.price_per_unit_cents < best) best = a.price_per_unit_cents;
  }
  return best;
}

function liveBestBidForMaterial(bids: MarketBidDto[] | undefined, m: string): number | null {
  let best: number | null = null;
  for (const b of bids ?? []) {
    if (b.material !== m) continue;
    if (best == null || b.max_price_per_unit_cents > best) best = b.max_price_per_unit_cents;
  }
  return best;
}

type EventLogEntryDto = {
  tick: number;
  kind: string;
  message: string;
  party?: string;
  recipe_id?: string;
  material?: string;
  qty?: number;
};

type BuildingCatalogDto = {
  id: string;
  label: string;
  kind?: string;
  /** Simple buildings only */
  cost_cents?: number;
  /** Contracted workshops — engine requires build_mode */
  self_shell_cents?: number;
  self_contractor_fee_cents?: number;
  self_materials?: Record<string, number>;
  turnkey_total_cents?: number;
};

type PlotBuildingDto = {
  instance_id?: string;
  condition_bps?: number;
  plot_id: string;
  party: string;
  building_id: string;
  label: string;
  cost_cents: number;
  build_mode?: string;
};

type StubHireDto = {
  employer: string;
  employee: string;
  signing_bonus_cents: number;
  tick: number;
  contract_id?: string;
};

type HireCatalogRow = {
  party: string;
  role: string;
  suggested_signing_cents: number;
};

type SupplyContractDto = {
  id: string;
  kind?: string;
  status?: string;
  supplier?: string;
  buyer?: string;
  material?: string;
  qty?: number;
  total_price_cents?: number;
  deliver_by_tick?: number;
};

type WorldDto = {
  seed: number;
  tick: number;
  scenario_id?: string;
  market_intel_expires_tick?: number;
  market_intel_active?: boolean;
  market_history_free_window_ticks?: number;
  plots: PlotDto[];
  balances_cents: Record<string, number>;
  inventory: Record<string, Record<string, number>>;
  parties: string[];
  recipes: RecipeDto[];
  active_production: ActiveProductionDto[];
  in_transit?: InTransitDto[];
  market_asks?: MarketAskDto[];
  market_bids?: MarketBidDto[];
  reputation?: Record<string, { honored: number; breached: number }>;
  contracts?: Record<string, unknown>[];
  event_log?: EventLogEntryDto[];
  building_catalog?: BuildingCatalogDto[];
  plot_buildings?: PlotBuildingDto[];
  stub_hires?: StubHireDto[];
  market_history?: MarketHistorySnap[];
  hire_catalog?: HireCatalogRow[];
};

function SectionTitle({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <h3 className="realm-section-title" style={style}>
      {children}
    </h3>
  );
}

function readSimPausedFromStorage(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(FRONTIER_SIM_PAUSED_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function readSimSpeedIdxFromStorage(): 0 | 1 | 2 {
  if (typeof window === "undefined") return 1;
  try {
    const sp = localStorage.getItem(FRONTIER_SIM_SPEED_STORAGE_KEY);
    if (sp === "0" || sp === "1" || sp === "2") return Number(sp) as 0 | 1 | 2;
  } catch {
    /* ignore */
  }
  return 1;
}

function readDevResetScenarioFromStorage(): DevResetScenarioId {
  if (typeof window === "undefined") return "frontier";
  try {
    const s = localStorage.getItem(FRONTIER_SCENARIO_STORAGE_KEY);
    if (s && (DEV_RESET_SCENARIOS as readonly string[]).includes(s)) return s as DevResetScenarioId;
  } catch {
    /* ignore */
  }
  return "frontier";
}

export default function HomePage() {
  const { pushToast } = useRealmToast();
  const [world, setWorld] = useState<WorldDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const tickInFlightRef = useRef(false);
  const [simPaused, setSimPaused] = useState(readSimPausedFromStorage);
  const [simSpeedIdx, setSimSpeedIdx] = useState<0 | 1 | 2>(readSimSpeedIdxFromStorage);
  const [devResetScenario, setDevResetScenario] = useState<DevResetScenarioId>(readDevResetScenarioFromStorage);
  const [tab, setTab] = useState<TabId>("world");
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [selectedPlotId, setSelectedPlotId] = useState<string | null>(null);
  const [shipFrom, setShipFrom] = useState("p-0-0");
  const [shipTo, setShipTo] = useState("p-1-0");
  const [shipMaterial, setShipMaterial] = useState("timber");
  const [shipQty, setShipQty] = useState("1");
  const [bazaarSymbol, setBazaarSymbol] = useState("timber");
  const [bazaarActiveId, setBazaarActiveId] = useState("timber");
  const [sellQty, setSellQty] = useState("1");
  const [sellPriceDollars, setSellPriceDollars] = useState("5.00");
  const [bidQty, setBidQty] = useState("1");
  const [bidMaxDollars, setBidMaxDollars] = useState("5.00");
  const [sellFillQty, setSellFillQty] = useState("1");
  const [p2pRole, setP2pRole] = useState<"sell" | "buy">("sell");
  const [p2pParty, setP2pParty] = useState("t1_consumer");
  const [p2pMaterial, setP2pMaterial] = useState("grain");
  const [p2pQty, setP2pQty] = useState("1");
  const [p2pTotalDollars, setP2pTotalDollars] = useState("0.50");
  const [lastContractId, setLastContractId] = useState<string | null>(null);
  const [supplyCounterparty, setSupplyCounterparty] = useState("t1_consumer");
  const [supplyYouAre, setSupplyYouAre] = useState<"supplier" | "buyer">("supplier");
  const [supplyMaterial, setSupplyMaterial] = useState("grain");
  const [supplyQty, setSupplyQty] = useState("2");
  const [supplyTotalDollars, setSupplyTotalDollars] = useState("0.80");
  const [supplyDueTicks, setSupplyDueTicks] = useState("10");
  const [stubPhase2ContractId, setStubPhase2ContractId] = useState("");
  const [stubLoanBorrower, setStubLoanBorrower] = useState("t1_consumer");
  const [stubLoanPrincipalDollars, setStubLoanPrincipalDollars] = useState("100.00");
  const [stubLoanRepayDollars, setStubLoanRepayDollars] = useState("110.00");
  const [stubLoanDueTicks, setStubLoanDueTicks] = useState("15");
  const [stubEquityIssuer, setStubEquityIssuer] = useState("player");
  const [stubEquityInvestor, setStubEquityInvestor] = useState("t1_consumer");
  const [stubEquityInvestmentDollars, setStubEquityInvestmentDollars] = useState("20.00");
  const [stubEquityDivCents, setStubEquityDivCents] = useState("25");
  const [stubEquityDivTicks, setStubEquityDivTicks] = useState("4");
  const [stubServiceProvider, setStubServiceProvider] = useState("player");
  const [stubServiceSubscriber, setStubServiceSubscriber] = useState("t1_consumer");
  const [stubServiceFeeDollars, setStubServiceFeeDollars] = useState("5.00");
  const [stubServiceDurationTicks, setStubServiceDurationTicks] = useState("8");
  const [bazaarAdvancedOpen, setBazaarAdvancedOpen] = useState(false);
  const [advBidIceberg, setAdvBidIceberg] = useState("");
  const [advBidHonored, setAdvBidHonored] = useState("0");
  const [advAskIceberg, setAdvAskIceberg] = useState("");
  const [advAskHonored, setAdvAskHonored] = useState("0");
  const [commandOpen, setCommandOpen] = useState(true);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const mapViewportRef = useRef<HTMLDivElement>(null);
  const [viewportPx, setViewportPx] = useState({ w: 720, h: 520 });
  const [mapFx, setMapFx] = useState<MapFxEvent[]>([]);
  const mapFxSeq = useRef(0);
  const sparkSeqRef = useRef(0);
  const [sparks, setSparks] = useState<{ id: number; cx: number; cy: number; hue: number }[]>([]);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [mapZoom, setMapZoom] = useState(1);
  const [mapStyle, setMapStyle] = useState<"terrain" | "satellite" | "political">("terrain");
  const [mapRenderer, setMapRenderer] = useState<"svg" | "pixi">("svg");
  const mapNavSuppress = useRef(false);
  const panDragRef = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null);
  const mapPanPointerId = useRef<number | null>(null);
  /** True only after we capture the pointer for an active pan — immediate capture breaks plot clicks on the SVG. */
  const mapPanCaptureActiveRef = useRef(false);
  const panRef = useRef(pan);
  const mapZoomRef = useRef(mapZoom);
  const didPan = useRef(false);
  const didInitPan = useRef(false);

  panRef.current = pan;
  mapZoomRef.current = mapZoom;
  const tabRef = useRef<TabId>(tab);
  tabRef.current = tab;
  const paletteOpenRef = useRef(paletteOpen);
  paletteOpenRef.current = paletteOpen;
  const settingsOpenRef = useRef(false);
  settingsOpenRef.current = settingsOpen;
  const onboardingOpenRef = useRef(onboardingOpen);
  onboardingOpenRef.current = onboardingOpen;
  const commandOpenRef = useRef(commandOpen);
  commandOpenRef.current = commandOpen;
  const eventLogSeenKeysRef = useRef<Set<string>>(new Set());
  const eventLogPrimedRef = useRef(false);

  useEffect(() => {
    try {
      const v = localStorage.getItem(FRONTIER_MAP_STYLE_STORAGE_KEY);
      if (v === "satellite" || v === "political" || v === "terrain") setMapStyle(v);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    try {
      const r = localStorage.getItem(FRONTIER_MAP_RENDERER_STORAGE_KEY);
      if (r === "pixi" || r === "svg") setMapRenderer(r);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(FRONTIER_SIM_PAUSED_STORAGE_KEY, simPaused ? "1" : "0");
      localStorage.setItem(FRONTIER_SIM_SPEED_STORAGE_KEY, String(simSpeedIdx));
    } catch {
      /* ignore */
    }
  }, [simPaused, simSpeedIdx]);

  useEffect(() => {
    try {
      localStorage.setItem(FRONTIER_SCENARIO_STORAGE_KEY, devResetScenario);
    } catch {
      /* ignore */
    }
  }, [devResetScenario]);

  useEffect(() => {
    didInitPan.current = false;
    eventLogSeenKeysRef.current.clear();
    eventLogPrimedRef.current = false;
  }, [world?.seed]);

  useEffect(() => {
    const el = mapViewportRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      const z0 = mapZoomRef.current;
      const p = panRef.current;
      const factor = Math.exp(-e.deltaY * 0.0009);
      const z1 = Math.min(2.8, Math.max(0.38, z0 * factor));
      const wx = (cx - p.x) / z0;
      const wy = (cy - p.y) / z0;
      const nextPan = { x: cx - wx * z1, y: cy - wy * z1 };
      mapZoomRef.current = z1;
      panRef.current = nextPan;
      setMapZoom(z1);
      setPan(nextPan);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await fetch("/api/engine/world");
      if (!r.ok) throw new Error(await r.text());
      setWorld((await r.json()) as WorldDto);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!world?.event_log) return;
    if (!eventLogPrimedRef.current) {
      for (const ev of world.event_log) {
        eventLogSeenKeysRef.current.add(`${ev.tick}|${ev.kind}|${ev.message}`);
      }
      eventLogPrimedRef.current = true;
      return;
    }
    for (const ev of world.event_log) {
      const key = `${ev.tick}|${ev.kind}|${ev.message}`;
      if (eventLogSeenKeysRef.current.has(key)) continue;
      eventLogSeenKeysRef.current.add(key);
      if (eventLogSeenKeysRef.current.size > 500) {
        eventLogSeenKeysRef.current = new Set(Array.from(eventLogSeenKeysRef.current).slice(-250));
      }
      if (ev.party !== "player") continue;
      if (ev.kind === "production_done") {
        const rid = ev.recipe_id ?? "";
        const label = world.recipes?.find((r) => r.id === rid)?.display_name ?? rid;
        pushToast({ message: `Outputs ready: ${label}`, kind: "ok" });
      } else if (ev.kind === "production_stalled_storage") {
        pushToast({
          message: "Production stalled — pack full. Ship, sell, or use space before outputs land.",
          kind: "warn",
        });
      } else if (ev.kind === "ship_deliver") {
        const mat = ev.material ?? "";
        const q = ev.qty ?? 0;
        pushToast({ message: `Shipment arrived: ${q}×${displayMaterial(mat)}`, kind: "ok" });
      }
    }
  }, [world?.event_log, world?.recipes, pushToast]);

  useEffect(() => {
    try {
      if (typeof window !== "undefined" && !localStorage.getItem(FRONTIER_ONBOARD_STORAGE_KEY)) {
        setOnboardingOpen(true);
      }
    } catch {
      setOnboardingOpen(true);
    }
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod || e.key.toLowerCase() !== "k") return;
      const t = e.target as HTMLElement;
      if (t.closest("[data-realm-no-palette]")) return;
      const tag = t.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
        if (!t.closest(".realm-palette")) return;
      }
      if (t.isContentEditable) return;
      e.preventDefault();
      setPaletteOpen((o) => !o);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (paletteOpenRef.current || onboardingOpenRef.current) return;
      if (e.key !== "[" && e.key !== "]") return;
      const el = e.target as HTMLElement;
      if (el.closest("[data-realm-no-palette]")) return;
      const tag = el.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (el.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      e.preventDefault();
      const order = getFrontierTabCycleOrder();
      const cur = tabRef.current;
      const i = order.indexOf(cur);
      if (i < 0) return;
      const di = e.key === "[" ? -1 : 1;
      const ni = (i + di + order.length) % order.length;
      setTab(order[ni]);
      setCommandOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (settingsOpenRef.current) {
        e.preventDefault();
        setSettingsOpen(false);
        return;
      }
      if (paletteOpenRef.current || onboardingOpenRef.current) return;
      const el = e.target as HTMLElement;
      const tag = el.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (el.isContentEditable) return;
      if (!commandOpenRef.current) return;
      e.preventDefault();
      setCommandOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const el = mapViewportRef.current;
    if (!el) return;
    const apply = () => {
      const r = el.getBoundingClientRect();
      setViewportPx({ w: Math.max(80, r.width), h: Math.max(80, r.height) });
    };
    apply();
    const ro = new ResizeObserver(() => apply());
    ro.observe(el);
    return () => ro.disconnect();
  }, [world]);

  const grid = useMemo(() => {
    if (!world?.plots.length) return { w: 0, h: 0, cellPx: 36 };
    const w = Math.max(...world.plots.map((p) => p.x)) + 1;
    const h = Math.max(...world.plots.map((p) => p.y)) + 1;
    const pad = 4;
    const innerW = Math.max(60, viewportPx.w - pad * 2);
    const innerH = Math.max(60, viewportPx.h - pad * 2);
    const cw = innerW / Math.max(1, w);
    const ch = innerH / Math.max(1, h);
    const cellPx = Math.floor(Math.max(8, Math.min(56, Math.min(cw, ch))));
    return { w, h, cellPx };
  }, [world, viewportPx]);

  const mesh = useMemo(() => {
    if (!world || grid.w === 0) return null;
    return buildOrganicMesh(world.seed, grid.w, grid.h, MAP_PAD, grid.cellPx);
  }, [world, grid.w, grid.h, grid.cellPx]);

  const gridContentPx = useMemo(() => {
    if (!mesh) return { w: 0, h: 0 };
    return { w: mesh.contentWidth, h: mesh.contentHeight };
  }, [mesh]);

  useLayoutEffect(() => {
    const el = mapViewportRef.current;
    if (!world || grid.w === 0 || !el || didInitPan.current) return;
    const vw = el.clientWidth;
    const vh = el.clientHeight;
    const { w: cw, h: ch } = gridContentPx;
    if (cw < 1 || ch < 1) return;
    const next = { x: (vw - cw) / 2, y: (vh - ch) / 2 };
    panRef.current = next;
    mapZoomRef.current = 1;
    setPan(next);
    didInitPan.current = true;
  }, [world, grid.w, grid.h, grid.cellPx, gridContentPx]);

  const queueFx = useCallback(
    (ev: Omit<MapFxEvent, "id">) => {
      playFrontierSfx(ev.kind);
      void resumeFrontierAudio();
      const id = ++mapFxSeq.current;
      setMapFx((prev) => [...prev, { id, ...ev }]);
      window.setTimeout(() => {
        setMapFx((prev) => prev.filter((e) => e.id !== id));
      }, 1700);
      if (mesh && grid.w > 0) {
        const sid = ++sparkSeqRef.current;
        const c = mesh.plotCentroid(ev.gx, ev.gy);
        setSparks((prev) => [...prev, { id: sid, cx: c.x, cy: c.y, hue: FX_HUE[ev.kind] ?? 200 }]);
        window.setTimeout(() => setSparks((prev) => prev.filter((s) => s.id !== sid)), 480);
      }
    },
    [grid.w, mesh],
  );

  const buildsByPlot = useMemo(() => {
    const m = new Map<string, number>();
    for (const b of world?.plot_buildings ?? []) {
      m.set(b.plot_id, (m.get(b.plot_id) ?? 0) + 1);
    }
    return m;
  }, [world?.plot_buildings]);

  const playerOwnsLand = useMemo(
    () => (world?.plots ?? []).some((p) => p.owner === "player"),
    [world?.plots],
  );

  const starterPulsePlotIds = useMemo(() => {
    if (!world?.plots.length || playerOwnsLand) return new Set<string>();
    return computeStarterHintPlotIds(world.plots, 5);
  }, [world?.plots, playerOwnsLand]);

  const mapAnchor = useMemo((): { cx: number; cy: number; caption: string } | null => {
    if (!mesh || !world?.plots.length) return null;
    if (playerOwnsLand) {
      const mine = world.plots.filter((p) => p.owner === "player");
      mine.sort((a, b) => a.x + a.y - (b.x + b.y) || a.id.localeCompare(b.id));
      const p = mine[0];
      if (!p) return null;
      const c = mesh.plotCentroid(p.x, p.y);
      return { cx: c.x, cy: c.y, caption: "You are here" };
    }
    const origin = world.plots.find((q) => q.id === "p-0-0");
    if (!origin) return null;
    const c = mesh.plotCentroid(origin.x, origin.y);
    return { cx: c.x, cy: c.y, caption: "Start here" };
  }, [mesh, world?.plots, playerOwnsLand]);

  const mapAriaLabel = useMemo(() => {
    if (playerOwnsLand) return "Frontier map — click a plot to select it";
    return "Frontier map — Start here marks the landing corner; soft gold highlights suggest good first claims";
  }, [playerOwnsLand]);

  useEffect(() => {
    if (!SHOW_INTERNAL_ATLAS_AND_DEV_CONTRACTS && tab === "codex") setTab("world");
  }, [tab]);

  const playerPlotChoices = useMemo(
    () =>
      (world?.plots ?? [])
        .filter((p) => p.owner === "player")
        .sort((a, b) => a.id.localeCompare(b.id)),
    [world?.plots],
  );

  const schematicEligiblePlots = useMemo(() => {
    if (!world?.plots) return [];
    return world.plots
      .filter((p) => p.owner === "player" && p.surveyed)
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((p) => ({ id: p.id, shortLabel: `${p.id} · ${p.terrain}` }));
  }, [world?.plots]);

  const shipPreview = useMemo(() => {
    if (!world) return null;
    return {
      fee: previewShipFeeCents(shipFrom, shipTo),
      arrive: previewShipArriveTick(world.tick, shipFrom, shipTo),
      dist: manhattanPlotIds(shipFrom, shipTo),
    };
  }, [world, shipFrom, shipTo]);

  const selectedPlot = useMemo(
    () => world?.plots.find((p) => p.id === selectedPlotId) ?? null,
    [world, selectedPlotId],
  );

  const workshopRecipesForSelectedPlot = useMemo(() => {
    const all = (world?.recipes ?? []) as RecipeDto[];
    const ids = selectedPlot?.surveyed ? selectedPlot.recipe_ids : undefined;
    if (!ids?.length) return [];
    const allow = new Set(ids);
    return all.filter((r) => allow.has(r.id));
  }, [world?.recipes, selectedPlot]);

  const playerInv = world?.inventory["player"] ?? {};

  const buildingsHere = useMemo(() => {
    if (!selectedPlotId || !world?.plot_buildings) return [];
    return world.plot_buildings.filter((b) => b.plot_id === selectedPlotId);
  }, [world?.plot_buildings, selectedPlotId]);

  const eventLogReversed = useMemo(() => {
    const ev = world?.event_log ?? [];
    return [...ev].reverse();
  }, [world?.event_log]);

  const supplyContractRows = useMemo(() => {
    if (!world?.contracts) return [];
    return (world.contracts as unknown[]).filter(
      (c): c is SupplyContractDto => (c as SupplyContractDto).kind === "supply",
    );
  }, [world?.contracts]);

  const financialStubRows = useMemo(() => {
    if (!world?.contracts) return [];
    return (world.contracts as Record<string, unknown>[]).filter((c) =>
      ["loan", "equity_stub", "service_sub"].includes(String(c.kind)),
    );
  }, [world?.contracts]);

  const pactCounterpartyChoices = useMemo(() => {
    const ps = world?.parties ?? [];
    return ps.filter((p) => p !== "player").sort((a, b) => a.localeCompare(b));
  }, [world?.parties]);

  useEffect(() => {
    if (pactCounterpartyChoices.length === 0) return;
    if (!pactCounterpartyChoices.includes(supplyCounterparty)) {
      setSupplyCounterparty(pactCounterpartyChoices[0]);
    }
  }, [pactCounterpartyChoices, supplyCounterparty]);

  const bazaarSymbolList = useMemo(() => {
    const base = collectBazaarSymbolIds(world ?? undefined);
    const id = normalizeBazaarSymbolId(bazaarSymbol);
    if (!id) return base;
    if (!base.includes(id)) return [...base, id].sort((a, b) => a.localeCompare(b));
    return base;
  }, [world, bazaarSymbol]);

  const syncBazaarFieldFromDomValue = useCallback((raw: string) => {
    setBazaarSymbol(raw.toLowerCase());
    const n = normalizeBazaarSymbolId(raw);
    if (n) setBazaarActiveId(n);
  }, []);

  const playerCash =
    world?.balances_cents["cash:player"] != null
      ? (world.balances_cents["cash:player"] / 100).toFixed(2)
      : "—";

  const playerCashCents = world?.balances_cents["cash:player"];
  const canAffordSurvey =
    typeof playerCashCents === "number" && playerCashCents >= FRONTIER_SURVEY_COST_CENTS;

  const toggleSimPause = useCallback(() => {
    setSimPaused((p) => {
      const next = !p;
      pushToast({
        message: next ? "Simulation paused." : "Simulation running.",
        kind: "ok",
      });
      return next;
    });
  }, [pushToast]);

  const setSimSpeedPreset = useCallback(
    (next: 0 | 1 | 2) => {
      setSimSpeedIdx(next);
      pushToast({ message: `Sim speed: ${SIM_SPEED_LABELS[next]}`, kind: "info" });
    },
    [pushToast],
  );

  const cycleSimSpeed = useCallback(() => {
    setSimSpeedIdx((i) => {
      const next = ((i + 1) % 3) as 0 | 1 | 2;
      pushToast({ message: `Sim speed: ${SIM_SPEED_LABELS[next]}`, kind: "info" });
      return next;
    });
  }, [pushToast]);

  const advanceSimTick = useCallback(async () => {
    if (tickInFlightRef.current) return;
    tickInFlightRef.current = true;
    setError(null);
    try {
      const r = await fetch("/api/engine/tick", { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSimPaused(true);
    } finally {
      tickInFlightRef.current = false;
    }
  }, [load]);

  const simIntervalMs = SIM_SPEEDS_MS[simSpeedIdx];
  const msPerSimTick = simIntervalMs;

  useEffect(() => {
    if (!world || simPaused || onboardingOpen) return;
    const id = window.setInterval(() => {
      void advanceSimTick();
    }, simIntervalMs);
    return () => window.clearInterval(id);
  }, [world?.seed, simPaused, simIntervalMs, advanceSimTick, onboardingOpen]);

  async function claimPlot(p: PlotDto) {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`/api/engine/plots/${encodeURIComponent(p.id)}/claim`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      queueFx({ kind: "claim", gx: p.x, gy: p.y, label: "CLAIM" });
      await load();
      pushToast({ message: "Plot claimed.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function surveyPlot(p: PlotDto) {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`/api/engine/plots/${encodeURIComponent(p.id)}/survey`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      const body = (await r.json()) as { ok?: boolean; terrain?: string; recipe_ids?: string[] };
      queueFx({ kind: "survey", gx: p.x, gy: p.y, label: "SCAN" });
      await load();
      const n = Array.isArray(body.recipe_ids) ? body.recipe_ids.length : null;
      const terr = typeof body.terrain === "string" ? body.terrain : null;
      if (n != null && terr) {
        pushToast({
          message:
            n === 0
              ? `Survey complete on ${terr} — build a workshop here to unlock recipes.`
              : `Survey complete — ${n} recipes unlocked on ${terr}.`,
          kind: n === 0 ? "info" : "ok",
        });
      } else {
        pushToast({ message: "Survey complete.", kind: "ok" });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function produce(plotId: string, recipeId: string) {
    const plot = world?.plots.find((pp) => pp.id === plotId);
    const recipeLabel = world?.recipes?.find((x) => x.id === recipeId)?.display_name ?? recipeId;
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ recipe_id: recipeId });
      const r = await fetch(`/api/engine/plots/${encodeURIComponent(plotId)}/produce?${q.toString()}`, {
        method: "POST",
      });
      if (!r.ok) throw new Error(await r.text());
      if (plot) queueFx({ kind: "produce", gx: plot.x, gy: plot.y, label: "MAKE" });
      await load();
      pushToast({ message: `Production started: ${recipeLabel}`, kind: "ok" });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      pushToast({ message: msg.length > 140 ? `${msg.slice(0, 137)}…` : msg, kind: "warn" });
    } finally {
      setBusy(false);
    }
  }

  async function persistenceSave() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/engine/persistence/save", { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await load();
      pushToast({ message: "Game saved.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function persistenceLoad() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/engine/persistence/load", { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      didInitPan.current = false;
      await load();
      pushToast({ message: "Game loaded.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function devResetWorld() {
    if (
      typeof window !== "undefined" &&
      !window.confirm(
        `Reset the in-memory world to a fresh bootstrap (seed 42, scenario “${devResetScenario}”)? Unsaved progress is lost unless you saved to SQLite first.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ seed: "42", scenario: devResetScenario });
      const r = await fetch(`/api/engine/dev/reset?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      didInitPan.current = false;
      await load();
      pushToast({ message: `World reset (${devResetScenario}).`, kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function shipGoods() {
    const qty = Number(shipQty);
    if (!Number.isFinite(qty) || qty <= 0) {
      setError("Ship quantity must be a positive number.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        party: "player",
        material: shipMaterial,
        qty: String(qty),
        from_plot: shipFrom,
        to_plot: shipTo,
      });
      const r = await fetch(`/api/engine/ship?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      const dest = world?.plots.find((pp) => pp.id === shipTo);
      if (dest) queueFx({ kind: "ship", gx: dest.x, gy: dest.y, label: "SHIP" });
      await load();
      pushToast({ message: "Shipment queued.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function placeSellOrder() {
    const qty = Number(sellQty);
    const priceCents = parseDollarsToCents(sellPriceDollars);
    if (!Number.isFinite(qty) || qty <= 0 || priceCents == null || priceCents <= 0) {
      setError("Sell quantity must be positive; price must be a positive dollar amount per unit (e.g. 5.00).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        party: "player",
        material: bazaarActiveId,
        qty: String(qty),
        price_per_unit_cents: String(priceCents),
      });
      if (bazaarAdvancedOpen) {
        const ice = advAskIceberg.trim();
        if (ice !== "") {
          const n = Number(ice);
          if (Number.isFinite(n) && n >= 1 && n < qty) q.set("iceberg_display_qty", String(Math.floor(n)));
        }
        const hon = Number(advAskHonored);
        if (Number.isFinite(hon) && hon > 0) q.set("min_counterparty_honored", String(Math.floor(hon)));
      }
      const r = await fetch(`/api/engine/market/sell?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "trade",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((2 * (grid.h - 1)) / 3)),
          label: "SELL",
        });
      }
      await load();
      pushToast({ message: "Sell order posted.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function cancelAsk(orderId: string) {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ party: "player", order_id: orderId });
      const r = await fetch(`/api/engine/market/cancel?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "trade",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 4)),
          label: "CANCEL",
        });
      }
      await load();
      pushToast({ message: "Sell order cancelled.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function placeBuyOrder() {
    const qty = Number(bidQty);
    const maxCents = parseDollarsToCents(bidMaxDollars);
    if (!Number.isFinite(qty) || qty <= 0 || maxCents == null || maxCents <= 0) {
      setError("Bid quantity must be positive; max price must be a positive dollar amount per unit.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        party: "player",
        material: bazaarActiveId,
        qty: String(qty),
        max_price_per_unit_cents: String(maxCents),
      });
      if (bazaarAdvancedOpen) {
        const ice = advBidIceberg.trim();
        if (ice !== "") {
          const n = Number(ice);
          if (Number.isFinite(n) && n >= 1 && n < qty) q.set("iceberg_display_qty", String(Math.floor(n)));
        }
        const hon = Number(advBidHonored);
        if (Number.isFinite(hon) && hon > 0) q.set("min_counterparty_honored", String(Math.floor(hon)));
      }
      const r = await fetch(`/api/engine/market/bid?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "trade",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 3)),
          label: "BID",
        });
      }
      await load();
      pushToast({ message: "Bid posted.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function cancelBid(orderId: string) {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ party: "player", order_id: orderId });
      const r = await fetch(`/api/engine/market/cancel_bid?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "trade",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 5)),
          label: "CANCEL",
        });
      }
      await load();
      pushToast({ message: "Bid cancelled.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function sellIntoBids() {
    const maxQty = Number(sellFillQty);
    if (!Number.isFinite(maxQty) || maxQty <= 0) {
      setError("Sell-into-bids quantity must be a positive number.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        party: "player",
        material: bazaarActiveId,
        max_qty: String(maxQty),
      });
      const r = await fetch(`/api/engine/market/sell_fill?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "trade",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((2 * (grid.h - 1)) / 3)),
          label: "FILL",
        });
      }
      await load();
      pushToast({ message: "Market sell-fill executed.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runP2pTrade() {
    const qty = Number(p2pQty);
    const total = parseDollarsToCents(p2pTotalDollars);
    if (!Number.isFinite(qty) || qty <= 0 || total == null || total < 0) {
      setError("P2P quantity must be positive; total price must be zero or more in dollars.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const seller = p2pRole === "sell" ? "player" : p2pParty.trim();
      const buyer = p2pRole === "sell" ? p2pParty.trim() : "player";
      const idempotencyKey =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `p2p-${Date.now()}`;
      const q = new URLSearchParams({
        seller,
        buyer,
        material: p2pMaterial.trim(),
        qty: String(qty),
        total_price_cents: String(total),
        idempotency_key: idempotencyKey,
      });
      const r = await fetch(`/api/engine/trade/p2p?${q.toString()}`, { method: "POST" });
      if (!r.ok) {
        const raw = await r.text();
        let msg = raw;
        try {
          const j = JSON.parse(raw) as { detail?: unknown };
          const d = j.detail;
          if (d && typeof d === "object" && d !== null && "reason" in d) {
            msg = String((d as { reason: string }).reason);
          } else if (typeof d === "string") {
            msg = d;
          }
        } catch {
          /* keep raw */
        }
        throw new Error(msg);
      }
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "trade",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 3)),
          label: "P2P",
        });
      }
      await load();
      pushToast({ message: "P2P trade completed.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function proposeMemoContract() {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ party_a: "player", party_b: "npc_grain_vendor", kind: "memo" });
      const r = await fetch(`/api/engine/contracts/propose?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      const body = (await r.json()) as { contract_id?: string };
      if (body.contract_id) setLastContractId(body.contract_id);
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "contract",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 2)),
          label: "PACT",
        });
      }
      await load();
      pushToast({ message: "Memo contract proposed.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function proposeSupplyContract() {
    const qty = Number(supplyQty);
    const total = parseDollarsToCents(supplyTotalDollars);
    const due = Number(supplyDueTicks);
    if (!Number.isFinite(qty) || qty <= 0 || total == null || total < 0 || !Number.isFinite(due) || due < 1) {
      setError("Supply: quantity and deadline (ticks from now) must be positive; total price must be zero or more in dollars.");
      return;
    }
    const counter = supplyCounterparty.trim();
    if (!counter) {
      setError("Supply: pick a counterparty.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const supplier = supplyYouAre === "supplier" ? "player" : counter;
      const buyer = supplyYouAre === "supplier" ? counter : "player";
      const q = new URLSearchParams({
        supplier,
        buyer,
        material: supplyMaterial.trim(),
        qty: String(qty),
        total_price_cents: String(total),
        due_in_ticks: String(due),
      });
      const r = await fetch(`/api/engine/contracts/supply/propose?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "contract",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 2)),
          label: "PACT",
        });
      }
      await load();
      pushToast({ message: "Supply contract proposed.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function acceptSupplyContractRow(contractId: string) {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ buyer: "player", contract_id: contractId });
      const r = await fetch(`/api/engine/contracts/supply/accept?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await load();
      pushToast({ message: "Supply contract accepted.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function fulfillSupplyContractRow(contractId: string) {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ supplier: "player", contract_id: contractId });
      const r = await fetch(`/api/engine/contracts/supply/fulfill?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "contract",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 2)),
          label: "OK",
        });
      }
      await load();
      pushToast({ message: "Supply contract fulfilled.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function proposeLoanStub() {
    const principal = parseDollarsToCents(stubLoanPrincipalDollars);
    const repay = parseDollarsToCents(stubLoanRepayDollars);
    const due = Number(stubLoanDueTicks);
    if (principal == null || principal <= 0 || repay == null || repay <= 0 || !Number.isFinite(due) || due < 1) {
      setError("Loan: enter positive dollar amounts and a deadline of at least 1 tick.");
      return;
    }
    if (repay < principal) {
      setError("Loan: repay total must be at least the principal.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        lender: "player",
        borrower: stubLoanBorrower.trim(),
        principal_cents: String(principal),
        repay_cents: String(repay),
        due_in_ticks: String(Math.floor(due)),
      });
      const r = await fetch(`/api/engine/contracts/loan/propose?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      const body = (await r.json()) as { contract_id?: string };
      if (body.contract_id) setStubPhase2ContractId(body.contract_id);
      await load();
      pushToast({ message: "Loan proposed.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function acceptLoanStubAsBorrower() {
    const cid = stubPhase2ContractId.trim();
    if (!cid) {
      setError("Set contract id (from your last propose) before accepting.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ borrower: stubLoanBorrower.trim(), contract_id: cid });
      const r = await fetch(`/api/engine/contracts/loan/accept?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await load();
      pushToast({ message: "Loan accepted (principal moved).", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function repayLoanStub() {
    const cid = stubPhase2ContractId.trim();
    if (!cid) {
      setError("Set contract id before repaying.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ borrower: stubLoanBorrower.trim(), contract_id: cid });
      const r = await fetch(`/api/engine/contracts/loan/repay?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await load();
      pushToast({ message: "Loan repaid.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function proposeEquityStubPanel() {
    const inv = parseDollarsToCents(stubEquityInvestmentDollars);
    const div = Number(stubEquityDivCents);
    const ticks = Number(stubEquityDivTicks);
    if (inv == null || inv <= 0 || !Number.isFinite(div) || div <= 0 || !Number.isFinite(ticks) || ticks < 1) {
      setError("Equity stub: positive investment (dollars), positive dividend (cents per tick), and tick count.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        issuer: stubEquityIssuer.trim(),
        investor: stubEquityInvestor.trim(),
        investment_cents: String(inv),
        dividend_per_tick_cents: String(Math.floor(div)),
        dividend_ticks: String(Math.floor(ticks)),
      });
      const r = await fetch(`/api/engine/contracts/equity/propose?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      const body = (await r.json()) as { contract_id?: string };
      if (body.contract_id) setStubPhase2ContractId(body.contract_id);
      await load();
      pushToast({ message: "Equity stub proposed.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function acceptEquityStubPanel() {
    const cid = stubPhase2ContractId.trim();
    if (!cid) {
      setError("Set contract id before accepting equity stub.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ investor: stubEquityInvestor.trim(), contract_id: cid });
      const r = await fetch(`/api/engine/contracts/equity/accept?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await load();
      pushToast({ message: "Equity funding recorded.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function proposeServiceStubPanel() {
    const fee = parseDollarsToCents(stubServiceFeeDollars);
    const dur = Number(stubServiceDurationTicks);
    if (fee == null || fee <= 0 || !Number.isFinite(dur) || dur < 1) {
      setError("Service stub: positive fee and duration ticks.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        provider: stubServiceProvider.trim(),
        subscriber: stubServiceSubscriber.trim(),
        fee_cents: String(fee),
        duration_ticks: String(Math.floor(dur)),
      });
      const r = await fetch(`/api/engine/contracts/service/propose?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      const body = (await r.json()) as { contract_id?: string };
      if (body.contract_id) setStubPhase2ContractId(body.contract_id);
      await load();
      pushToast({ message: "Service contract proposed.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function acceptServiceStubPanel() {
    const cid = stubPhase2ContractId.trim();
    if (!cid) {
      setError("Set contract id before accepting service stub.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ subscriber: stubServiceSubscriber.trim(), contract_id: cid });
      const r = await fetch(`/api/engine/contracts/service/accept?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await load();
      pushToast({ message: "Service subscription started (prepaid).", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function honorContract() {
    if (!lastContractId) {
      setError("Propose a memo contract first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`/api/engine/contracts/${encodeURIComponent(lastContractId)}/honor`, {
        method: "POST",
      });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "contract",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 2)),
          label: "OK",
        });
      }
      await load();
      pushToast({ message: "Contract honored.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function maintainBuildingOnPlot(plotId: string, instanceId: string) {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ instance_id: instanceId, party: "player" });
      const r = await fetch(`/api/engine/plots/${encodeURIComponent(plotId)}/maintain?${q.toString()}`, {
        method: "POST",
      });
      if (!r.ok) throw new Error(await r.text());
      await load();
      pushToast({ message: "Maintenance applied.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function buyMarketIntel() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`/api/engine/market/intel?party=player`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await load();
      pushToast({ message: "Market intel purchased.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function buildOnSelectedPlot(buildingId: string, buildMode?: "turnkey" | "self_contract") {
    if (!selectedPlotId) {
      setError("Select a surveyed plot you own.");
      return;
    }
    const plot = world?.plots.find((pp) => pp.id === selectedPlotId);
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ building_id: buildingId, party: "player" });
      if (buildMode) q.set("build_mode", buildMode);
      const r = await fetch(
        `/api/engine/plots/${encodeURIComponent(selectedPlotId)}/build?${q.toString()}`,
        { method: "POST" },
      );
      if (!r.ok) throw new Error(await r.text());
      if (plot) queueFx({ kind: "build", gx: plot.x, gy: plot.y, label: "RISE" });
      await load();
      pushToast({ message: "Build started.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function hireNpc(employee: string, signingBonusCents: number) {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        employer: "player",
        employee,
        signing_bonus_cents: String(signingBonusCents),
      });
      const r = await fetch(`/api/engine/hire?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "hire",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 2)),
          label: "HIRE",
        });
      }
      await load();
      pushToast({ message: "Hire recorded.", kind: "ok" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function onPlotClick(p: PlotDto) {
    setSelectedPlotId(p.id);
    setTab("world");
  }

  function resetMapView() {
    const el = mapViewportRef.current;
    if (!el || grid.w === 0) return;
    const vw = el.clientWidth;
    const vh = el.clientHeight;
    const { w: nw, h: nh } = gridContentPx;
    const next = { x: (vw - nw) / 2, y: (vh - nh) / 2 };
    mapZoomRef.current = 1;
    panRef.current = next;
    setMapZoom(1);
    setPan(next);
  }

  function cycleMapStyle() {
    setMapStyle((s) => {
      const next = s === "terrain" ? "satellite" : s === "satellite" ? "political" : "terrain";
      try {
        localStorage.setItem(FRONTIER_MAP_STYLE_STORAGE_KEY, next);
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  function onMapPointerDownCapture(e: React.PointerEvent) {
    if (e.button !== 0) return;
    mapPanPointerId.current = e.pointerId;
    mapPanCaptureActiveRef.current = false;
    didPan.current = false;
    panDragRef.current = { sx: e.clientX, sy: e.clientY, px: panRef.current.x, py: panRef.current.y };
  }

  function onMapPointerMove(e: React.PointerEvent) {
    const d = panDragRef.current;
    if (!d) return;
    const dx = e.clientX - d.sx;
    const dy = e.clientY - d.sy;
    if (dx * dx + dy * dy > 36) didPan.current = true;
    if (dx * dx + dy * dy > 9) {
      const el = mapViewportRef.current;
      if (el && !mapPanCaptureActiveRef.current) {
        try {
          el.setPointerCapture(e.pointerId);
          mapPanCaptureActiveRef.current = true;
        } catch {
          /* already captured elsewhere */
        }
      }
      const next = { x: d.px + dx, y: d.py + dy };
      panRef.current = next;
      setPan(next);
    }
  }

  function releaseMapPointerCapture() {
    const pid = mapPanPointerId.current;
    const el = mapViewportRef.current;
    if (pid != null && el && mapPanCaptureActiveRef.current) {
      try {
        el.releasePointerCapture(pid);
      } catch {
        /* not capturing */
      }
    }
    mapPanPointerId.current = null;
    mapPanCaptureActiveRef.current = false;
  }

  function onMapPointerUp() {
    releaseMapPointerCapture();
    if (didPan.current) mapNavSuppress.current = true;
    panDragRef.current = null;
  }

  function replayBriefing() {
    try {
      localStorage.removeItem(FRONTIER_ONBOARD_STORAGE_KEY);
      localStorage.removeItem(FRONTIER_MAP_STYLE_STORAGE_KEY);
      localStorage.removeItem("realm_frontier_map_style");
      localStorage.removeItem("realm_frontier_onboard_v3");
      localStorage.removeItem("realm_frontier_onboard_v4");
      localStorage.removeItem("realm_frontier_onboard_v5");
      localStorage.removeItem("realm_frontier_onboard_v6");
      localStorage.removeItem("realm_frontier_onboard_v7");
      localStorage.removeItem("realm_frontier_onboard_v8");
      localStorage.removeItem(FRONTIER_SIM_PAUSED_STORAGE_KEY);
      localStorage.removeItem(FRONTIER_SIM_SPEED_STORAGE_KEY);
    } catch {
      /* ignore */
    }
    setSimPaused(false);
    setSimSpeedIdx(1);
    setOnboardingOpen(true);
  }

  return (
    <main className="realm-shell realm-app">
      <OnboardingModal open={onboardingOpen} onComplete={() => setOnboardingOpen(false)} />

      {error ? (
        <div className="realm-error" role="alert">
          {error}
        </div>
      ) : null}

      {world ? (
        <>
          <header className="realm-top-strip">
            <div className="realm-top-strip__hud">
              <div className="realm-brand">
                <div className="realm-brand__title">Realm</div>
                <div className="realm-brand__sub">Frontier · player-run economy (solo slice)</div>
              </div>
              <div className="realm-stat-row">
                <motion.span
                  key={world.tick}
                  className="realm-pill"
                  initial={{ scale: 1.04, opacity: 0.7 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 500, damping: 28 }}
                >
                  World tick <strong>{world.tick}</strong>
                </motion.span>
                <span className="realm-pill">
                  Seed <strong>{world.seed}</strong>
                </span>
                {world.scenario_id ? (
                  <span className="realm-pill">
                    Scenario <strong>{world.scenario_id}</strong>
                  </span>
                ) : null}
                <span className="realm-pill">
                  Cash <strong>${playerCash}</strong>
                </span>
                <motion.button
                  type="button"
                  className={`realm-btn realm-btn--sm ${simPaused ? "realm-btn--ghost" : "realm-btn--primary"}`}
                  aria-pressed={!simPaused}
                  aria-label={simPaused ? "Run simulation" : "Pause simulation"}
                  disabled={busy}
                  onClick={toggleSimPause}
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                >
                  {simPaused ? "Run" : "Pause"}
                </motion.button>
                <button
                  type="button"
                  className="realm-btn realm-btn--ghost realm-btn--sm"
                  title="Real-time gap between engine ticks while running"
                  onClick={cycleSimSpeed}
                >
                  {SIM_SPEED_LABELS[simSpeedIdx]}
                </button>
                <button
                  type="button"
                  className="realm-btn realm-btn--ghost realm-btn--sm"
                  title="Open settings (sim speed, pause, dev reset)"
                  onClick={() => setSettingsOpen(true)}
                >
                  Settings
                </button>
                <button
                  type="button"
                  className="realm-btn realm-btn--ghost realm-btn--sm"
                  title="Collapse side panel (Esc when not typing)"
                  onClick={() => setCommandOpen((o) => !o)}
                >
                  {commandOpen ? "Hide panel" : "Show panel"}
                </button>
                <button type="button" className="realm-btn realm-btn--ghost realm-btn--sm" onClick={replayBriefing}>
                  Briefing
                </button>
                <button
                  type="button"
                  className="realm-btn realm-btn--ghost realm-btn--sm"
                  title="Open command palette (Ctrl or Cmd + K). Use [ and ] to cycle command tabs when not typing in a field."
                  onClick={() => setPaletteOpen(true)}
                >
                  Go to…
                </button>
              </div>
            </div>
            <FrontierTopNav
              active={tab}
              onSelect={(t) => {
                setTab(t);
                setCommandOpen(true);
              }}
            />
          </header>

          <div className="realm-world-main">
            <div className="realm-world-stage">
              <div className="realm-atmosphere" aria-hidden>
                <div className="realm-atmosphere__sky" />
                <div className="realm-atmosphere__aurora" />
                <div className="realm-atmosphere__stars" />
              </div>
              <div
                ref={mapViewportRef}
                className="realm-map-viewport"
                onPointerDownCapture={onMapPointerDownCapture}
                onPointerMove={onMapPointerMove}
                onPointerUp={onMapPointerUp}
                onPointerCancel={onMapPointerUp}
              >
                <div className="realm-map-toolbar" role="toolbar" aria-label="Zoom and map appearance">
                  <span className="realm-map-toolbar__label">{mapStyle}</span>
                  <button
                    type="button"
                    className="realm-map-toolbar__btn"
                    onClick={() => {
                      setMapZoom((z) => {
                        const z1 = Math.min(2.8, z * 1.12);
                        mapZoomRef.current = z1;
                        return z1;
                      });
                    }}
                  >
                    +
                  </button>
                  <button
                    type="button"
                    className="realm-map-toolbar__btn"
                    onClick={() => {
                      setMapZoom((z) => {
                        const z1 = Math.max(0.38, z / 1.12);
                        mapZoomRef.current = z1;
                        return z1;
                      });
                    }}
                  >
                    −
                  </button>
                  <button type="button" className="realm-map-toolbar__btn" onClick={resetMapView}>
                    Reset
                  </button>
                  <button type="button" className="realm-map-toolbar__btn" onClick={cycleMapStyle}>
                    Style
                  </button>
                  <button
                    type="button"
                    className="realm-map-toolbar__btn"
                    title="Switch map renderer: SVG (vector) or Pixi (WebGL canvas)"
                    onClick={() => {
                      setMapRenderer((m) => {
                        const next = m === "svg" ? "pixi" : "svg";
                        try {
                          localStorage.setItem(FRONTIER_MAP_RENDERER_STORAGE_KEY, next);
                        } catch {
                          /* ignore */
                        }
                        return next;
                      });
                    }}
                  >
                    {mapRenderer === "pixi" ? "GL" : "SVG"}
                  </button>
                </div>
                <div
                  className="realm-map-world-surface"
                  data-map-style={mapStyle}
                  style={{
                    transform: `translate(${pan.x}px, ${pan.y}px) scale(${mapZoom})`,
                  }}
                >
                  <div className="realm-map-grid-stack">
                    {mesh ? (
                      <>
                        <RealmMapFxOverlay
                          events={mapFx}
                          width={gridContentPx.w}
                          height={gridContentPx.h}
                          getBurstCenter={(gx, gy) => mesh.plotCentroid(gx, gy)}
                          burstScale={grid.cellPx}
                        />
                        <RealmMapParticlesCanvas width={gridContentPx.w} height={gridContentPx.h} sparks={sparks} />
                        {mapRenderer === "svg" ? (
                          <RealmMapMeshSvg
                            mesh={mesh}
                            plots={world.plots}
                            selectedPlotId={selectedPlotId}
                            buildsByPlot={buildsByPlot}
                            busy={busy}
                            mapNavSuppress={mapNavSuppress}
                            onPlotClick={onPlotClick}
                            starterPulsePlotIds={starterPulsePlotIds}
                            mapAnchor={mapAnchor}
                            ariaLabel={mapAriaLabel}
                          />
                        ) : (
                          <RealmMapMeshPixi
                            mesh={mesh}
                            plots={world.plots}
                            selectedPlotId={selectedPlotId}
                            buildsByPlot={buildsByPlot}
                            busy={busy}
                            mapNavSuppress={mapNavSuppress}
                            onPlotClick={onPlotClick}
                            starterPulsePlotIds={starterPulsePlotIds}
                            mapAnchor={mapAnchor}
                            ariaLabel={mapAriaLabel}
                            mapStyle={mapStyle}
                          />
                        )}
                      </>
                    ) : null}
                  </div>
                </div>
              </div>
              <p className="realm-map-footnote">
                Drag to pan · scroll wheel zoom · click a plot to select it (gold ring). Toggle <strong>SVG</strong> / <strong>GL</strong> in the map toolbar for
                vector vs Pixi canvas. Claim and survey from the side panel. Pause the clock in the header when you want the world to hold still.
              </p>
            </div>

            <AnimatePresence>
              {commandOpen ? (
                <motion.aside
                  key="cmd"
                  className="realm-panel-pop"
                  role="complementary"
                  aria-label="Side panel"
                  initial={{ opacity: 0, x: 48 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 40 }}
                  transition={{ type: "spring", stiffness: 420, damping: 32 }}
                >
                  <div className="realm-panel-pop__head">
                    <span className="realm-panel-pop__title" aria-live="polite">
                      {panelHeadline(tab)}
                    </span>
                    <button type="button" className="realm-panel-pop__close" onClick={() => setCommandOpen(false)} aria-label="Close side panel">
                      ✕
                    </button>
                  </div>

              <AnimatePresence mode="wait">
                <motion.div
                  key={tab}
                  role="tabpanel"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.2 }}
                  className="realm-panel-scroll"
                >
                  {tab === "world" ? (
                    <>
                      <SectionTitle>Selected plot</SectionTitle>
                      {selectedPlot ? (
                        <>
                          <div className="realm-help" style={{ marginBottom: 12 }}>
                            <strong style={{ color: "var(--realm-text)" }}>{selectedPlot.id}</strong>
                            <span style={{ display: "block", marginTop: 6 }}>
                              Terrain <strong>{selectedPlot.terrain}</strong> · grid ({selectedPlot.x}, {selectedPlot.y})
                            </span>
                            <span style={{ display: "block", marginTop: 4 }}>
                              Owner:{" "}
                              {selectedPlot.owner == null ? (
                                <strong>unclaimed</strong>
                              ) : selectedPlot.owner === "player" ? (
                                <strong>you</strong>
                              ) : (
                                <strong>{displayParty(selectedPlot.owner)}</strong>
                              )}
                            </span>
                            <span style={{ display: "block", marginTop: 4 }}>
                              Survey status:{" "}
                              <strong>{selectedPlot.surveyed ? "complete — industry unlocked" : "not surveyed"}</strong>
                            </span>
                            {!selectedPlot.surveyed && selectedPlot.owner === "player" ? (
                              <span style={{ display: "block", marginTop: 6, fontSize: 11, lineHeight: 1.45 }}>
                                Surveying costs <strong>${(FRONTIER_SURVEY_COST_CENTS / 100).toFixed(2)}</strong> cash and reveals
                                subsurface grades (ore / clay / coal hints).
                              </span>
                            ) : null}
                            {selectedPlot.owner === "player" && selectedPlot.surveyed && selectedPlot.subsurface ? (
                              <span style={{ display: "block", marginTop: 6, fontSize: 11, lineHeight: 1.45 }}>
                                Subsurface grades:{" "}
                                {Object.entries(selectedPlot.subsurface)
                                  .map(([k, v]) => `${displayMaterial(k.replace(/_grade$/, ""))} ${(v as number).toFixed(2)}`)
                                  .join(" · ")}
                              </span>
                            ) : null}
                            {selectedPlot.owner === "player" && selectedPlot.surveyed && !selectedPlot.subsurface ? (
                              <span style={{ display: "block", marginTop: 6, fontSize: 11 }}>
                                No subsurface readout (survey data missing in snapshot).
                              </span>
                            ) : null}
                            {buildingsHere.length > 0 ? (
                              <span style={{ display: "block", marginTop: 6, fontSize: 11 }}>
                                Structures on this plot: {buildingsHere.length}
                                <span style={{ display: "block", opacity: 0.9, marginTop: 2 }}>
                                  {buildingsHere.map((x) => x.label).join(" · ")}
                                </span>
                              </span>
                            ) : null}
                          </div>

                          {!selectedPlot.owner ? (
                            <div style={{ marginBottom: 14 }}>
                              <p className="realm-help" style={{ marginTop: 0 }}>
                                Claiming assigns the plot to you (no cash cost in this build). Survey afterward to produce here.
                              </p>
                              <button
                                type="button"
                                className="realm-btn realm-btn--primary"
                                disabled={busy}
                                onClick={() => void claimPlot(selectedPlot)}
                              >
                                Claim this plot
                              </button>
                            </div>
                          ) : null}

                          {selectedPlot.owner === "player" && !selectedPlot.surveyed ? (
                            <div style={{ marginBottom: 14 }}>
                              <button
                                type="button"
                                className="realm-btn realm-btn--primary"
                                disabled={busy || !canAffordSurvey}
                                onClick={() => void surveyPlot(selectedPlot)}
                              >
                                Survey for ${(FRONTIER_SURVEY_COST_CENTS / 100).toFixed(2)}
                              </button>
                              {!canAffordSurvey && typeof playerCashCents === "number" ? (
                                <p className="realm-help" style={{ marginTop: 8, marginBottom: 0 }}>
                                  Short by ${Math.max(0, (FRONTIER_SURVEY_COST_CENTS - playerCashCents) / 100).toFixed(2)} (
                                  cash ${playerCash}).
                                </p>
                              ) : null}
                            </div>
                          ) : null}

                          {selectedPlot.owner != null && selectedPlot.owner !== "player" ? (
                            <p className="realm-help" style={{ marginBottom: 14 }}>
                              Not your holding — browse terrain and structures only.
                            </p>
                          ) : null}

                          {selectedPlot.owner === "player" && selectedPlot.surveyed ? (
                            <>
                              <SectionTitle>Recipes on this plot</SectionTitle>
                              <p className="realm-help" style={{ marginTop: 0, marginBottom: 8 }}>
                                Only recipes that match this tile&apos;s <strong>terrain</strong> can run here after survey — mountains host smelting, forests
                                favor timber work, and <strong>water</strong> cannot host workshops in this build.
                              </p>
                              {workshopRecipesForSelectedPlot.length === 0 ? (
                                <p className="realm-help" style={{ marginBottom: 8 }}>
                                  After survey, recipes appear only when the matching <strong>workshop</strong> is built on this plot (see Build below). On
                                  water, workshops are not available.
                                </p>
                              ) : (
                                <ul style={{ listStyle: "none", padding: 0, margin: "0 0 8px" }}>
                                  {workshopRecipesForSelectedPlot.map((r) => (
                                    <li key={r.id} style={{ marginBottom: 6 }}>
                                      <button
                                        type="button"
                                        className="realm-list-btn"
                                        disabled={busy}
                                        onClick={() => void produce(selectedPlot.id, r.id)}
                                      >
                                        {r.display_name} · {r.duration_ticks} ticks · labor ${(r.labor_cents / 100).toFixed(2)}
                                      </button>
                                    </li>
                                  ))}
                                </ul>
                              )}
                              <SectionTitle>Build on this plot</SectionTitle>
                              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                                {(world.building_catalog ?? []).map((b) => {
                                  const kind = b.kind ?? "simple";
                                  if (kind === "contracted") {
                                    const tt = b.turnkey_total_cents ?? 0;
                                    const selfCash = (b.self_shell_cents ?? 0) + (b.self_contractor_fee_cents ?? 0);
                                    const matParts = Object.entries(b.self_materials ?? {}).map(([k, v]) => `${v}×${k}`);
                                    const matHint = matParts.length ? matParts.join(", ") : "mats";
                                    return (
                                      <li key={b.id} style={{ marginBottom: 10 }}>
                                        <div style={{ marginBottom: 4, opacity: 0.9 }}>{b.label}</div>
                                        <button
                                          type="button"
                                          className="realm-list-btn"
                                          disabled={busy}
                                          onClick={() => void buildOnSelectedPlot(b.id, "turnkey")}
                                        >
                                          Turnkey · ${(tt / 100).toFixed(2)} <span style={{ opacity: 0.75 }}>(vendor supplies)</span>
                                        </button>
                                        <button
                                          type="button"
                                          className="realm-list-btn"
                                          style={{ marginTop: 6 }}
                                          disabled={busy}
                                          onClick={() => void buildOnSelectedPlot(b.id, "self_contract")}
                                        >
                                          Self + contractor · ${(selfCash / 100).toFixed(2)} + {matHint}
                                        </button>
                                      </li>
                                    );
                                  }
                                  const c = b.cost_cents ?? 0;
                                  return (
                                    <li key={b.id} style={{ marginBottom: 6 }}>
                                      <button
                                        type="button"
                                        className="realm-list-btn"
                                        disabled={busy}
                                        onClick={() => void buildOnSelectedPlot(b.id)}
                                      >
                                        {b.label} · ${(c / 100).toFixed(2)}
                                      </button>
                                    </li>
                                  );
                                })}
                              </ul>
                              {buildingsHere.length > 0 ? (
                                <>
                                  <SectionTitle>Built here</SectionTitle>
                                  <ul className="realm-help" style={{ marginTop: 4, paddingLeft: 18 }}>
                                    {buildingsHere.map((x, i) => (
                                      <li key={x.instance_id ?? `${x.building_id}-${i}`} style={{ marginBottom: 8 }}>
                                        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                                          <span>
                                            {x.label}
                                            {typeof x.condition_bps === "number" ? (
                                              <span style={{ opacity: 0.85 }}>
                                                {" "}
                                                · condition {(x.condition_bps / 100).toFixed(0)}%
                                              </span>
                                            ) : null}
                                          </span>
                                          {x.instance_id && selectedPlotId ? (
                                            <button
                                              type="button"
                                              className="realm-btn realm-btn--ghost realm-btn--sm"
                                              disabled={busy}
                                              onClick={() => void maintainBuildingOnPlot(selectedPlotId, x.instance_id!)}
                                            >
                                              Maintain
                                            </button>
                                          ) : null}
                                        </div>
                                      </li>
                                    ))}
                                  </ul>
                                </>
                              ) : null}
                            </>
                          ) : null}
                        </>
                      ) : (
                        <p className="realm-help">
                          Click a plot on the map (gold ring). Until you own land, a <strong>Start here</strong> pin and soft gold glow mark easy first claims
                          near the corner — then use this panel to claim and survey.
                        </p>
                      )}

                      <SectionTitle>Active production</SectionTitle>
                      {(world.active_production ?? []).length === 0 ? (
                        <p className="realm-help">
                          Nothing is running. <strong>Select a surveyed plot you own</strong>, then pick a recipe above to start a batch.
                        </p>
                      ) : (
                        <ul className="realm-help" style={{ paddingLeft: 18, margin: 0 }}>
                          {(world.active_production ?? []).map((a) => {
                            const rn = world.recipes?.find((r) => r.id === a.recipe_id)?.display_name ?? a.recipe_id;
                            return (
                              <li key={a.run_id}>
                                {a.plot_id} · {rn} · {formatRelativeTicksFromNow(a.ticks_remaining, msPerSimTick)} left
                              </li>
                            );
                          })}
                        </ul>
                      )}

                      <SectionTitle>Inventory (player)</SectionTitle>
                      <p className="realm-help" style={{ marginTop: 0, marginBottom: 8 }}>
                        ≈ prices use the latest market book snapshot (mid of bid and ask when both exist).
                      </p>
                      <table className="realm-table">
                        <thead>
                          <tr>
                            <th>Material</th>
                            <th style={{ textAlign: "right" }}>Qty</th>
                            <th style={{ textAlign: "right" }}>≈ $/u</th>
                            <th style={{ textAlign: "right" }}>≈ stack</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.keys(playerInv).length === 0 ? (
                            <tr>
                              <td colSpan={4} className="realm-help" style={{ padding: "10px 8px" }}>
                                Your pack is empty. <strong>Produce on a surveyed plot</strong>, buy from the Bazaar, or accept a supply contract to stock
                                materials.
                              </td>
                            </tr>
                          ) : null}
                          {Object.entries(playerInv)
                            .sort(([a], [b]) => a.localeCompare(b))
                            .map(([k, v]) => {
                              const unitCents = bookMidpointCentsPerUnit(world.market_history, k);
                              const unitUsd =
                                unitCents != null ? `~$${(unitCents / 100).toFixed(2)}` : "—";
                              const stackUsd =
                                unitCents != null ? `~$${((unitCents * v) / 100).toFixed(2)}` : "—";
                              return (
                                <tr key={k}>
                                  <td>{displayMaterial(k)}</td>
                                  <td style={{ textAlign: "right", fontFamily: "var(--realm-mono)" }}>{v}</td>
                                  <td style={{ textAlign: "right", fontFamily: "var(--realm-mono)", fontSize: 13 }}>
                                    {unitUsd}
                                  </td>
                                  <td style={{ textAlign: "right", fontFamily: "var(--realm-mono)", fontSize: 13 }}>
                                    {stackUsd}
                                  </td>
                                </tr>
                              );
                            })}
                        </tbody>
                      </table>
                    </>
                  ) : null}

                  {tab === "market" ? (
                    <>
                      <SectionTitle>Markets</SectionTitle>
                      <p className="realm-help" style={{ marginTop: 0, marginBottom: 8 }}>
                        Pick a commodity to load its chart and order book. Use ◀ ▶, click a tile, or type an engine id (e.g. <code>grain</code>).
                      </p>
                      <div className="realm-bazaar-watchlist">
                        <div className="realm-bazaar-watchlist__controls">
                          <button
                            type="button"
                            className="realm-btn realm-btn--ghost realm-btn--sm"
                            aria-label="Previous market"
                            disabled={bazaarSymbolList.length === 0}
                            onClick={() => {
                              const list = bazaarSymbolList;
                              if (!list.length) return;
                              const cur = bazaarActiveId;
                              const i = list.indexOf(cur);
                              const from = i >= 0 ? i : 0;
                              const id = list[(from - 1 + list.length) % list.length];
                              setBazaarSymbol(id);
                              setBazaarActiveId(id);
                            }}
                          >
                            ◀
                          </button>
                          <label className="realm-label">
                            Symbol
                            <input
                              className="realm-input"
                              value={bazaarSymbol}
                              onChange={(e) => syncBazaarFieldFromDomValue(e.target.value)}
                              onInput={(e) => syncBazaarFieldFromDomValue((e.target as HTMLInputElement).value)}
                              onBlur={(e) => {
                                const raw = (e.target as HTMLInputElement).value;
                                const n = normalizeBazaarSymbolId(raw) || bazaarSymbolList[0] || "timber";
                                setBazaarSymbol(n);
                                setBazaarActiveId(n);
                              }}
                              list="realm-bazaar-datalist"
                              spellCheck={false}
                              autoCapitalize="off"
                              autoCorrect="off"
                              style={{ width: 140 }}
                            />
                          </label>
                          <datalist id="realm-bazaar-datalist">
                            {bazaarSymbolList.map((s) => (
                              <option key={s} value={s} />
                            ))}
                          </datalist>
                          <button
                            type="button"
                            className="realm-btn realm-btn--ghost realm-btn--sm"
                            aria-label="Next market"
                            disabled={bazaarSymbolList.length === 0}
                            onClick={() => {
                              const list = bazaarSymbolList;
                              if (!list.length) return;
                              const cur = bazaarActiveId;
                              const i = list.indexOf(cur);
                              const from = i >= 0 ? i : 0;
                              const id = list[(from + 1) % list.length];
                              setBazaarSymbol(id);
                              setBazaarActiveId(id);
                            }}
                          >
                            ▶
                          </button>
                        </div>
                        <div className="realm-bazaar-watchlist__chips" role="listbox" aria-label="Markets">
                          {bazaarSymbolList.map((s) => {
                            const on = s === bazaarActiveId;
                            const bidC = liveBestBidForMaterial(world.market_bids, s);
                            const askC = liveBestAskForMaterial(world.market_asks, s);
                            const bidS = bidC != null ? formatUsdFromCents(bidC) : "—";
                            const askS = askC != null ? formatUsdFromCents(askC) : "—";
                            return (
                              <button
                                key={s}
                                type="button"
                                role="option"
                                aria-selected={on}
                                className={`realm-bazaar-chip${on ? " realm-bazaar-chip--on" : ""}`}
                                onClick={() => {
                                  setBazaarSymbol(s);
                                  setBazaarActiveId(s);
                                }}
                              >
                                <span className="realm-bazaar-chip__name">{displayMaterial(s)}</span>
                                <span className="realm-bazaar-chip__quote">
                                  {bidS} bid · {askS} ask
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </div>

                      <SectionTitle>Price · {displayMaterial(bazaarActiveId)}</SectionTitle>
                      <p className="realm-help" style={{ marginTop: 0, marginBottom: 8 }}>
                        {world.market_intel_active ? (
                          <>
                            <strong>Full history</strong> — market analytics active through tick{" "}
                            {world.market_intel_expires_tick ?? "—"}.
                          </>
                        ) : (
                          <>
                            Free chart shows only the last{" "}
                            <strong>{world.market_history_free_window_ticks ?? 48}</strong> recorded ticks. Purchase extended visibility to see the full feed
                            in this client.
                          </>
                        )}{" "}
                        <button type="button" className="realm-btn realm-btn--ghost realm-btn--sm" disabled={busy} onClick={() => void buyMarketIntel()}>
                          Buy market intel ($250)
                        </button>
                      </p>
                      <div className="realm-chart-card">
                        <MarketHistoryChart history={world.market_history ?? []} symbol={bazaarActiveId} />
                      </div>

                      <SectionTitle>Order book · {displayMaterial(bazaarActiveId)}</SectionTitle>
                      <p className="realm-help" style={{ marginTop: 0, marginBottom: 8 }}>
                        Only resting orders for the symbol above. Switch markets to see other commodities.
                      </p>
                      <SectionTitle style={{ fontSize: "0.92em", opacity: 0.95 }}>Asks (sellers)</SectionTitle>
                      {(world.market_asks ?? []).filter((a) => a.material === bazaarActiveId).length === 0 ? (
                        <p className="realm-help">
                          No asks for {displayMaterial(bazaarActiveId)}. <strong>List for sale</strong> below to post a price.
                        </p>
                      ) : (
                        <table className="realm-table">
                          <thead>
                            <tr>
                              <th style={{ textAlign: "right" }}>Qty</th>
                              <th style={{ textAlign: "right" }}>~$/unit</th>
                              <th>Seller</th>
                              <th style={{ textAlign: "right" }}> </th>
                            </tr>
                          </thead>
                          <tbody>
                            {(world.market_asks ?? [])
                              .filter((a) => a.material === bazaarActiveId)
                              .map((a) => (
                                <tr key={a.order_id}>
                                  <td style={{ textAlign: "right" }}>{a.qty}</td>
                                  <td style={{ textAlign: "right" }}>{formatUsdPerUnitFromCentsPerUnit(a.price_per_unit_cents)}</td>
                                  <td>{displayParty(a.party)}</td>
                                  <td style={{ textAlign: "right" }}>
                                    {a.party === "player" ? (
                                      <button
                                        type="button"
                                        className="realm-btn realm-btn--ghost realm-btn--sm"
                                        disabled={busy}
                                        onClick={() => void cancelAsk(a.order_id)}
                                      >
                                        Cancel
                                      </button>
                                    ) : (
                                      <span className="realm-help"> </span>
                                    )}
                                  </td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      )}
                      <SectionTitle style={{ fontSize: "0.92em", opacity: 0.95 }}>Bids (buyers)</SectionTitle>
                      {(world.market_bids ?? []).filter((b) => b.material === bazaarActiveId).length === 0 ? (
                        <p className="realm-help">
                          No bids for {displayMaterial(bazaarActiveId)}. <strong>Place limit bid</strong> below to join the book.
                        </p>
                      ) : (
                        <table className="realm-table">
                          <thead>
                            <tr>
                              <th style={{ textAlign: "right" }}>Qty</th>
                              <th style={{ textAlign: "right" }}>Max ~$/unit</th>
                              <th>Buyer</th>
                              <th style={{ textAlign: "right" }}> </th>
                            </tr>
                          </thead>
                          <tbody>
                            {(world.market_bids ?? [])
                              .filter((b) => b.material === bazaarActiveId)
                              .map((b) => (
                                <tr key={b.order_id}>
                                  <td style={{ textAlign: "right" }}>{b.qty}</td>
                                  <td style={{ textAlign: "right" }}>{formatUsdPerUnitFromCentsPerUnit(b.max_price_per_unit_cents)}</td>
                                  <td>{displayParty(b.party)}</td>
                                  <td style={{ textAlign: "right" }}>
                                    {b.party === "player" ? (
                                      <button
                                        type="button"
                                        className="realm-btn realm-btn--ghost realm-btn--sm"
                                        disabled={busy}
                                        onClick={() => void cancelBid(b.order_id)}
                                      >
                                        Cancel
                                      </button>
                                    ) : (
                                      <span className="realm-help"> </span>
                                    )}
                                  </td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      )}

                      <SectionTitle>Trade · {displayMaterial(bazaarActiveId)}</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Bids and asks below use the <strong>selected symbol</strong> only. Mid from history (if any):{" "}
                        {(() => {
                          const u = bookMidpointCentsPerUnit(world.market_history, bazaarActiveId);
                          return u != null ? `~${formatUsdFromCents(u)}/u` : "—";
                        })()}
                      </p>
                      <SectionTitle style={{ fontSize: "0.92em", opacity: 0.95 }}>Place limit bid</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Locks cash for up to quantity × your max price; matches cheaper listed offers automatically.
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                        <label className="realm-label">
                          Qty
                          <input
                            className="realm-input"
                            value={bidQty}
                            onChange={(e) => setBidQty(e.target.value)}
                            style={{ width: 56 }}
                          />
                        </label>
                        <label className="realm-label">
                          Max $/unit
                          <input
                            className="realm-input"
                            value={bidMaxDollars}
                            onChange={(e) => setBidMaxDollars(e.target.value)}
                            style={{ width: 72 }}
                          />
                        </label>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void placeBuyOrder()}>
                          Place bid
                        </button>
                      </div>
                      <SectionTitle style={{ fontSize: "0.92em", opacity: 0.95 }}>List for sale</SectionTitle>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                        <label className="realm-label">
                          Qty
                          <input
                            className="realm-input"
                            value={sellQty}
                            onChange={(e) => setSellQty(e.target.value)}
                            style={{ width: 56 }}
                          />
                        </label>
                        <label className="realm-label">
                          $/unit
                          <input
                            className="realm-input"
                            value={sellPriceDollars}
                            onChange={(e) => setSellPriceDollars(e.target.value)}
                            style={{ width: 72 }}
                          />
                        </label>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void placeSellOrder()}>
                          Place ask
                        </button>
                      </div>
                      <button
                        type="button"
                        className="realm-btn realm-btn--ghost realm-btn--sm"
                        style={{ marginTop: 14 }}
                        onClick={() => setBazaarAdvancedOpen((o) => !o)}
                      >
                        {bazaarAdvancedOpen ? "Hide advanced orders" : "Advanced: iceberg, reputation gates, sell-into-book, direct trade"}
                      </button>
                      {bazaarAdvancedOpen ? (
                        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid rgba(255,255,255,0.08)" }}>
                          <p className="realm-help" style={{ marginTop: 0 }}>
                            Optional: show only part of your size on the book (iceberg), or require a minimum &quot;honored&quot; reputation on the other
                            party before you match.
                          </p>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end", marginBottom: 10 }}>
                            <label className="realm-label">
                              Bid iceberg clip (units)
                              <input
                                className="realm-input"
                                value={advBidIceberg}
                                onChange={(e) => setAdvBidIceberg(e.target.value)}
                                style={{ width: 80 }}
                                placeholder="off"
                              />
                            </label>
                            <label className="realm-label">
                              Min counterparty honored
                              <input
                                className="realm-input"
                                value={advBidHonored}
                                onChange={(e) => setAdvBidHonored(e.target.value)}
                                style={{ width: 56 }}
                              />
                            </label>
                            <label className="realm-label">
                              Ask iceberg clip (units)
                              <input
                                className="realm-input"
                                value={advAskIceberg}
                                onChange={(e) => setAdvAskIceberg(e.target.value)}
                                style={{ width: 80 }}
                                placeholder="off"
                              />
                            </label>
                            <label className="realm-label">
                              Min counterparty honored
                              <input
                                className="realm-input"
                                value={advAskHonored}
                                onChange={(e) => setAdvAskHonored(e.target.value)}
                                style={{ width: 56 }}
                              />
                            </label>
                          </div>
                          <SectionTitle>Sell into bids</SectionTitle>
                          <p className="realm-help" style={{ marginBottom: 10 }}>
                            Walks the bid side for <strong>{displayMaterial(bazaarActiveId)}</strong>; you must hold the goods. Paid from buyers&apos;
                            escrow up to their limits.
                          </p>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                            <label className="realm-label">
                              Max qty
                              <input
                                className="realm-input"
                                value={sellFillQty}
                                onChange={(e) => setSellFillQty(e.target.value)}
                                style={{ width: 56 }}
                              />
                            </label>
                            <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void sellIntoBids()}>
                              Sell into book
                            </button>
                          </div>
                          <SectionTitle>Direct trade (P2P)</SectionTitle>
                          <p className="realm-help" style={{ marginBottom: 10 }}>
                            One-shot exchange with a named party — no central book. Material is independent of the chart symbol.
                          </p>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                            <label className="realm-label">
                              You are
                              <select
                                className="realm-input"
                                value={p2pRole}
                                onChange={(e) => setP2pRole(e.target.value as "sell" | "buy")}
                                style={{ width: 120 }}
                              >
                                <option value="sell">Seller</option>
                                <option value="buy">Buyer</option>
                              </select>
                            </label>
                            <label className="realm-label">
                              Counterparty
                              <input
                                className="realm-input"
                                value={p2pParty}
                                onChange={(e) => setP2pParty(e.target.value)}
                                style={{ width: 180 }}
                              />
                            </label>
                            <label className="realm-label">
                              Material
                              <input
                                className="realm-input"
                                value={p2pMaterial}
                                onChange={(e) => setP2pMaterial(e.target.value)}
                                style={{ width: 120 }}
                              />
                            </label>
                            <label className="realm-label">
                              Qty
                              <input
                                className="realm-input"
                                value={p2pQty}
                                onChange={(e) => setP2pQty(e.target.value)}
                                style={{ width: 48 }}
                              />
                            </label>
                            <label className="realm-label">
                              Total price ($)
                              <input
                                className="realm-input"
                                value={p2pTotalDollars}
                                onChange={(e) => setP2pTotalDollars(e.target.value)}
                                style={{ width: 72 }}
                              />
                            </label>
                            <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void runP2pTrade()}>
                              Execute trade
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </>
                  ) : null}

                  {tab === "logistics" ? (
                    <>
                      <SectionTitle>In transit</SectionTitle>
                      {(world.in_transit ?? []).length === 0 ? (
                        <p className="realm-help">
                          Nothing in flight. <strong>Ship goods</strong> between two plots you own to move inventory without trading.
                        </p>
                      ) : (
                        <ul className="realm-help" style={{ paddingLeft: 18, margin: 0 }}>
                          {(world.in_transit ?? []).map((s) => (
                            <li key={s.id}>
                              {formatQtyTimesMaterial(s.qty, s.material)} → {s.dest_plot_id} · arrive{" "}
                              {formatDeliverBy(world.tick, s.arrive_tick, msPerSimTick)}
                            </li>
                          ))}
                        </ul>
                      )}
                      <SectionTitle>Ship goods</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Choose origin and destination from land you own. Fee is paid when you dispatch; travel time grows with distance.
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                        <label className="realm-label">
                          From plot
                          <select
                            className="realm-input"
                            value={shipFrom}
                            onChange={(e) => setShipFrom(e.target.value)}
                            style={{ minWidth: 120 }}
                          >
                            {playerPlotChoices.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.id}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="realm-label">
                          To plot
                          <select
                            className="realm-input"
                            value={shipTo}
                            onChange={(e) => setShipTo(e.target.value)}
                            style={{ minWidth: 120 }}
                          >
                            {playerPlotChoices.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.id}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="realm-label">
                          Material
                          {Object.keys(playerInv).length > 0 ? (
                            <select
                              className="realm-input"
                              value={shipMaterial}
                              onChange={(e) => setShipMaterial(e.target.value)}
                              style={{ minWidth: 140 }}
                            >
                              {Object.keys(playerInv)
                                .sort((a, b) => a.localeCompare(b))
                                .map((k) => (
                                  <option key={k} value={k}>
                                    {displayMaterial(k)} ({playerInv[k]})
                                  </option>
                                ))}
                            </select>
                          ) : (
                            <input
                              className="realm-input"
                              value={shipMaterial}
                              onChange={(e) => setShipMaterial(e.target.value)}
                              style={{ width: 120 }}
                              placeholder="grain"
                            />
                          )}
                        </label>
                        <label className="realm-label">
                          Qty
                          <input className="realm-input" value={shipQty} onChange={(e) => setShipQty(e.target.value)} style={{ width: 48 }} />
                        </label>
                        <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void shipGoods()}>
                          Dispatch
                        </button>
                      </div>
                      {shipPreview?.fee != null && shipPreview.dist != null && shipPreview.dist > 0 && shipPreview.arrive != null ? (
                        <p className="realm-help" style={{ marginTop: 10 }}>
                          Preview: <strong>{formatUsdFromCents(shipPreview.fee)}</strong> shipping fee · arrives{" "}
                          {formatDeliverBy(world.tick, shipPreview.arrive, msPerSimTick)} · {shipPreview.dist} tiles apart
                        </p>
                      ) : (
                        <p className="realm-help" style={{ marginTop: 10 }}>
                          Pick two different owned plots to see fee and arrival time.
                        </p>
                      )}
                    </>
                  ) : null}

                  {tab === "schematic" ? (
                    <>
                      <SectionTitle>Plot schematic</SectionTitle>
                      <PlotSchematicPanel
                        recipes={workshopRecipesForSelectedPlot as SchematicRecipe[]}
                        playerInventory={playerInv}
                        eligiblePlots={schematicEligiblePlots}
                        selectedPlotId={selectedPlotId}
                        onSelectPlot={setSelectedPlotId}
                        disabled={busy}
                      />
                    </>
                  ) : null}

                  {tab === "hire" ? (
                    <>
                      <SectionTitle>Hire (employment)</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Signing bonus opens an employment record. Each production run routes <strong>40%</strong> of recipe labor cash to hired parties (split
                        evenly); the rest goes to system reserve as before.
                      </p>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Active hires: {(world.stub_hires ?? []).length}
                      </p>
                      {(world.hire_catalog ?? []).length === 0 ? (
                        <p className="realm-help">
                          No NPCs are on the hiring board in this snapshot. <strong>Advance a few ticks</strong> or reload — catalog comes from the
                          bootstrap world.
                        </p>
                      ) : (
                        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 16px" }}>
                          {(world.hire_catalog ?? []).map((row) => (
                            <li key={row.party} style={{ marginBottom: 6 }}>
                              <button
                                type="button"
                                className="realm-list-btn"
                                disabled={busy}
                                onClick={() => void hireNpc(row.party, row.suggested_signing_cents)}
                              >
                                {row.role} — {displayParty(row.party)} — {formatUsdFromCents(row.suggested_signing_cents)} bonus
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </>
                  ) : null}

                  {tab === "pacts" ? (
                    <>
                      <SectionTitle>Supply contracts</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Propose terms: the <strong>buyer accepts</strong>, then the <strong>supplier fulfills</strong> (goods + payment) before the deadline
                        tick or the supplier is marked <strong>breached</strong>. Use the toggle to play either side.
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 12 }}>
                        <span className="realm-help" style={{ margin: 0 }}>
                          You are:
                        </span>
                        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                          <input
                            type="radio"
                            name="supply-you-are"
                            checked={supplyYouAre === "supplier"}
                            onChange={() => setSupplyYouAre("supplier")}
                          />
                          Supplier (you deliver)
                        </label>
                        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                          <input
                            type="radio"
                            name="supply-you-are"
                            checked={supplyYouAre === "buyer"}
                            onChange={() => setSupplyYouAre("buyer")}
                          />
                          Buyer (you pay on fulfill)
                        </label>
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end", marginBottom: 14 }}>
                        <label className="realm-label">
                          {supplyYouAre === "supplier" ? "Buyer" : "Supplier"}
                          <select
                            className="realm-input"
                            value={pactCounterpartyChoices.includes(supplyCounterparty) ? supplyCounterparty : pactCounterpartyChoices[0] ?? ""}
                            onChange={(e) => setSupplyCounterparty(e.target.value)}
                            style={{ minWidth: 160 }}
                          >
                            {pactCounterpartyChoices.length === 0 ? (
                              <option value="">—</option>
                            ) : (
                              pactCounterpartyChoices.map((p) => (
                                <option key={p} value={p}>
                                  {displayParty(p)}
                                </option>
                              ))
                            )}
                          </select>
                        </label>
                        <label className="realm-label">
                          Material
                          <input
                            className="realm-input"
                            value={supplyMaterial}
                            onChange={(e) => setSupplyMaterial(e.target.value)}
                            style={{ width: 100 }}
                          />
                        </label>
                        <label className="realm-label">
                          Qty
                          <input
                            className="realm-input"
                            value={supplyQty}
                            onChange={(e) => setSupplyQty(e.target.value)}
                            style={{ width: 48 }}
                          />
                        </label>
                        <label className="realm-label">
                          Total price
                          <input
                            className="realm-input"
                            value={supplyTotalDollars}
                            onChange={(e) => setSupplyTotalDollars(e.target.value)}
                            style={{ width: 72 }}
                            placeholder="0.80"
                          />
                        </label>
                        <label className="realm-label">
                          Deadline (ticks from now)
                          <input
                            className="realm-input"
                            value={supplyDueTicks}
                            onChange={(e) => setSupplyDueTicks(e.target.value)}
                            style={{ width: 72 }}
                          />
                        </label>
                        <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void proposeSupplyContract()}>
                          Propose contract
                        </button>
                      </div>

                      {supplyContractRows.length === 0 ? (
                        <p className="realm-help">
                          No supply contracts yet. <strong>Propose one above</strong> to lock in a future delivery at a fixed total price.
                        </p>
                      ) : (
                        <table className="realm-table" style={{ marginBottom: 16 }}>
                          <thead>
                            <tr>
                              <th>Id</th>
                              <th>Status</th>
                              <th>Supplier</th>
                              <th>Buyer</th>
                              <th>Goods</th>
                              <th style={{ textAlign: "right" }}>Qty</th>
                              <th style={{ textAlign: "right" }}>Total</th>
                              <th>Deliver by</th>
                              <th style={{ textAlign: "right" }}> </th>
                            </tr>
                          </thead>
                          <tbody>
                            {supplyContractRows.map((c) => (
                              <tr key={c.id}>
                                <td style={{ fontFamily: "var(--realm-mono)", fontSize: 12 }}>{c.id}</td>
                                <td>{c.status}</td>
                                <td>{displayParty(c.supplier)}</td>
                                <td>{displayParty(c.buyer)}</td>
                                <td>{c.material != null ? displayMaterial(c.material) : "—"}</td>
                                <td style={{ textAlign: "right" }}>{c.qty ?? "—"}</td>
                                <td style={{ textAlign: "right" }}>{formatUsdFromCents(c.total_price_cents)}</td>
                                <td style={{ fontSize: 12 }}>{formatDeliverBy(world.tick, c.deliver_by_tick, msPerSimTick)}</td>
                                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                                  {c.status === "proposed" && c.buyer === "player" ? (
                                    <button
                                      type="button"
                                      className="realm-btn realm-btn--ghost realm-btn--sm"
                                      disabled={busy}
                                      onClick={() => void acceptSupplyContractRow(c.id)}
                                    >
                                      Accept as buyer
                                    </button>
                                  ) : null}
                                  {c.status === "active" && c.supplier === "player" ? (
                                    <button
                                      type="button"
                                      className="realm-btn realm-btn--ghost realm-btn--sm"
                                      disabled={busy}
                                      onClick={() => void fulfillSupplyContractRow(c.id)}
                                      style={{ marginLeft: 6 }}
                                    >
                                      Fulfill
                                    </button>
                                  ) : null}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}

                      <SectionTitle>Financial stubs (Phase 2)</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Engine FSMs for <strong>loan</strong> (principal → repay), <strong>equity_stub</strong> (investment + per-tick dividends), and{" "}
                        <strong>service_sub</strong> (prepaid window). Use the contract id field after each propose; run the clock for tick-driven equity and
                        loan collections.
                      </p>
                      <label className="realm-label" style={{ display: "block", marginBottom: 10 }}>
                        Last stub contract id
                        <input
                          className="realm-input"
                          value={stubPhase2ContractId}
                          onChange={(e) => setStubPhase2ContractId(e.target.value)}
                          spellCheck={false}
                          style={{ width: "100%", maxWidth: 360 }}
                          placeholder="c-…"
                        />
                      </label>

                      <p className="realm-help" style={{ margin: "12px 0 6px", fontWeight: 600 }}>
                        Loan (you lend as player)
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end", marginBottom: 12 }}>
                        <label className="realm-label">
                          Borrower
                          <select
                            className="realm-input"
                            value={pactCounterpartyChoices.includes(stubLoanBorrower) ? stubLoanBorrower : pactCounterpartyChoices[0] ?? ""}
                            onChange={(e) => setStubLoanBorrower(e.target.value)}
                            style={{ minWidth: 160 }}
                          >
                            {pactCounterpartyChoices.map((p) => (
                              <option key={p} value={p}>
                                {displayParty(p)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="realm-label">
                          Principal ($)
                          <input
                            className="realm-input"
                            value={stubLoanPrincipalDollars}
                            onChange={(e) => setStubLoanPrincipalDollars(e.target.value)}
                            style={{ width: 80 }}
                          />
                        </label>
                        <label className="realm-label">
                          Repay total ($)
                          <input
                            className="realm-input"
                            value={stubLoanRepayDollars}
                            onChange={(e) => setStubLoanRepayDollars(e.target.value)}
                            style={{ width: 80 }}
                          />
                        </label>
                        <label className="realm-label">
                          Due in (ticks)
                          <input
                            className="realm-input"
                            value={stubLoanDueTicks}
                            onChange={(e) => setStubLoanDueTicks(e.target.value)}
                            style={{ width: 56 }}
                          />
                        </label>
                        <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void proposeLoanStub()}>
                          Propose loan
                        </button>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void acceptLoanStubAsBorrower()}>
                          Accept as borrower
                        </button>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void repayLoanStub()}>
                          Repay
                        </button>
                      </div>

                      <p className="realm-help" style={{ margin: "12px 0 6px", fontWeight: 600 }}>
                        Equity stub
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end", marginBottom: 12 }}>
                        <label className="realm-label">
                          Issuer
                          <select
                            className="realm-input"
                            value={["player", ...pactCounterpartyChoices].includes(stubEquityIssuer) ? stubEquityIssuer : "player"}
                            onChange={(e) => setStubEquityIssuer(e.target.value)}
                          >
                            <option value="player">You</option>
                            {pactCounterpartyChoices.map((p) => (
                              <option key={p} value={p}>
                                {displayParty(p)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="realm-label">
                          Investor
                          <select
                            className="realm-input"
                            value={["player", ...pactCounterpartyChoices].includes(stubEquityInvestor) ? stubEquityInvestor : "t1_consumer"}
                            onChange={(e) => setStubEquityInvestor(e.target.value)}
                          >
                            <option value="player">You</option>
                            {pactCounterpartyChoices.map((p) => (
                              <option key={`inv-${p}`} value={p}>
                                {displayParty(p)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="realm-label">
                          Investment ($)
                          <input
                            className="realm-input"
                            value={stubEquityInvestmentDollars}
                            onChange={(e) => setStubEquityInvestmentDollars(e.target.value)}
                            style={{ width: 72 }}
                          />
                        </label>
                        <label className="realm-label">
                          Dividend (¢/tick)
                          <input
                            className="realm-input"
                            value={stubEquityDivCents}
                            onChange={(e) => setStubEquityDivCents(e.target.value)}
                            style={{ width: 56 }}
                          />
                        </label>
                        <label className="realm-label">
                          Ticks
                          <input
                            className="realm-input"
                            value={stubEquityDivTicks}
                            onChange={(e) => setStubEquityDivTicks(e.target.value)}
                            style={{ width: 48 }}
                          />
                        </label>
                        <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void proposeEquityStubPanel()}>
                          Propose equity
                        </button>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void acceptEquityStubPanel()}>
                          Accept as investor
                        </button>
                      </div>

                      <p className="realm-help" style={{ margin: "12px 0 6px", fontWeight: 600 }}>
                        Service subscription (prepaid)
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end", marginBottom: 14 }}>
                        <label className="realm-label">
                          Provider
                          <select
                            className="realm-input"
                            value={["player", ...pactCounterpartyChoices].includes(stubServiceProvider) ? stubServiceProvider : "player"}
                            onChange={(e) => setStubServiceProvider(e.target.value)}
                          >
                            <option value="player">You</option>
                            {pactCounterpartyChoices.map((p) => (
                              <option key={`pr-${p}`} value={p}>
                                {displayParty(p)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="realm-label">
                          Subscriber
                          <select
                            className="realm-input"
                            value={["player", ...pactCounterpartyChoices].includes(stubServiceSubscriber) ? stubServiceSubscriber : "t1_consumer"}
                            onChange={(e) => setStubServiceSubscriber(e.target.value)}
                          >
                            <option value="player">You</option>
                            {pactCounterpartyChoices.map((p) => (
                              <option key={`sub-${p}`} value={p}>
                                {displayParty(p)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="realm-label">
                          Fee ($)
                          <input
                            className="realm-input"
                            value={stubServiceFeeDollars}
                            onChange={(e) => setStubServiceFeeDollars(e.target.value)}
                            style={{ width: 64 }}
                          />
                        </label>
                        <label className="realm-label">
                          Duration (ticks)
                          <input
                            className="realm-input"
                            value={stubServiceDurationTicks}
                            onChange={(e) => setStubServiceDurationTicks(e.target.value)}
                            style={{ width: 56 }}
                          />
                        </label>
                        <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void proposeServiceStubPanel()}>
                          Propose service
                        </button>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void acceptServiceStubPanel()}>
                          Accept as subscriber
                        </button>
                      </div>

                      {financialStubRows.length === 0 ? (
                        <p className="realm-help" style={{ marginBottom: 16 }}>
                          No financial stub rows in this snapshot yet.
                        </p>
                      ) : (
                        <table className="realm-table" style={{ marginBottom: 16 }}>
                          <thead>
                            <tr>
                              <th>Id</th>
                              <th>Kind</th>
                              <th>Status</th>
                              <th>Notes</th>
                            </tr>
                          </thead>
                          <tbody>
                            {financialStubRows.map((c) => (
                              <tr key={String(c.id)}>
                                <td style={{ fontFamily: "var(--realm-mono)", fontSize: 12 }}>{String(c.id)}</td>
                                <td>{String(c.kind)}</td>
                                <td>{String(c.status ?? "—")}</td>
                                <td style={{ fontSize: 12 }} className="realm-help">
                                  {c.kind === "loan"
                                    ? `${String(c.lender)} → ${String(c.borrower)} · repay ${formatUsdFromCents(Number(c.repay_cents))}`
                                    : c.kind === "equity_stub"
                                      ? `${String(c.issuer)} / ${String(c.investor)} · ${String(c.dividends_remaining ?? "—")} div left`
                                      : `${String(c.provider)} → ${String(c.subscriber)} · to tick ${String(c.expires_tick ?? "—")}`}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}

                      {SHOW_INTERNAL_ATLAS_AND_DEV_CONTRACTS ? (
                        <>
                          <SectionTitle>Generic memo (dev)</SectionTitle>
                          <p className="realm-help" style={{ marginBottom: 8 }}>
                            Last memo id: {lastContractId ?? "—"} — honoring increments both parties&apos; <code>honored</code> (no goods).
                          </p>
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void proposeMemoContract()}>
                              Propose memo
                            </button>
                            <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void honorContract()}>
                              Honor last memo
                            </button>
                          </div>
                        </>
                      ) : null}
                    </>
                  ) : null}

                  {tab === "codex" ? (
                    SHOW_INTERNAL_ATLAS_AND_DEV_CONTRACTS ? (
                      <div className="realm-codex-grid">
                        <p className="realm-help" style={{ marginTop: 0 }}>
                          Atlas is an internal roadmap: what is live in this build versus stub and longer-term plans. Cards with a jump link open the related
                          panel.
                        </p>
                      {(
                        [
                          ["live", "Live in this build"],
                          ["stub", "Stub / partial"],
                          ["planned", "Planned"],
                        ] as const
                      ).map(([lane, label]) => (
                        <div key={lane} className={`realm-codex-lane realm-codex-lane--${lane}`}>
                          <h3 className="realm-codex-lane-title">{label}</h3>
                          <div className="realm-codex-cards">
                            {FRONTIER_FEATURES.filter((f) => f.lane === lane).map((f) =>
                              f.jumpTab ? (
                              <button
                                key={f.id}
                                type="button"
                                className="realm-codex-card"
                                onClick={() => {
                                  setTab(f.jumpTab!);
                                }}
                              >
                                <div className="realm-codex-card__title">{f.title}</div>
                                <div className="realm-codex-card__detail">{f.detail}</div>
                                <div className="realm-codex-card__jump">→ Open {panelHeadline(f.jumpTab)}</div>
                              </button>
                              ) : (
                                <div key={f.id} className="realm-codex-card realm-codex-card--static">
                                  <div className="realm-codex-card__title">{f.title}</div>
                                  <div className="realm-codex-card__detail">{f.detail}</div>
                                </div>
                              ),
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="realm-help" style={{ marginTop: 0 }}>
                      Atlas (internal roadmap) is not shown in this build.
                    </p>
                  )
                ) : null}

                  {tab === "log" ? (
                    <>
                      <SectionTitle>Action log</SectionTitle>
                      <div className="realm-log">
                        {eventLogReversed.length === 0 ? (
                          <span className="realm-help">
                            No events yet. <strong>Run the clock</strong>, trade, produce, or ship — the chronicle records engine outcomes here.
                          </span>
                        ) : (
                          eventLogReversed.map((e, i) => (
                            <div key={i} className="realm-log-line">
                              <span style={{ opacity: 0.5 }}>t{e.tick}</span>{" "}
                              <span style={{ opacity: 0.65 }}>[{e.kind}]</span> {prettifyChronicleMessage(e.message)}
                            </div>
                          ))
                        )}
                      </div>
                      <SectionTitle>Persistence</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Save writes a SQLite snapshot you can reload in this client. Your last save is remembered for the session.
                      </p>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void persistenceSave()}>
                          Save snapshot
                        </button>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void persistenceLoad()}>
                          Load snapshot
                        </button>
                      </div>
                    </>
                  ) : null}
                </motion.div>
              </AnimatePresence>
                </motion.aside>
              ) : null}
            </AnimatePresence>

            {!commandOpen ? (
              <button type="button" className="realm-panel-fab" onClick={() => setCommandOpen(true)} aria-label="Open side panel">
                Show panel
              </button>
            ) : null}
          </div>
        </>
      ) : (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="realm-help"
          style={{ fontSize: 22, padding: 24, textAlign: "center" }}
        >
          Loading world…
        </motion.p>
      )}
      <FrontierSettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        busy={busy}
        simPaused={simPaused}
        onTogglePause={toggleSimPause}
        simSpeedIdx={simSpeedIdx}
        simSpeedLabels={SIM_SPEED_LABELS}
        simSpeedsMs={SIM_SPEEDS_MS}
        onSetSimSpeedIdx={setSimSpeedPreset}
        showDevReset={SHOW_INTERNAL_ATLAS_AND_DEV_CONTRACTS}
        devResetScenario={devResetScenario}
        onDevResetScenario={(s) => setDevResetScenario(s)}
        onDevResetWorld={devResetWorld}
      />
      <FrontierCommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        activeTab={tab}
        onPick={(t) => {
          setTab(t);
          setCommandOpen(true);
        }}
        onOpenSettings={() => setSettingsOpen(true)}
      />
    </main>
  );
}
