"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";

import { MarketHistoryChart, type MarketHistorySnap } from "./MarketHistoryChart";
import { OnboardingModal } from "./OnboardingModal";

const ONBOARD_KEY = "realm_frontier_onboard_v2";

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

type TabId = "world" | "market" | "logistics" | "contracts" | "log";

const TABS: { id: TabId; label: string }[] = [
  { id: "world", label: "Plot" },
  { id: "market", label: "Market" },
  { id: "logistics", label: "Logistics" },
  { id: "contracts", label: "Contracts" },
  { id: "log", label: "Log" },
];

const TERRAIN_COLOR: Record<string, string> = {
  plains: "#5a8f4a",
  forest: "#1e4a22",
  mountain: "#5a5d6b",
  desert: "#c9a85c",
  tundra: "#8fb8d4",
  swamp: "#2d4a32",
  water_shallow: "#2d6ba8",
  water_deep: "#0f2847",
};

function terrainColor(t: string): string {
  return TERRAIN_COLOR[t] ?? "#3d4450";
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
      if (typeof window !== "undefined" && !localStorage.getItem(ONBOARD_KEY)) {
        setOnboardingOpen(true);
      }
    } catch {
      setOnboardingOpen(true);
    }
  }, []);

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
    const cellPx = Math.min(34, Math.max(17, Math.floor(560 / Math.max(w, 1))));
    return { w, h, cells, cellPx };
  }, [world]);

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
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function claim(plotId: string) {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`/api/engine/plots/${encodeURIComponent(plotId)}/claim`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function survey(plotId: string) {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`/api/engine/plots/${encodeURIComponent(plotId)}/survey`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function produce(plotId: string, recipeId: string) {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ recipe_id: recipeId });
      const r = await fetch(`/api/engine/plots/${encodeURIComponent(plotId)}/produce?${q.toString()}`, {
        method: "POST",
      });
      if (!r.ok) throw new Error(await r.text());
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
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ building_id: buildingId, party: "player" });
      const r = await fetch(
        `/api/engine/plots/${encodeURIComponent(selectedPlotId)}/build?${q.toString()}`,
        { method: "POST" },
      );
      if (!r.ok) throw new Error(await r.text());
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
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function onPlotClick(p: PlotDto) {
    if (!p.owner) {
      void claim(p.id);
      setSelectedPlotId(p.id);
      setTab("world");
      return;
    }
    if (p.owner === "player") {
      if (!p.surveyed) {
        void survey(p.id);
        setTab("world");
        return;
      }
      setSelectedPlotId(p.id);
      setTab("world");
    }
  }

  function replayBriefing() {
    try {
      localStorage.removeItem(ONBOARD_KEY);
    } catch {
      /* ignore */
    }
    setOnboardingOpen(true);
  }

  return (
    <main className="realm-shell">
      <OnboardingModal open={onboardingOpen} onComplete={() => setOnboardingOpen(false)} />

      {error ? (
        <div className="realm-error" role="alert">
          {error}
        </div>
      ) : null}

      {world ? (
        <>
          <header className="realm-hud">
            <div className="realm-brand">
              <div className="realm-brand__title">Realm</div>
              <div className="realm-brand__sub">Frontier · solo prototype</div>
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
              <button type="button" className="realm-btn realm-btn--ghost realm-btn--sm" onClick={replayBriefing}>
                Briefing
              </button>
            </div>
          </header>

          <div className="realm-deck">
            <div>
              <div className="realm-map-frame">
                <div
                  className="realm-map-grid"
                  style={{ gridTemplateColumns: `repeat(${grid.w}, ${grid.cellPx}px)` }}
                >
                  {grid.cells.flatMap((row, y) =>
                    row.map((p, x) => {
                      const sel = p && selectedPlotId === p.id;
                      const mine = p?.owner === "player";
                      const cls = ["realm-map-cell", sel ? "realm-map-cell--sel" : "", mine ? "realm-map-cell--mine" : ""]
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
                            background: p ? terrainColor(p.terrain) : "#000",
                          }}
                        />
                      );
                    }),
                  )}
                </div>
                <p className="realm-map-hint">
                  Click empty land to <strong>claim</strong>. Your plot: first click <strong>surveys</strong> ($500),
                  then select to <strong>produce</strong> or <strong>build</strong>. Orange ring = selected.
                </p>
                <div className="realm-cta-row">
                  <motion.button
                    type="button"
                    className="realm-btn realm-btn--primary"
                    disabled={busy}
                    onClick={() => void tick()}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    Advance tick
                  </motion.button>
                  <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void marketBuyGrain()}>
                    Buy 1 grain
                  </button>
                </div>
              </div>
            </div>

            <div className="realm-panel-wrap">
              <nav className="realm-tabs" aria-label="Command panels">
                {TABS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`realm-tab${tab === t.id ? " realm-tab--active" : ""}`}
                    onClick={() => setTab(t.id)}
                  >
                    {t.label}
                  </button>
                ))}
              </nav>

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
            </div>
          </div>
        </>
      ) : (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="realm-help"
          style={{ fontSize: 15, padding: 24, textAlign: "center" }}
        >
          Loading world…
        </motion.p>
      )}
    </main>
  );
}
