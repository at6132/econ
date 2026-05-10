"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { FRONTIER_FEATURES } from "./frontierFeatures";
import { FRONTIER_ONBOARD_STORAGE_KEY } from "./frontierConstants";
import { playFrontierSfx, resumeFrontierAudio } from "./frontierSfx";
import { FRONTIER_MENU, type TabId } from "./frontierMenu";
import { FrontierTopNav } from "./FrontierTopNav";
import { buildOrganicMesh } from "./mapOrganicMesh";
import type { MapFxEvent, MapFxKind } from "./mapFxTypes";
import { MarketHistoryChart, type MarketHistorySnap } from "./MarketHistoryChart";
import { OnboardingModal } from "./OnboardingModal";
import { RealmMapFxOverlay } from "./RealmMapFxOverlay";
import { RealmMapMeshSvg } from "./RealmMapMeshSvg";
import { RealmMapParticlesCanvas } from "./RealmMapParticlesCanvas";

const MAP_PAD = 4;

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
  for (const g of FRONTIER_MENU) {
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

type EventLogEntryDto = {
  tick: number;
  kind: string;
  message: string;
};

type BuildingCatalogDto = {
  id: string;
  label: string;
  cost_cents: number;
};

type PlotBuildingDto = {
  plot_id: string;
  party: string;
  building_id: string;
  label: string;
  cost_cents: number;
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

function SectionTitle({ children }: { children: string }) {
  return <h3 className="realm-section-title">{children}</h3>;
}

export default function HomePage() {
  const [world, setWorld] = useState<WorldDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<TabId>("world");
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [selectedPlotId, setSelectedPlotId] = useState<string | null>(null);
  const [shipFrom, setShipFrom] = useState("p-0-0");
  const [shipTo, setShipTo] = useState("p-1-0");
  const [shipMaterial, setShipMaterial] = useState("timber");
  const [shipQty, setShipQty] = useState("1");
  const [sellMaterial, setSellMaterial] = useState("timber");
  const [sellQty, setSellQty] = useState("1");
  const [sellPriceCents, setSellPriceCents] = useState("500");
  const [bidMaterial, setBidMaterial] = useState("timber");
  const [bidQty, setBidQty] = useState("1");
  const [bidMaxCents, setBidMaxCents] = useState("500");
  const [sellFillMaterial, setSellFillMaterial] = useState("timber");
  const [sellFillQty, setSellFillQty] = useState("1");
  const [p2pRole, setP2pRole] = useState<"sell" | "buy">("sell");
  const [p2pParty, setP2pParty] = useState("t1_consumer");
  const [p2pMaterial, setP2pMaterial] = useState("grain");
  const [p2pQty, setP2pQty] = useState("1");
  const [p2pTotalCents, setP2pTotalCents] = useState("50");
  const [lastContractId, setLastContractId] = useState<string | null>(null);
  const [supplyBuyer, setSupplyBuyer] = useState("t1_consumer");
  const [supplyMaterial, setSupplyMaterial] = useState("grain");
  const [supplyQty, setSupplyQty] = useState("2");
  const [supplyTotalCents, setSupplyTotalCents] = useState("80");
  const [supplyDueTicks, setSupplyDueTicks] = useState("10");
  const [commandOpen, setCommandOpen] = useState(true);
  const mapViewportRef = useRef<HTMLDivElement>(null);
  const [viewportPx, setViewportPx] = useState({ w: 720, h: 520 });
  const [mapFx, setMapFx] = useState<MapFxEvent[]>([]);
  const mapFxSeq = useRef(0);
  const sparkSeqRef = useRef(0);
  const [sparks, setSparks] = useState<{ id: number; cx: number; cy: number; hue: number }[]>([]);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [mapZoom, setMapZoom] = useState(1);
  const [mapStyle, setMapStyle] = useState<"terrain" | "satellite" | "political">("terrain");
  const mapNavSuppress = useRef(false);
  const panDragRef = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null);
  const mapPanPointerId = useRef<number | null>(null);
  const panRef = useRef(pan);
  const mapZoomRef = useRef(mapZoom);
  const didPan = useRef(false);
  const didInitPan = useRef(false);

  panRef.current = pan;
  mapZoomRef.current = mapZoom;

  useEffect(() => {
    try {
      const v = localStorage.getItem("realm_frontier_map_style");
      if (v === "satellite" || v === "political" || v === "terrain") setMapStyle(v);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    didInitPan.current = false;
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
    try {
      if (typeof window !== "undefined" && !localStorage.getItem(FRONTIER_ONBOARD_STORAGE_KEY)) {
        setOnboardingOpen(true);
      }
    } catch {
      setOnboardingOpen(true);
    }
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

  const selectedPlot = useMemo(
    () => world?.plots.find((p) => p.id === selectedPlotId) ?? null,
    [world, selectedPlotId],
  );

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

  const playerCash =
    world?.balances_cents["cash:player"] != null
      ? (world.balances_cents["cash:player"] / 100).toFixed(2)
      : "—";

  async function tick() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/engine/tick", { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "tick",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 2)),
          label: "TURN",
        });
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function claimPlot(p: PlotDto) {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`/api/engine/plots/${encodeURIComponent(p.id)}/claim`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      queueFx({ kind: "claim", gx: p.x, gy: p.y, label: "CLAIM" });
      await load();
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
      queueFx({ kind: "survey", gx: p.x, gy: p.y, label: "SCAN" });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function produce(plotId: string, recipeId: string) {
    const plot = world?.plots.find((pp) => pp.id === plotId);
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
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
        "Reset the in-memory Frontier world to a fresh bootstrap (seed 42)? Unsaved progress is lost unless you saved to SQLite first.",
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/engine/dev/reset?seed=42", { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      didInitPan.current = false;
      await load();
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function marketBuyGrain() {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ party: "player", material: "grain", max_qty: "1" });
      const r = await fetch(`/api/engine/market/buy?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "trade",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 3)),
          label: "BUY",
        });
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function placeSellOrder() {
    const qty = Number(sellQty);
    const price = Number(sellPriceCents);
    if (!Number.isFinite(qty) || qty <= 0 || !Number.isFinite(price) || price <= 0) {
      setError("Sell qty and price (cents) must be positive numbers.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        party: "player",
        material: sellMaterial,
        qty: String(qty),
        price_per_unit_cents: String(price),
      });
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function placeBuyOrder() {
    const qty = Number(bidQty);
    const maxPx = Number(bidMaxCents);
    if (!Number.isFinite(qty) || qty <= 0 || !Number.isFinite(maxPx) || maxPx <= 0) {
      setError("Bid qty and max price (cents) must be positive numbers.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        party: "player",
        material: bidMaterial.trim(),
        qty: String(qty),
        max_price_per_unit_cents: String(maxPx),
      });
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
        material: sellFillMaterial.trim(),
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runP2pTrade() {
    const qty = Number(p2pQty);
    const total = Number(p2pTotalCents);
    if (!Number.isFinite(qty) || qty <= 0 || !Number.isFinite(total) || total < 0) {
      setError("P2P qty must be positive; total price (cents) must be zero or more.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const seller = p2pRole === "sell" ? "player" : p2pParty.trim();
      const buyer = p2pRole === "sell" ? p2pParty.trim() : "player";
      const q = new URLSearchParams({
        seller,
        buyer,
        material: p2pMaterial.trim(),
        qty: String(qty),
        total_price_cents: String(total),
      });
      const r = await fetch(`/api/engine/trade/p2p?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      if (grid.w > 0 && grid.h > 0) {
        queueFx({
          kind: "trade",
          gx: Math.max(0, Math.floor((grid.w - 1) / 2)),
          gy: Math.max(0, Math.floor((grid.h - 1) / 3)),
          label: "P2P",
        });
      }
      await load();
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function proposeSupplyContract() {
    const qty = Number(supplyQty);
    const total = Number(supplyTotalCents);
    const due = Number(supplyDueTicks);
    if (!Number.isFinite(qty) || qty <= 0 || !Number.isFinite(total) || total < 0 || !Number.isFinite(due) || due < 1) {
      setError("Supply: qty and due ticks must be positive; total price (cents) must be zero or more.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        supplier: "player",
        buyer: supplyBuyer.trim(),
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function acceptSupplyContractRow(contractId: string, buyerParty: string) {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ buyer: buyerParty, contract_id: contractId });
      const r = await fetch(`/api/engine/contracts/supply/accept?${q.toString()}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await load();
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function buildOnSelectedPlot(buildingId: string) {
    if (!selectedPlotId) {
      setError("Select a surveyed plot you own.");
      return;
    }
    const plot = world?.plots.find((pp) => pp.id === selectedPlotId);
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ building_id: buildingId, party: "player" });
      const r = await fetch(
        `/api/engine/plots/${encodeURIComponent(selectedPlotId)}/build?${q.toString()}`,
        { method: "POST" },
      );
      if (!r.ok) throw new Error(await r.text());
      if (plot) queueFx({ kind: "build", gx: plot.x, gy: plot.y, label: "RISE" });
      await load();
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function onPlotClick(p: PlotDto) {
    if (!p.owner) {
      void claimPlot(p);
      setSelectedPlotId(p.id);
      setTab("world");
      return;
    }
    if (p.owner === "player") {
      if (!p.surveyed) {
        void surveyPlot(p);
        setTab("world");
        return;
      }
      setSelectedPlotId(p.id);
      setTab("world");
    }
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
        localStorage.setItem("realm_frontier_map_style", next);
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  function onMapPointerDownCapture(e: React.PointerEvent) {
    if (e.button !== 0) return;
    (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
    mapPanPointerId.current = e.pointerId;
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
      const next = { x: d.px + dx, y: d.py + dy };
      panRef.current = next;
      setPan(next);
    }
  }

  function releaseMapPointerCapture() {
    const pid = mapPanPointerId.current;
    const el = mapViewportRef.current;
    if (pid != null && el) {
      try {
        el.releasePointerCapture(pid);
      } catch {
        /* not capturing */
      }
    }
    mapPanPointerId.current = null;
  }

  function onMapPointerUp() {
    releaseMapPointerCapture();
    if (didPan.current) mapNavSuppress.current = true;
    panDragRef.current = null;
  }

  function replayBriefing() {
    try {
      localStorage.removeItem(FRONTIER_ONBOARD_STORAGE_KEY);
    } catch {
      /* ignore */
    }
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
                <div className="realm-brand__sub">Frontier · solo build</div>
              </div>
              <div className="realm-stat-row">
                <motion.span
                  key={world.tick}
                  className="realm-pill"
                  initial={{ scale: 1.04, opacity: 0.7 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 500, damping: 28 }}
                >
                  Tick <strong>{world.tick}</strong>
                </motion.span>
                <span className="realm-pill">
                  Seed <strong>{world.seed}</strong>
                </span>
                <span className="realm-pill">
                  Cash <strong>${playerCash}</strong>
                </span>
                <motion.button
                  type="button"
                  className="realm-btn realm-btn--primary realm-btn--sm"
                  disabled={busy}
                  onClick={() => void tick()}
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                >
                  End turn
                </motion.button>
                <button type="button" className="realm-btn realm-btn--ghost realm-btn--sm" disabled={busy} onClick={() => void marketBuyGrain()}>
                  Buy 1 grain
                </button>
                <button type="button" className="realm-btn realm-btn--ghost realm-btn--sm" onClick={() => setCommandOpen((o) => !o)}>
                  {commandOpen ? "Hide command" : "Command"}
                </button>
                <button type="button" className="realm-btn realm-btn--ghost realm-btn--sm" onClick={replayBriefing}>
                  Briefing
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
                <motion.div
                  key={world.tick}
                  className="realm-tick-ripple"
                  initial={{ opacity: 0.45 }}
                  animate={{ opacity: 0 }}
                  transition={{ duration: 0.55, ease: "easeOut" }}
                />
                <div className="realm-map-toolbar" role="toolbar" aria-label="Map controls">
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
                        <RealmMapMeshSvg
                          mesh={mesh}
                          plots={world.plots}
                          selectedPlotId={selectedPlotId}
                          buildsByPlot={buildsByPlot}
                          busy={busy}
                          mapNavSuppress={mapNavSuppress}
                          onPlotClick={onPlotClick}
                        />
                      </>
                    ) : null}
                  </div>
                </div>
              </div>
              <p className="realm-map-footnote">
                Drag to pan · wheel zoom · Style: terrain / satellite / political. Regions are jittered from a large world map (engine still uses plot
                tiles). Empty = <strong>claim</strong> · yours again = <strong>survey</strong> · surveyed = <strong>industry</strong> · gold = selected
              </p>
            </div>

            <AnimatePresence>
              {commandOpen ? (
                <motion.aside
                  key="cmd"
                  className="realm-panel-pop"
                  role="complementary"
                  aria-label="Command panel"
                  initial={{ opacity: 0, x: 48 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 40 }}
                  transition={{ type: "spring", stiffness: 420, damping: 32 }}
                >
                  <div className="realm-panel-pop__head">
                    <span className="realm-panel-pop__title" aria-live="polite">
                      {panelHeadline(tab)}
                    </span>
                    <button type="button" className="realm-panel-pop__close" onClick={() => setCommandOpen(false)} aria-label="Hide command panel">
                      ×
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
                  style={{ flex: 1, minHeight: 0 }}
                >
                  {tab === "world" ? (
                    <>
                      <SectionTitle>Selected plot</SectionTitle>
                      {selectedPlot ? (
                        <div className="realm-help" style={{ marginBottom: 12 }}>
                          <strong style={{ color: "var(--realm-text)" }}>{selectedPlot.id}</strong> · {selectedPlot.terrain}{" "}
                          · {selectedPlot.surveyed ? "surveyed" : "not surveyed"}
                          {selectedPlot.owner === "player" && selectedPlot.surveyed && selectedPlot.subsurface ? (
                            <span style={{ display: "block", marginTop: 6, fontSize: 11 }}>
                              Subsurface grades (ore/clay/coal):{" "}
                              {Object.entries(selectedPlot.subsurface)
                                .map(([k, v]) => `${k.replace(/_grade/, "")} ${(v as number).toFixed(2)}`)
                                .join(" · ")}
                            </span>
                          ) : null}
                        </div>
                      ) : (
                        <p className="realm-help">Select a plot you own (surveyed) to manage production.</p>
                      )}

                      {selectedPlot?.owner === "player" && selectedPlot.surveyed ? (
                        <>
                          <SectionTitle>Recipes</SectionTitle>
                          <ul style={{ listStyle: "none", padding: 0, margin: "0 0 8px" }}>
                            {(world.recipes ?? []).map((r) => (
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
                          <SectionTitle>Build on this plot</SectionTitle>
                          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                            {(world.building_catalog ?? []).map((b) => (
                              <li key={b.id} style={{ marginBottom: 6 }}>
                                <button
                                  type="button"
                                  className="realm-list-btn"
                                  disabled={busy}
                                  onClick={() => void buildOnSelectedPlot(b.id)}
                                >
                                  {b.label} · ${(b.cost_cents / 100).toFixed(2)}
                                </button>
                              </li>
                            ))}
                          </ul>
                          {buildingsHere.length > 0 ? (
                            <>
                              <SectionTitle>Built here</SectionTitle>
                              <ul className="realm-help" style={{ marginTop: 4 }}>
                                {buildingsHere.map((x, i) => (
                                  <li key={`${x.building_id}-${i}`}>
                                    {x.label} ({x.building_id})
                                  </li>
                                ))}
                              </ul>
                            </>
                          ) : null}
                        </>
                      ) : null}

                      <SectionTitle>Active production</SectionTitle>
                      {(world.active_production ?? []).length === 0 ? (
                        <p className="realm-help">None running.</p>
                      ) : (
                        <ul className="realm-help" style={{ paddingLeft: 18, margin: 0 }}>
                          {(world.active_production ?? []).map((a) => (
                            <li key={a.run_id}>
                              {a.plot_id} · {a.recipe_id} · {a.ticks_remaining} ticks left
                            </li>
                          ))}
                        </ul>
                      )}

                      <SectionTitle>Inventory (player)</SectionTitle>
                      <table className="realm-table">
                        <thead>
                          <tr>
                            <th>Material</th>
                            <th style={{ textAlign: "right" }}>Qty</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(playerInv)
                            .sort(([a], [b]) => a.localeCompare(b))
                            .map(([k, v]) => (
                              <tr key={k}>
                                <td>{k}</td>
                                <td style={{ textAlign: "right", fontFamily: "var(--realm-mono)" }}>{v}</td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </>
                  ) : null}

                  {tab === "market" ? (
                    <>
                      <SectionTitle>Asks (sell side)</SectionTitle>
                      {(world.market_asks ?? []).length === 0 ? (
                        <p className="realm-help">No open asks.</p>
                      ) : (
                        <table className="realm-table">
                          <thead>
                            <tr>
                              <th>Mat</th>
                              <th style={{ textAlign: "right" }}>Qty</th>
                              <th style={{ textAlign: "right" }}>¢/u</th>
                              <th>Seller</th>
                              <th style={{ textAlign: "right" }}> </th>
                            </tr>
                          </thead>
                          <tbody>
                            {(world.market_asks ?? []).map((a) => (
                              <tr key={a.order_id}>
                                <td>{a.material}</td>
                                <td style={{ textAlign: "right" }}>{a.qty}</td>
                                <td style={{ textAlign: "right" }}>{a.price_per_unit_cents}</td>
                                <td>{a.party}</td>
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
                      <SectionTitle>Bids (buy side)</SectionTitle>
                      {(world.market_bids ?? []).length === 0 ? (
                        <p className="realm-help">No open bids.</p>
                      ) : (
                        <table className="realm-table">
                          <thead>
                            <tr>
                              <th>Mat</th>
                              <th style={{ textAlign: "right" }}>Qty</th>
                              <th style={{ textAlign: "right" }}>Max ¢/u</th>
                              <th>Buyer</th>
                              <th style={{ textAlign: "right" }}> </th>
                            </tr>
                          </thead>
                          <tbody>
                            {(world.market_bids ?? []).map((b) => (
                              <tr key={b.order_id}>
                                <td>{b.material}</td>
                                <td style={{ textAlign: "right" }}>{b.qty}</td>
                                <td style={{ textAlign: "right" }}>{b.max_price_per_unit_cents}</td>
                                <td>{b.party}</td>
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
                      <SectionTitle>Market depth</SectionTitle>
                      <div className="realm-chart-card">
                        <MarketHistoryChart history={world.market_history ?? []} />
                      </div>
                      <SectionTitle>Place limit bid (player)</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Locks up to <code>qty × max ¢/u</code> in market escrow; lifts cheaper asks immediately at their price.
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                        <label className="realm-label">
                          material
                          <input
                            className="realm-input"
                            value={bidMaterial}
                            onChange={(e) => setBidMaterial(e.target.value)}
                            style={{ width: 120 }}
                          />
                        </label>
                        <label className="realm-label">
                          qty
                          <input
                            className="realm-input"
                            value={bidQty}
                            onChange={(e) => setBidQty(e.target.value)}
                            style={{ width: 56 }}
                          />
                        </label>
                        <label className="realm-label">
                          max ¢/unit
                          <input
                            className="realm-input"
                            value={bidMaxCents}
                            onChange={(e) => setBidMaxCents(e.target.value)}
                            style={{ width: 64 }}
                          />
                        </label>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void placeBuyOrder()}>
                          Place bid
                        </button>
                      </div>
                      <SectionTitle>List for sale (player)</SectionTitle>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                        <label className="realm-label">
                          material
                          <input
                            className="realm-input"
                            value={sellMaterial}
                            onChange={(e) => setSellMaterial(e.target.value)}
                            style={{ width: 120 }}
                          />
                        </label>
                        <label className="realm-label">
                          qty
                          <input
                            className="realm-input"
                            value={sellQty}
                            onChange={(e) => setSellQty(e.target.value)}
                            style={{ width: 56 }}
                          />
                        </label>
                        <label className="realm-label">
                          ¢/unit
                          <input
                            className="realm-input"
                            value={sellPriceCents}
                            onChange={(e) => setSellPriceCents(e.target.value)}
                            style={{ width: 64 }}
                          />
                        </label>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void placeSellOrder()}>
                          Place ask
                        </button>
                      </div>
                      <SectionTitle>Sell into bids (player)</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Walks highest bids; you must hold inventory. Payment comes from bid escrow at each bid&apos;s limit.
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                        <label className="realm-label">
                          material
                          <input
                            className="realm-input"
                            value={sellFillMaterial}
                            onChange={(e) => setSellFillMaterial(e.target.value)}
                            style={{ width: 120 }}
                          />
                        </label>
                        <label className="realm-label">
                          max qty
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
                      <SectionTitle>P2P trade (atomic)</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Direct deal: counterparty pays (or receives) <code>total_price_cents</code> for the whole lot — no order book. Example: sell grain to{" "}
                        <code>t1_consumer</code> from bootstrap.
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                        <label className="realm-label">
                          you are
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
                          counterparty id
                          <input
                            className="realm-input"
                            value={p2pParty}
                            onChange={(e) => setP2pParty(e.target.value)}
                            style={{ width: 180 }}
                          />
                        </label>
                        <label className="realm-label">
                          material
                          <input
                            className="realm-input"
                            value={p2pMaterial}
                            onChange={(e) => setP2pMaterial(e.target.value)}
                            style={{ width: 120 }}
                          />
                        </label>
                        <label className="realm-label">
                          qty
                          <input
                            className="realm-input"
                            value={p2pQty}
                            onChange={(e) => setP2pQty(e.target.value)}
                            style={{ width: 48 }}
                          />
                        </label>
                        <label className="realm-label">
                          total (¢)
                          <input
                            className="realm-input"
                            value={p2pTotalCents}
                            onChange={(e) => setP2pTotalCents(e.target.value)}
                            style={{ width: 72 }}
                          />
                        </label>
                        <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void runP2pTrade()}>
                          Execute P2P
                        </button>
                      </div>
                    </>
                  ) : null}

                  {tab === "logistics" ? (
                    <>
                      <SectionTitle>In transit</SectionTitle>
                      {(world.in_transit ?? []).length === 0 ? (
                        <p className="realm-help">Nothing in flight.</p>
                      ) : (
                        <ul className="realm-help" style={{ paddingLeft: 18, margin: 0 }}>
                          {(world.in_transit ?? []).map((s) => (
                            <li key={s.id}>
                              {s.material} ×{s.qty} → {s.dest_plot_id} · arrive tick {s.arrive_tick}
                            </li>
                          ))}
                        </ul>
                      )}
                      <SectionTitle>Ship goods</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Own both plots. Fee debits cash; goods arrive after distance-based ticks.
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                        <label className="realm-label">
                          from
                          <input className="realm-input" value={shipFrom} onChange={(e) => setShipFrom(e.target.value)} />
                        </label>
                        <label className="realm-label">
                          to
                          <input className="realm-input" value={shipTo} onChange={(e) => setShipTo(e.target.value)} />
                        </label>
                        <label className="realm-label">
                          material
                          <input
                            className="realm-input"
                            value={shipMaterial}
                            onChange={(e) => setShipMaterial(e.target.value)}
                            style={{ width: 100 }}
                          />
                        </label>
                        <label className="realm-label">
                          qty
                          <input className="realm-input" value={shipQty} onChange={(e) => setShipQty(e.target.value)} style={{ width: 48 }} />
                        </label>
                        <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void shipGoods()}>
                          Dispatch
                        </button>
                      </div>
                    </>
                  ) : null}

                  {tab === "contracts" ? (
                    <>
                      <SectionTitle>Hire (employment)</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Signing bonus + employment record. Production runs route{" "}
                        <strong>40%</strong> of recipe labor cash to hired parties (split evenly); the rest goes to system
                        reserve as before.
                      </p>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Hires so far: {(world.stub_hires ?? []).length}
                      </p>
                      <ul style={{ listStyle: "none", padding: 0, margin: "0 0 16px" }}>
                        {(world.hire_catalog ?? []).map((row) => (
                          <li key={row.party} style={{ marginBottom: 6 }}>
                            <button
                              type="button"
                              className="realm-list-btn"
                              disabled={busy}
                              onClick={() => void hireNpc(row.party, row.suggested_signing_cents)}
                            >
                              {row.role} — ${(row.suggested_signing_cents / 100).toFixed(2)} bonus
                            </button>
                          </li>
                        ))}
                      </ul>

                      <SectionTitle>Supply contract (deliver by tick)</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        You are the <strong>supplier</strong>. Buyer must <strong>accept</strong>, then you <strong>fulfill</strong> (goods +
                        payment) before the deadline tick or the supplier is marked <strong>breached</strong>.
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end", marginBottom: 14 }}>
                        <label className="realm-label">
                          buyer party
                          <input
                            className="realm-input"
                            value={supplyBuyer}
                            onChange={(e) => setSupplyBuyer(e.target.value)}
                            style={{ width: 160 }}
                          />
                        </label>
                        <label className="realm-label">
                          material
                          <input
                            className="realm-input"
                            value={supplyMaterial}
                            onChange={(e) => setSupplyMaterial(e.target.value)}
                            style={{ width: 100 }}
                          />
                        </label>
                        <label className="realm-label">
                          qty
                          <input
                            className="realm-input"
                            value={supplyQty}
                            onChange={(e) => setSupplyQty(e.target.value)}
                            style={{ width: 48 }}
                          />
                        </label>
                        <label className="realm-label">
                          total ¢
                          <input
                            className="realm-input"
                            value={supplyTotalCents}
                            onChange={(e) => setSupplyTotalCents(e.target.value)}
                            style={{ width: 64 }}
                          />
                        </label>
                        <label className="realm-label">
                          due in ticks
                          <input
                            className="realm-input"
                            value={supplyDueTicks}
                            onChange={(e) => setSupplyDueTicks(e.target.value)}
                            style={{ width: 72 }}
                          />
                        </label>
                        <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void proposeSupplyContract()}>
                          Propose supply
                        </button>
                      </div>

                      {supplyContractRows.length === 0 ? (
                        <p className="realm-help">No supply contracts yet.</p>
                      ) : (
                        <table className="realm-table" style={{ marginBottom: 16 }}>
                          <thead>
                            <tr>
                              <th>Id</th>
                              <th>Status</th>
                              <th>Buyer</th>
                              <th>Mat</th>
                              <th style={{ textAlign: "right" }}>Qty</th>
                              <th style={{ textAlign: "right" }}>¢</th>
                              <th style={{ textAlign: "right" }}>Due≤t</th>
                              <th style={{ textAlign: "right" }}> </th>
                            </tr>
                          </thead>
                          <tbody>
                            {supplyContractRows.map((c) => (
                              <tr key={c.id}>
                                <td style={{ fontFamily: "var(--realm-mono)", fontSize: 12 }}>{c.id}</td>
                                <td>{c.status}</td>
                                <td>{c.buyer}</td>
                                <td>{c.material}</td>
                                <td style={{ textAlign: "right" }}>{c.qty}</td>
                                <td style={{ textAlign: "right" }}>{c.total_price_cents}</td>
                                <td style={{ textAlign: "right" }}>{c.deliver_by_tick ?? "—"}</td>
                                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                                  {c.status === "proposed" && c.buyer ? (
                                    <button
                                      type="button"
                                      className="realm-btn realm-btn--ghost realm-btn--sm"
                                      disabled={busy}
                                      onClick={() => void acceptSupplyContractRow(c.id, String(c.buyer))}
                                    >
                                      Accept (buyer)
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

                      <SectionTitle>Generic memo contract (dev)</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 8 }}>
                        Last memo id: {lastContractId ?? "—"} — honor increments both parties&apos; <code>honored</code> (no goods).
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

                  {tab === "codex" ? (
                    <div className="realm-codex-grid">
                      <p className="realm-help" style={{ marginTop: 0 }}>
                        Atlas tracks what the engine already does vs placeholder systems vs backlog. Add rows in{" "}
                        <code>frontierFeatures.ts</code>; wire new screens via <code>frontierMenu.ts</code> + panel
                        blocks in <code>page.tsx</code>.
                      </p>
                      {(
                        [
                          ["live", "In this build"],
                          ["stub", "Stubs (thin vertical slice)"],
                          ["planned", "Coming later"],
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
                  ) : null}

                  {tab === "log" ? (
                    <>
                      <SectionTitle>Action log</SectionTitle>
                      <div className="realm-log">
                        {eventLogReversed.length === 0 ? (
                          <span className="realm-help">No events yet.</span>
                        ) : (
                          eventLogReversed.map((e, i) => (
                            <div key={i} className="realm-log-line">
                              <span style={{ opacity: 0.5 }}>t{e.tick}</span>{" "}
                              <span style={{ opacity: 0.65 }}>[{e.kind}]</span> {e.message}
                            </div>
                          ))
                        )}
                      </div>
                      <SectionTitle>Persistence</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Writes <code>saves/realm_dev.sqlite</code> at repo root (path resolved from the engine package).
                      </p>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void persistenceSave()}>
                          Save snapshot
                        </button>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void persistenceLoad()}>
                          Load snapshot
                        </button>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void devResetWorld()}>
                          Dev: reset world
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
              <button type="button" className="realm-panel-fab" onClick={() => setCommandOpen(true)}>
                Command
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
    </main>
  );
}
