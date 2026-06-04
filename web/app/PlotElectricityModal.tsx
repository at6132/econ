"use client";

import { useCallback, useEffect, useState } from "react";

type ProviderOffer = {
  provider_party: string;
  display_name: string;
  rate_cents_per_kwh: number;
  min_kwh_per_day: number;
  max_kwh_per_day: number;
  capacity_kwh_per_day: number;
  already_connected: boolean;
};

type Connection = {
  connection_id: string;
  provider_name: string;
  provider: string;
  role: string;
  rate_cents_per_kwh: number;
  min_wh_per_day: number;
  max_wh_per_day: number;
  status: string;
  contract_text: string;
};

type EnergyFlow = {
  sources: Array<{ label: string; capacity_wh_per_day: number; own: boolean }>;
  storage: Array<{ instance_id: string; label: string; stored_wh: number; capacity_wh: number }>;
  consumers: Array<{ label: string; kind: string; draw_wh_per_batch?: number }>;
  load_wh_today: number;
  config: {
    primary_connection_id: string;
    backup_connection_ids: string[];
    battery_instance_ids: string[];
  };
};

export type PlotEnergySnapshot = {
  ok: boolean;
  plot_id: string;
  access_mode: string;
  may_draw_grid_energy: boolean;
  block_reason: string | null;
  provider_offers: ProviderOffer[];
  connections: Connection[];
  energy_flow: EnergyFlow;
  utility_config: EnergyFlow["config"];
  power: {
    powered: boolean;
    clearing_price_cents: number;
    status_note?: string;
    brownout?: boolean;
  };
};

type Props = {
  open: boolean;
  plotId: string;
  worldTick: number;
  party?: string;
  onClose: () => void;
  onWorldChange?: () => void;
};

