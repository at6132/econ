"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FRONTIER_FEATURES } from "./frontierFeatures";
import { FRONTIER_ONBOARD_STORAGE_KEY } from "./frontierConstants";
import { FRONTIER_MENU, type TabId } from "./frontierMenu";
import { FrontierTopNav } from "./FrontierTopNav";
import type { MapFxEvent } from "./mapFxTypes";
import { MarketHistoryChart, type MarketHistorySnap } from "./MarketHistoryChart";
import { OnboardingModal } from "./OnboardingModal";
import { RealmMapFxOverlay } from "./RealmMapFxOverlay";

const MAP_CELL_GAP = 2;

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
  reputation?: Record<string, { honored: number; breached: number }>;
  contracts?: Record<string, unknown>[];
  event_log?: EventLogEntryDto[];
  building_catalog?: BuildingCatalogDto[];
  plot_buildings?: PlotBuildingDto[];
  stub_hires?: StubHireDto[];
  market_history?: MarketHistorySnap[];
  hire_catalog?: HireCatalogRow[];
};

const KNOWN_TERRAIN = new Set([
  "plains",
  "forest",
  "mountain",
  "desert",
  "tundra",
  "swamp",
  "water_shallow",
  "water_deep",
]);

function terrainCellClass(terrain: string): string {
  if (!KNOWN_TERRAIN.has(terrain)) return "realm-map-cell--t-unknown";
  return `realm-map-cell--t-${terrain}`;
}

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
  const [lastContractId, setLastContractId] = useState<string | null>(null);
  const [commandOpen, setCommandOpen] = useState(true);
  const mapViewportRef = useRef<HTMLDivElement>(null);
  const [viewportPx, setViewportPx] = useState({ w: 720, h: 520 });
  const [mapFx, setMapFx] = useState<MapFxEvent[]>([]);
  const mapFxSeq = useRef(0);

  const queueFx = useCallback((ev: Omit<MapFxEvent, "id">) => {
    const id = ++mapFxSeq.current;
    setMapFx((prev) => [...prev, { id, ...ev }]);
    window.setTimeout(() => {
      setMapFx((prev) => prev.filter((e) => e.id !== id));
    }, 1700);
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
    if (!world?.plots.length) return { w: 0, h: 0, cells: [] as PlotDto[][], cellPx: 36 };
    const w = Math.max(...world.plots.map((p) => p.x)) + 1;
    const h = Math.max(...world.plots.map((p) => p.y)) + 1;
    const cells: PlotDto[][] = Array.from({ length: h }, () =>
      Array.from({ length: w }, () => null as unknown as PlotDto),
    );
    for (const p of world.plots) {
      cells[p.y][p.x] = p;
    }
    const gap = MAP_CELL_GAP;
    const pad = 20;
    const innerW = Math.max(60, viewportPx.w - pad * 2);
    const innerH = Math.max(60, viewportPx.h - pad * 2);
    const cw = (innerW - gap * Math.max(0, w - 1)) / Math.max(1, w);
    const ch = (innerH - gap * Math.max(0, h - 1)) / Math.max(1, h);
    const cellPx = Math.floor(Math.max(14, Math.min(88, Math.min(cw, ch))));
    return { w, h, cells, cellPx };
  }, [world, viewportPx]);

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

  async function proposeContract() {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ party_a: "player", party_b: "npc_grain_vendor", kind: "supply" });
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

  async function honorContract() {
    if (!lastContractId) {
      setError("Propose a contract first.");
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
              <div ref={mapViewportRef} className="realm-map-viewport">
                <div className="realm-map-frame realm-map-frame--hero">
                  <motion.div
                    key={world.tick}
                    className="realm-tick-ripple"
                    initial={{ opacity: 0.45 }}
                    animate={{ opacity: 0 }}
                    transition={{ duration: 0.55, ease: "easeOut" }}
                  />
                  <div className="realm-map-god-wrap">
                    <div className="realm-map-grid-stack">
                      <RealmMapFxOverlay
                        events={mapFx}
                        cellPx={grid.cellPx}
                        gap={MAP_CELL_GAP}
                        gridW={grid.w}
                        gridH={grid.h}
                        pad={4}
                      />
                      <div
                        className="realm-map-grid"
                        style={{
                          gridTemplateColumns: `repeat(${grid.w}, ${grid.cellPx}px)`,
                          gap: MAP_CELL_GAP,
                        }}
                      >
                        {grid.cells.flatMap((row, y) =>
                          row.map((p, x) => {
                            const sel = p && selectedPlotId === p.id;
                            const mine = p?.owner === "player";
                            const terrainCls = p ? terrainCellClass(p.terrain) : "realm-map-cell--void";
                            const nBuild = p ? (buildsByPlot.get(p.id) ?? 0) : 0;
                            const cls = [
                              "realm-map-cell",
                              terrainCls,
                              sel ? "realm-map-cell--sel" : "",
                              mine ? "realm-map-cell--mine" : "",
                            ]
                              .filter(Boolean)
                              .join(" ");
                            return (
                              <motion.button
                                key={p?.id ?? `cell-${x}-${y}`}
                                type="button"
                                className={cls}
                                title={`${p?.id ?? ""} · ${p?.terrain ?? ""} · owner ${p?.owner ?? "none"} · surveyed ${p?.surveyed ? "yes" : "no"}`}
                                disabled={busy || !p}
                                onClick={() => p && onPlotClick(p)}
                                layout
                                whileTap={{ scale: 0.94 }}
                                style={{
                                  width: grid.cellPx,
                                  height: grid.cellPx,
                                }}
                              >
                                {nBuild > 0 ? (
                                  <span className="realm-map-cell__build" aria-hidden>
                                    ▣{nBuild > 1 ? nBuild : ""}
                                  </span>
                                ) : null}
                              </motion.button>
                            );
                          }),
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <p className="realm-map-footnote">
                Empty = <strong>claim</strong> · yours again = <strong>survey</strong> · surveyed = <strong>industry</strong> · gold = selected
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
                      <SectionTitle>Order book</SectionTitle>
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
                            </tr>
                          </thead>
                          <tbody>
                            {(world.market_asks ?? []).map((a) => (
                              <tr key={a.order_id}>
                                <td>{a.material}</td>
                                <td style={{ textAlign: "right" }}>{a.qty}</td>
                                <td style={{ textAlign: "right" }}>{a.price_per_unit_cents}</td>
                                <td>{a.party}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                      <SectionTitle>Market depth</SectionTitle>
                      <div className="realm-chart-card">
                        <MarketHistoryChart history={world.market_history ?? []} />
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
                      <SectionTitle>Hire (employment stub)</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 10 }}>
                        Signing bonus creates an <code>employment</code> contract. Hires so far: {(world.stub_hires ?? []).length}
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
                      <SectionTitle>Supply contract (stub)</SectionTitle>
                      <p className="realm-help" style={{ marginBottom: 8 }}>
                        Last id: {lastContractId ?? "—"} · open supply:{" "}
                        {(world.contracts ?? []).filter((c) => (c as { status?: string; kind?: string }).status === "open" && (c as { kind?: string }).kind !== "employment").length}
                      </p>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void proposeContract()}>
                          Propose with vendor
                        </button>
                        <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void honorContract()}>
                          Honor last
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
