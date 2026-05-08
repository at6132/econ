"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { MarketHistoryChart, type MarketHistorySnap } from "./MarketHistoryChart";

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

const TERRAIN_COLOR: Record<string, string> = {
  plains: "#6b8e4e",
  forest: "#2d5a27",
  mountain: "#6d6d7a",
  desert: "#c4a35a",
  tundra: "#a8c4d4",
  swamp: "#3d5c40",
  water_shallow: "#3a6ea5",
  water_deep: "#1e3a5f",
};

function terrainColor(t: string): string {
  return TERRAIN_COLOR[t] ?? "#444";
}

export default function HomePage() {
  const [world, setWorld] = useState<WorldDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
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
    const cellPx = Math.min(36, Math.max(18, Math.floor(520 / Math.max(w, 1))));
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
      const r = await fetch(`/api/engine/plots/${encodeURIComponent(plotId)}/claim`, {
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

  async function survey(plotId: string) {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`/api/engine/plots/${encodeURIComponent(plotId)}/survey`, {
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

  async function produce(plotId: string, recipeId: string) {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ recipe_id: recipeId });
      const r = await fetch(
        `/api/engine/plots/${encodeURIComponent(plotId)}/produce?${q.toString()}`,
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
      return;
    }
    if (p.owner === "player") {
      if (!p.surveyed) {
        void survey(p.id);
        return;
      }
      setSelectedPlotId(p.id);
    }
  }

  const playerCash =
    world?.balances_cents["cash:player"] != null
      ? (world.balances_cents["cash:player"] / 100).toFixed(2)
      : "—";

  return (
    <main style={{ padding: 16, maxWidth: 1100, margin: "0 auto" }}>
      <header style={{ marginBottom: 16 }}>
        <h1 style={{ margin: "0 0 8px", fontSize: 22 }}>Realm — Frontier (Phase 1)</h1>
        <p style={{ margin: 0, opacity: 0.85, fontSize: 14 }}>
          Engine on port 8000 · <code>npm run dev</code> here · claim → survey → start recipe →
          advance ticks until outputs land.
        </p>
      </header>

      {error ? (
        <p style={{ color: "#f85149", marginBottom: 12 }} role="alert">
          {error}
        </p>
      ) : null}

      {world ? (
        <section style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 13, marginBottom: 8, opacity: 0.9 }}>
              Tick <strong>{world.tick}</strong> · Seed <strong>{world.seed}</strong> · Cash{" "}
              <strong>${playerCash}</strong>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: `repeat(${grid.w}, ${grid.cellPx}px)`,
                gap: 2,
                border: "1px solid #30363d",
                padding: 4,
                background: "#161b22",
                maxWidth: "100%",
                overflowX: "auto",
              }}
            >
              {grid.cells.flatMap((row, y) =>
                row.map((p, x) => {
                  const sel = p && selectedPlotId === p.id;
                  return (
                    <button
                      key={p?.id ?? `cell-${x}-${y}`}
                      type="button"
                      title={`${p?.id ?? ""} ${p?.terrain ?? ""} owner=${p?.owner ?? "none"} surveyed=${p?.surveyed}`}
                      disabled={busy || !p}
                      onClick={() => p && onPlotClick(p)}
                      style={{
                        width: grid.cellPx,
                        height: grid.cellPx,
                        border: sel ? "2px solid #f0883e" : p?.owner ? "2px solid #58a6ff" : "1px solid #21262d",
                        background: p ? terrainColor(p.terrain) : "#000",
                        cursor: busy ? "wait" : "pointer",
                        padding: 0,
                        outline: sel ? "1px solid #f0883e" : undefined,
                      }}
                    />
                  );
                }),
              )}
            </div>
            <p style={{ fontSize: 12, opacity: 0.75, marginTop: 8, maxWidth: 440 }}>
              Empty cell: claim. Your unsurveyed plot: survey ($500). Your surveyed plot: select
              (orange). Then start a recipe in the panel.
            </p>
            <button type="button" disabled={busy} onClick={() => void tick()} style={{ marginTop: 8 }}>
              Advance tick
            </button>
          </div>

          <aside style={{ flex: 1, minWidth: 280, fontSize: 13 }}>
            <h2 style={{ fontSize: 15, marginTop: 0 }}>Plot & production</h2>
            {selectedPlot ? (
              <div style={{ marginBottom: 12 }}>
                <div>
                  <strong>{selectedPlot.id}</strong> · {selectedPlot.terrain}{" "}
                  {selectedPlot.surveyed ? "(surveyed)" : "(not surveyed)"}
                </div>
                {selectedPlot.owner === "player" && selectedPlot.surveyed ? (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontWeight: 600, marginBottom: 6 }}>Recipes</div>
                    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {(world.recipes ?? []).map((r) => (
                        <li key={r.id} style={{ marginBottom: 6 }}>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void produce(selectedPlot.id, r.id)}
                            style={{ width: "100%", textAlign: "left" }}
                          >
                            {r.display_name} ({r.duration_ticks} ticks, labor $
                            {(r.labor_cents / 100).toFixed(2)})
                          </button>
                        </li>
                      ))}
                    </ul>
                    <div style={{ fontWeight: 600, margin: "12px 0 6px" }}>Build (stub, this plot)</div>
                    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {(world.building_catalog ?? []).map((b) => (
                        <li key={b.id} style={{ marginBottom: 6 }}>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void buildOnSelectedPlot(b.id)}
                            style={{ width: "100%", textAlign: "left" }}
                          >
                            {b.label} (${(b.cost_cents / 100).toFixed(2)})
                          </button>
                        </li>
                      ))}
                    </ul>
                    {buildingsHere.length > 0 ? (
                      <div style={{ marginTop: 8, fontSize: 12, opacity: 0.9 }}>
                        <div style={{ fontWeight: 600 }}>Built here</div>
                        <ul style={{ paddingLeft: 18, margin: "4px 0 0" }}>
                          {buildingsHere.map((x, i) => (
                            <li key={`${x.building_id}-${i}`}>
                              {x.label} ({x.building_id})
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : (
              <p style={{ opacity: 0.8 }}>Select a surveyed plot you own.</p>
            )}

            <h3 style={{ fontSize: 14, marginBottom: 6 }}>Active production</h3>
            {(world.active_production ?? []).length === 0 ? (
              <p style={{ opacity: 0.7 }}>None</p>
            ) : (
              <ul style={{ paddingLeft: 18, margin: 0 }}>
                {(world.active_production ?? []).map((a) => (
                  <li key={a.run_id}>
                    {a.plot_id} · {a.recipe_id} · {a.ticks_remaining} ticks left
                  </li>
                ))}
              </ul>
            )}

            <h3 style={{ fontSize: 14, marginTop: 16, marginBottom: 6 }}>Inventory (player)</h3>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #30363d" }}>Material</th>
                  <th style={{ textAlign: "right", borderBottom: "1px solid #30363d" }}>Qty</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(playerInv)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ padding: "4px 0" }}>{k}</td>
                      <td style={{ textAlign: "right" }}>{v}</td>
                    </tr>
                  ))}
              </tbody>
            </table>

            <h3 style={{ fontSize: 14, marginTop: 16, marginBottom: 6 }}>Hire (employment stub)</h3>
            <p style={{ margin: "0 0 8px", fontSize: 12, opacity: 0.75 }}>
              Signing bonus creates an <code>employment</code> contract row (no output yet). Hires:{" "}
              {(world.stub_hires ?? []).length}
            </p>
            <ul style={{ listStyle: "none", padding: 0, margin: "0 0 8px" }}>
              {(world.hire_catalog ?? []).map((row) => (
                <li key={row.party} style={{ marginBottom: 6 }}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void hireNpc(row.party, row.suggested_signing_cents)}
                    style={{ width: "100%", textAlign: "left", fontSize: 12 }}
                  >
                    {row.role} — ${(row.suggested_signing_cents / 100).toFixed(2)} bonus
                  </button>
                </li>
              ))}
            </ul>

            <h3 style={{ fontSize: 14, marginTop: 16, marginBottom: 6 }}>Order book (limit asks)</h3>
            {(world.market_asks ?? []).length === 0 ? (
              <p style={{ opacity: 0.7 }}>No open asks</p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, marginBottom: 8 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #30363d" }}>Mat</th>
                    <th style={{ textAlign: "right", borderBottom: "1px solid #30363d" }}>Qty</th>
                    <th style={{ textAlign: "right", borderBottom: "1px solid #30363d" }}>¢/u</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #30363d" }}>Seller</th>
                  </tr>
                </thead>
                <tbody>
                  {(world.market_asks ?? []).map((a) => (
                    <tr key={a.order_id}>
                      <td style={{ padding: "4px 0" }}>{a.material}</td>
                      <td style={{ textAlign: "right" }}>{a.qty}</td>
                      <td style={{ textAlign: "right" }}>{a.price_per_unit_cents}</td>
                      <td style={{ paddingLeft: 6 }}>{a.party}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button type="button" disabled={busy} onClick={() => void marketBuyGrain()} style={{ marginRight: 8 }}>
              Buy 1 grain (player)
            </button>

            <h3 style={{ fontSize: 14, marginTop: 14, marginBottom: 6 }}>Market depth (best ask ¢/u)</h3>
            <div style={{ width: "100%", maxWidth: 640, marginBottom: 10 }}>
              <MarketHistoryChart history={world.market_history ?? []} />
            </div>

            <h3 style={{ fontSize: 14, marginTop: 14, marginBottom: 6 }}>List for sale (player)</h3>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 8 }}>
              <label style={{ display: "flex", flexDirection: "column", fontSize: 11, gap: 2 }}>
                material
                <input
                  value={sellMaterial}
                  onChange={(e) => setSellMaterial(e.target.value)}
                  style={{ width: 100, padding: 4 }}
                />
              </label>
              <label style={{ display: "flex", flexDirection: "column", fontSize: 11, gap: 2 }}>
                qty
                <input
                  value={sellQty}
                  onChange={(e) => setSellQty(e.target.value)}
                  style={{ width: 48, padding: 4 }}
                />
              </label>
              <label style={{ display: "flex", flexDirection: "column", fontSize: 11, gap: 2 }}>
                ¢/unit
                <input
                  value={sellPriceCents}
                  onChange={(e) => setSellPriceCents(e.target.value)}
                  style={{ width: 56, padding: 4 }}
                />
              </label>
              <button type="button" disabled={busy} onClick={() => void placeSellOrder()} style={{ alignSelf: "flex-end" }}>
                Place ask
              </button>
            </div>

            <h3 style={{ fontSize: 14, marginTop: 14, marginBottom: 6 }}>In transit</h3>
            {(world.in_transit ?? []).length === 0 ? (
              <p style={{ opacity: 0.7 }}>None</p>
            ) : (
              <ul style={{ paddingLeft: 18, margin: "0 0 8px", fontSize: 12 }}>
                {(world.in_transit ?? []).map((s) => (
                  <li key={s.id}>
                    {s.material} ×{s.qty} → {s.dest_plot_id} (arr. tick {s.arrive_tick})
                  </li>
                ))}
              </ul>
            )}

            <h3 style={{ fontSize: 14, marginTop: 14, marginBottom: 6 }}>Ship (player, owned plots)</h3>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 8 }}>
              <label style={{ display: "flex", flexDirection: "column", fontSize: 11, gap: 2 }}>
                from
                <input value={shipFrom} onChange={(e) => setShipFrom(e.target.value)} style={{ width: 72, padding: 4 }} />
              </label>
              <label style={{ display: "flex", flexDirection: "column", fontSize: 11, gap: 2 }}>
                to
                <input value={shipTo} onChange={(e) => setShipTo(e.target.value)} style={{ width: 72, padding: 4 }} />
              </label>
              <label style={{ display: "flex", flexDirection: "column", fontSize: 11, gap: 2 }}>
                material
                <input
                  value={shipMaterial}
                  onChange={(e) => setShipMaterial(e.target.value)}
                  style={{ width: 88, padding: 4 }}
                />
              </label>
              <label style={{ display: "flex", flexDirection: "column", fontSize: 11, gap: 2 }}>
                qty
                <input value={shipQty} onChange={(e) => setShipQty(e.target.value)} style={{ width: 40, padding: 4 }} />
              </label>
              <button type="button" disabled={busy} onClick={() => void shipGoods()} style={{ alignSelf: "flex-end" }}>
                Dispatch
              </button>
            </div>

            <h3 style={{ fontSize: 14, marginTop: 14, marginBottom: 6 }}>Save / load (SQLite)</h3>
            <p style={{ margin: "0 0 8px", fontSize: 12, opacity: 0.75 }}>
              Writes <code>saves/realm_dev.sqlite</code> at repo root (from engine cwd).
            </p>
            <button type="button" disabled={busy} onClick={() => void persistenceSave()} style={{ marginRight: 8 }}>
              Save snapshot
            </button>
            <button type="button" disabled={busy} onClick={() => void persistenceLoad()}>
              Load snapshot
            </button>

            <h3 style={{ fontSize: 14, marginTop: 14, marginBottom: 6 }}>Contracts (stub)</h3>
            <p style={{ margin: "0 0 8px", fontSize: 12, opacity: 0.75 }}>
              Last id: {lastContractId ?? "—"} · open contracts: {(world.contracts ?? []).filter((c) => (c as { status?: string }).status === "open").length}
            </p>
            <button type="button" disabled={busy} onClick={() => void proposeContract()} style={{ marginRight: 8 }}>
              Propose with vendor
            </button>
            <button type="button" disabled={busy} onClick={() => void honorContract()}>
              Honor last
            </button>

            <h3 style={{ fontSize: 14, marginTop: 18, marginBottom: 6 }}>Action log</h3>
            <div
              style={{
                maxHeight: 220,
                overflowY: "auto",
                border: "1px solid #30363d",
                borderRadius: 4,
                padding: 8,
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                background: "#0d1117",
              }}
            >
              {eventLogReversed.length === 0 ? (
                <span style={{ opacity: 0.6 }}>No events yet.</span>
              ) : (
                eventLogReversed.map((e, i) => (
                  <div key={i} style={{ marginBottom: 6, lineHeight: 1.35 }}>
                    <span style={{ opacity: 0.55 }}>t{e.tick}</span>{" "}
                    <span style={{ opacity: 0.75 }}>[{e.kind}]</span> {e.message}
                  </div>
                ))
              )}
            </div>
          </aside>
        </section>
      ) : (
        <p>Loading world…</p>
      )}
    </main>
  );
}
