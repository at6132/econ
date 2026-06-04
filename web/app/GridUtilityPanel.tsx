"use client";

import { useCallback, useEffect, useState } from "react";

import { PlotElectricityModal, type PlotEnergySnapshot } from "./PlotElectricityModal";

export function GridUtilityPanel({
  plotId,
  worldTick,
  party = "player",
  onWorldChange,
}: {
  plotId: string;
  worldTick: number;
  party?: string;
  onWorldChange?: () => void;
}): JSX.Element | null {
  const [data, setData] = useState<PlotEnergySnapshot | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const reload = useCallback(async () => {
    try {
      const r = await fetch(
        `/api/engine/plots/${encodeURIComponent(plotId)}/energy?party=${encodeURIComponent(party)}`,
        { cache: "no-store" },
      );
      if (!r.ok) return;
      setData((await r.json()) as PlotEnergySnapshot);
    } catch {
      /* optional */
    }
  }, [plotId, party]);

  useEffect(() => {
    void reload();
  }, [plotId, worldTick, reload]);

  if (!data) return null;

  const statusLabel =
    data.access_mode === "own_generation"
      ? "Self-supplied"
      : data.access_mode === "utility_contract"
        ? `${data.connections.filter((c) => c.status === "active").length} contract(s)`
        : data.access_mode === "requires_contract"
          ? "Needs contract"
          : data.access_mode === "unpowered" || !data.power?.powered
            ? "Off grid"
            : data.power?.powered
              ? "On grid"
              : "Electricity";

  return (
    <>
      <div
        className="realm-panel-inset"
        style={{ marginTop: 10, padding: "8px 10px", borderLeft: "3px solid #ffc870" }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <div style={{ fontSize: 11 }}>
            <span style={{ fontWeight: 600, color: "#ffc870", letterSpacing: "0.06em" }}>ELECTRICITY</span>
            <span style={{ display: "block", marginTop: 2, opacity: 0.9 }}>
              {statusLabel}
              {data.power?.powered ? ` · ${data.power.clearing_price_cents}¢/kWh clearing` : ""}
            </span>
          </div>
          <button
            type="button"
            className="realm-btn realm-btn--primary realm-btn--sm"
            onClick={() => setModalOpen(true)}
          >
            Manage
          </button>
        </div>
        {!data.may_draw_grid_energy && data.block_reason ? (
          <p className="realm-help" style={{ margin: "6px 0 0", fontSize: 10, color: "#c9a227" }}>
            {data.block_reason}
          </p>
        ) : null}
      </div>

      <PlotElectricityModal
        open={modalOpen}
        plotId={plotId}
        worldTick={worldTick}
        party={party}
        onClose={() => setModalOpen(false)}
        onWorldChange={() => {
          onWorldChange?.();
          void reload();
        }}
      />
    </>
  );
}
