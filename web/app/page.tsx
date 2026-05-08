"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

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

type WorldDto = {
  seed: number;
  tick: number;
  plots: PlotDto[];
  balances_cents: Record<string, number>;
  inventory: Record<string, Record<string, number>>;
  parties: string[];
  recipes: RecipeDto[];
  active_production: ActiveProductionDto[];
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
    if (!world?.plots.length) return { w: 0, h: 0, cells: [] as PlotDto[][] };
    const w = Math.max(...world.plots.map((p) => p.x)) + 1;
    const h = Math.max(...world.plots.map((p) => p.y)) + 1;
    const cells: PlotDto[][] = Array.from({ length: h }, () =>
      Array.from({ length: w }, () => null as unknown as PlotDto),
    );
    for (const p of world.plots) {
      cells[p.y][p.x] = p;
    }
    return { w, h, cells };
  }, [world]);

  const selectedPlot = useMemo(
    () => world?.plots.find((p) => p.id === selectedPlotId) ?? null,
    [world, selectedPlotId],
  );

  const playerInv = world?.inventory["player"] ?? {};

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
                gridTemplateColumns: `repeat(${grid.w}, 36px)`,
                gap: 2,
                border: "1px solid #30363d",
                padding: 4,
                background: "#161b22",
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
                        width: 36,
                        height: 36,
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
          </aside>
        </section>
      ) : (
        <p>Loading world…</p>
      )}
    </main>
  );
}