export function PlotElectricityModal({
  open,
  plotId,
  worldTick,
  party = "player",
  onClose,
  onWorldChange,
}: Props): JSX.Element | null {
  const [data, setData] = useState<PlotEnergySnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [contractOpen, setContractOpen] = useState(false);
  const [contractText, setContractText] = useState("");
  const [contractProvider, setContractProvider] = useState("");
  const [contractRate, setContractRate] = useState(0);
  const [agreed, setAgreed] = useState(false);

  const reload = useCallback(async () => {
    if (!open) return;
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
  }, [open, plotId, party]);

  useEffect(() => {
    void reload();
  }, [open, plotId, worldTick, reload]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !contractOpen) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, contractOpen, onClose]);

  const saveConfig = async (patch: Partial<EnergyFlow["config"]>) => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(
        `/api/engine/plots/${encodeURIComponent(plotId)}/grid-utility/config?party=${encodeURIComponent(party)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        },
      );
      const j = (await r.json()) as { reason?: string };
      if (!r.ok) setMsg(String(j.reason ?? r.statusText));
      else {
        onWorldChange?.();
        await reload();
      }
    } finally {
      setBusy(false);
    }
  };

  const openContract = async (provider: string) => {
    setBusy(true);
    setMsg(null);
    try {
      const q = new URLSearchParams({ party, provider });
      const r = await fetch(
        `/api/engine/plots/${encodeURIComponent(plotId)}/grid-utility/contract-preview?${q}`,
      );
      const j = (await r.json()) as {
        contract_text?: string;
        rate_cents_per_kwh?: number;
        reason?: string;
      };
      if (!r.ok) {
        setMsg(String(j.reason ?? r.statusText));
        return;
      }
      setContractProvider(provider);
      setContractText(String(j.contract_text ?? ""));
      setContractRate(Number(j.rate_cents_per_kwh ?? 0));
      setAgreed(false);
      setContractOpen(true);
    } finally {
      setBusy(false);
    }
  };

  const signContract = async () => {
    if (!agreed || !contractProvider) return;
    setBusy(true);
    try {
      const q = new URLSearchParams({
        party,
        provider: contractProvider,
        payment_method: "party_cash",
        agreed_to_terms: "true",
        rate_cents_per_kwh: String(contractRate),
      });
      const r = await fetch(
        `/api/engine/plots/${encodeURIComponent(plotId)}/grid-utility/connect?${q}`,
        { method: "POST" },
      );
      const j = (await r.json()) as { reason?: string; connection_id?: string };
      if (!r.ok) setMsg(String(j.reason ?? r.statusText));
      else {
        setContractOpen(false);
        setMsg(`Signed contract ${j.connection_id ?? ""}`);
        onWorldChange?.();
        await reload();
      }
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async (connectionId: string) => {
    setBusy(true);
    try {
      const q = new URLSearchParams({ party, connection_id: connectionId });
      const r = await fetch(`/api/engine/grid-utility/disconnect?${q}`, { method: "POST" });
      const j = (await r.json()) as { reason?: string };
      if (!r.ok) setMsg(String(j.reason ?? r.statusText));
      else {
        onWorldChange?.();
        await reload();
      }
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  const flow = data?.energy_flow;
  const cfg = data?.utility_config ?? flow?.config;
  const connections = data?.connections.filter((c) => c.status === "active") ?? [];
  const offers = data?.provider_offers ?? [];

  return (
    <>
      <div
        className="realm-settings-backdrop"
        role="presentation"
        onMouseDown={(e) => {
          if (e.target === e.currentTarget && !contractOpen) onClose();
        }}
      >
        <div
          className="realm-settings-dialog realm-electricity-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="plot-electricity-title"
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="realm-settings-dialog__head">
            <h2 id="plot-electricity-title" className="realm-settings-dialog__title">
              Electricity — {plotId}
            </h2>
            <button type="button" className="realm-btn realm-btn--ghost realm-btn--sm" onClick={onClose}>
              ✕
            </button>
          </div>
          <div className="realm-settings-dialog__body">
            {data?.power ? (
              <p className="realm-help" style={{ marginTop: 0 }}>
                {data.power.status_note || "Grid"} · clearing {data.power.clearing_price_cents}¢/kWh
                {data.power.brownout ? " · brownout" : ""}
                {data.may_draw_grid_energy ? " · authorized" : " · not authorized"}
              </p>
            ) : null}

            <div className="realm-electricity-panels">
              <section className="realm-electricity-panel">
                <h3 className="realm-settings-section__title">Flow & routing</h3>
                <p className="realm-help">Load today: {((flow?.load_wh_today ?? 0) / 1000).toFixed(1)} kWh</p>

                <h4 className="realm-electricity-subhead">Sources</h4>
                {flow?.sources.length ? (
                  <ul className="realm-electricity-list">
                    {flow.sources.map((s) => (
                      <li key={s.label + String(s.capacity_wh_per_day)}>
                        {s.label} — {(s.capacity_wh_per_day / 1000).toFixed(1)} kWh/day
                        {s.own ? " (yours)" : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="realm-help">No on-plot generators.</p>
                )}

                <h4 className="realm-electricity-subhead">Storage</h4>
                {flow?.storage.length ? (
                  <ul className="realm-electricity-list">
                    {flow.storage.map((b) => (
                      <li key={b.instance_id}>
                        {b.label} — {(b.stored_wh / 1000).toFixed(1)} / {(b.capacity_wh / 1000).toFixed(1)} kWh
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="realm-help">No battery banks on plot.</p>
                )}

                <h4 className="realm-electricity-subhead">Consumers</h4>
                {flow?.consumers.length ? (
                  <ul className="realm-electricity-list">
                    {flow.consumers.map((c) => (
                      <li key={c.label + c.kind}>
                        {c.label}
                        {c.draw_wh_per_batch ? ` — ${(c.draw_wh_per_batch / 1000).toFixed(1)} kWh/batch` : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="realm-help">No active consumers.</p>
                )}

                {cfg && connections.length > 0 ? (
                  <>
                    <h4 className="realm-electricity-subhead">Supply routing</h4>
                    <label className="realm-electricity-field">
                      Primary provider
                      <select
                        className="realm-input"
                        value={cfg.primary_connection_id}
                        disabled={busy}
                        onChange={(e) => void saveConfig({ primary_connection_id: e.target.value })}
                      >
                        <option value="">—</option>
                        {connections.map((c) => (
                          <option key={c.connection_id} value={c.connection_id}>
                            {c.provider_name} ({c.rate_cents_per_kwh}¢/kWh)
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="realm-electricity-field">
                      Backup providers (hold Ctrl)
                      <select
                        className="realm-input"
                        multiple
                        size={Math.min(4, connections.length)}
                        value={cfg.backup_connection_ids}
                        disabled={busy}
                        onChange={(e) => {
                          const ids = Array.from(e.target.selectedOptions).map((o) => o.value);
                          void saveConfig({ backup_connection_ids: ids });
                        }}
                      >
                        {connections.map((c) => (
                          <option key={c.connection_id} value={c.connection_id}>
                            {c.provider_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    {flow?.storage.length ? (
                      <label className="realm-electricity-field">
                        Battery backup banks
                        <select
                          className="realm-input"
                          multiple
                          size={Math.min(3, flow.storage.length)}
                          value={cfg.battery_instance_ids}
                          disabled={busy}
                          onChange={(e) => {
                            const ids = Array.from(e.target.selectedOptions).map((o) => o.value);
                            void saveConfig({ battery_instance_ids: ids });
                          }}
                        >
                          {flow.storage.map((b) => (
                            <option key={b.instance_id} value={b.instance_id}>
                              {b.label} ({b.instance_id})
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                  </>
                ) : null}
              </section>

              <section className="realm-electricity-panel">
                <h3 className="realm-settings-section__title">Providers & contracts</h3>

                <h4 className="realm-electricity-subhead">Available</h4>
                {offers.length === 0 ? (
                  <p className="realm-help">No third-party grid providers in this region.</p>
                ) : (
                  <ul className="realm-electricity-provider-cards">
                    {offers.map((o) => (
                      <li key={o.provider_party} className="realm-electricity-provider-card">
                        <strong>{o.display_name}</strong>
                        <div className="realm-help">
                          {o.rate_cents_per_kwh}¢/kWh · cap {o.capacity_kwh_per_day} kWh/day
                          <br />
                          Contract band: {o.min_kwh_per_day}–{o.max_kwh_per_day} kWh/day
                        </div>
                        <button
                          type="button"
                          className="realm-btn realm-btn--primary realm-btn--sm"
                          disabled={busy || o.already_connected}
                          onClick={() => void openContract(o.provider_party)}
                        >
                          {o.already_connected ? "Connected" : "Select"}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                <h4 className="realm-electricity-subhead">Signed on this plot</h4>
                {connections.length === 0 ? (
                  <p className="realm-help">No active contracts.</p>
                ) : (
                  <ul className="realm-electricity-provider-cards">
                    {connections.map((c) => (
                      <li key={c.connection_id} className="realm-electricity-provider-card">
                        <strong>{c.provider_name}</strong>
                        <div className="realm-help">
                          {c.rate_cents_per_kwh}¢/kWh · role {c.role}
                          <br />
                          {(c.min_wh_per_day / 1000).toFixed(1)}–{(c.max_wh_per_day / 1000).toFixed(1)} kWh/day
                        </div>
                        <button
                          type="button"
                          className="realm-btn realm-btn--sm"
                          disabled={busy}
                          onClick={() => void disconnect(c.connection_id)}
                        >
                          Cancel
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>

            {data?.block_reason ? (
              <p className="realm-help" style={{ color: "#c9a227", marginTop: 10 }}>
                {data.block_reason}
              </p>
            ) : null}
            {msg ? <p className="realm-help" style={{ marginTop: 8 }}>{msg}</p> : null}
          </div>
        </div>
      </div>

      {contractOpen ? (
        <div
          className="realm-settings-backdrop"
          style={{ zIndex: 10050 }}
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setContractOpen(false);
          }}
        >
          <div
            className="realm-settings-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="utility-contract-title"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="realm-settings-dialog__head">
              <h2 id="utility-contract-title" className="realm-settings-dialog__title">
                Utility contract
              </h2>
              <button
                type="button"
                className="realm-btn realm-btn--ghost realm-btn--sm"
                onClick={() => setContractOpen(false)}
              >
                ✕
              </button>
            </div>
            <div className="realm-settings-dialog__body">
              <pre className="realm-electricity-contract">{contractText}</pre>
              <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 12 }}>
                <input
                  type="checkbox"
                  checked={agreed}
                  onChange={(e) => setAgreed(e.target.checked)}
                />
                <span>I have read and agree to the terms of this grid power supply agreement.</span>
              </label>
              <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
                <button
                  type="button"
                  className="realm-btn realm-btn--primary"
                  disabled={!agreed || busy}
                  onClick={() => void signContract()}
                >
                  {busy ? "Signing…" : "Sign contract"}
                </button>
                <button type="button" className="realm-btn" disabled={busy} onClick={() => setContractOpen(false)}>
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
