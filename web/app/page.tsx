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

type WorldDto = {
  seed: number;
  tick: number;
  plots: PlotDto[];
  balances_cents: Record<string, number>;
  inventory: Record<string, Record<string, number>>;
  parties: string[];
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

  const playerCash =
    world?.balances_cents["cash:player"] != null
      ? (world.balances_cents["cash:player"] / 100).toFixed(2)
      : "—";

  return (
    <main style={{ padding: 16, maxWidth: 1100, margin: "0 auto" }}>
      <header style={{ marginBottom: 16 }}>
        <h1 style={{ margin: "0 0 8px", fontSize: 22 }}>Realm — Frontier (Phase 1 shell)</h1>
        <p style={{ margin: 0, opacity: 0.85, fontSize: 14 }}>
          Map reads from the Python engine. Run <code>uvicorn realm.api:app</code> from{" "}
          <code>engine/</code> on port 8000, then <code>npm run dev</code> here.
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
                row.map((p, x) => (
                  <button
                    key={p?.id ?? `${x}-${y}`}
                    type="button"
                    title={`${p?.id ?? ""} ${p?.terrain ?? ""} owner=${p?.owner ?? "none"}`}
                    disabled={busy || !p}
                    onClick={() => {
                      if (!p) return;
                      if (!p.owner) void claim(p.id);
                      else if (p.owner === "player" && !p.surveyed) void survey(p.id);
                    }}
                    style={{
                      width: 36,
                      height: 36,
                      border: p?.owner ? "2px solid #58a6ff" : "1px solid #21262d",
                      background: p ? terrainColor(p.terrain) : "#000",
                      cursor: busy ? "wait" : "pointer",
                      padding: 0,
                    }}
                  />
                )),
              )}
            </div>
            <p style={{ fontSize: 12, opacity: 0.75, marginTop: 8, maxWidth: 420 }}>
              Click unclaimed plot to claim (player). Click your plot again to survey ($500). Colors =
              terrain.
            </p>
            <button type="button" disabled={busy} onClick={() => void tick()} style={{ marginTop: 8 }}>
              Advance tick
            </button>
          </div>

          <aside style={{ minWidth: 260, fontSize: 13 }}>
            <h2 style={{ fontSize: 15, marginTop: 0 }}>Plot detail</h2>
            <p style={{ opacity: 0.8 }}>Select by clicking the map (first matching cell).</p>
          </aside>
        </section>
      ) : (
        <p>Loading world…</p>
      )}
    </main>
  );
}
