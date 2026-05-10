"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { PLOT_SCHEMATIC_STORAGE_PREFIX } from "./frontierConstants";
import { displayMaterial } from "./formatters";
import { reorderChain, validateLinearRecipeChain, type SchematicRecipe } from "./plotSchematic";

export type PlotSchematicPanelProps = {
  recipes: SchematicRecipe[];
  playerInventory: Record<string, number>;
  eligiblePlots: { id: string; shortLabel: string }[];
  selectedPlotId: string | null;
  onSelectPlot: (plotId: string) => void;
  disabled: boolean;
};

export function PlotSchematicPanel({
  recipes,
  playerInventory,
  eligiblePlots,
  selectedPlotId,
  onSelectPlot,
  disabled,
}: PlotSchematicPanelProps) {
  const storageKey = selectedPlotId ? `${PLOT_SCHEMATIC_STORAGE_PREFIX}${selectedPlotId}` : null;

  const [chain, setChain] = useState<string[]>([]);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [validation, setValidation] = useState<{ ok: true; source?: "engine" | "client" } | { ok: false; errors: string[] } | null>(
    null,
  );
  const [validating, setValidating] = useState(false);

  useEffect(() => {
    setValidation(null);
    if (!storageKey) {
      setChain([]);
      return;
    }
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) {
        const parsed = JSON.parse(raw) as unknown;
        if (Array.isArray(parsed) && parsed.every((x) => typeof x === "string")) {
          setChain(parsed);
          return;
        }
      }
    } catch {
      /* ignore */
    }
    setChain([]);
  }, [storageKey]);

  useEffect(() => {
    if (!storageKey) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify(chain));
    } catch {
      /* ignore */
    }
  }, [storageKey, chain]);

  const recipeById = useMemo(() => new Map(recipes.map((r) => [r.id, r])), [recipes]);

  const runValidate = useCallback(async () => {
    if (!selectedPlotId) return;
    setValidating(true);
    try {
      const r = await fetch(
        `/api/engine/plots/${encodeURIComponent(selectedPlotId)}/schematic/validate?party=player`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ recipe_ids: chain }),
        },
      );
      if (r.ok) {
        const body = (await r.json()) as { ok?: boolean; errors?: string[] };
        if (body.ok === true) {
          setValidation({ ok: true, source: "engine" });
          return;
        }
        setValidation({ ok: false, errors: Array.isArray(body.errors) ? body.errors : ["Engine rejected the chain."] });
        return;
      }
      const txt = await r.text();
      let detail = txt;
      try {
        const j = JSON.parse(txt) as { detail?: unknown };
        if (typeof j.detail === "string") detail = j.detail;
        else if (Array.isArray(j.detail) && j.detail[0] && typeof (j.detail[0] as { msg?: string }).msg === "string") {
          detail = (j.detail[0] as { msg: string }).msg;
        }
      } catch {
        /* use raw txt */
      }
      setValidation({ ok: false, errors: [detail || `Request failed (${r.status})`] });
    } catch {
      const res = validateLinearRecipeChain(recipes, playerInventory, chain);
      if (res.ok) {
        setValidation({ ok: true, source: "client" });
      } else {
        setValidation(res);
      }
    } finally {
      setValidating(false);
    }
  }, [selectedPlotId, chain, recipes, playerInventory]);

  const addRecipe = useCallback((recipeId: string) => {
    setChain((c) => [...c, recipeId]);
    setValidation(null);
  }, []);

  const removeAt = useCallback((index: number) => {
    setChain((c) => c.filter((_, i) => i !== index));
    setValidation(null);
  }, []);

  const clearChain = useCallback(() => {
    setChain([]);
    setValidation(null);
  }, []);

  const onDragStart = (index: number) => (e: React.DragEvent) => {
    setDragIndex(index);
    e.dataTransfer.setData("text/plain", String(index));
    e.dataTransfer.effectAllowed = "move";
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const onDropOnIndex = (targetIndex: number) => (e: React.DragEvent) => {
    e.preventDefault();
    const from = Number(e.dataTransfer.getData("text/plain"));
    if (!Number.isFinite(from)) return;
    setChain((items) => reorderChain(items, from, targetIndex));
    setDragIndex(null);
    setValidation(null);
  };

  const onDragEnd = () => setDragIndex(null);

  if (!selectedPlotId) {
    return (
      <p className="realm-help">
        Select a <strong>surveyed plot you own</strong> from the territory panel first (gold ring on the map), then return here — each plot keeps its own saved
        chain.
      </p>
    );
  }

  if (eligiblePlots.every((p) => p.id !== selectedPlotId)) {
    return (
      <>
        <p className="realm-help" style={{ marginBottom: 10 }}>
          Plot <strong>{selectedPlotId}</strong> is not surveyed or not yours. Pick a workshop plot for this schematic:
        </p>
        {eligiblePlots.length === 0 ? (
          <p className="realm-help">Claim and survey a plot on the territory map first.</p>
        ) : (
          <label className="realm-label">
            Workshop plot
            <select
              className="realm-input"
              value={eligiblePlots[0]?.id}
              onChange={(e) => onSelectPlot(e.target.value)}
              style={{ minWidth: 160 }}
            >
              {eligiblePlots.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.shortLabel}
                </option>
              ))}
            </select>
          </label>
        )}
      </>
    );
  }

  return (
    <>
      <p className="realm-help" style={{ marginBottom: 12 }}>
        Build an <strong>ordered pipeline</strong> of engine recipes. Validation assumes each batch finishes before the next starts, and uses your{" "}
        <strong>current player inventory</strong> as the starting stock (solo planning — the sim still runs one active run per plot).
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end", marginBottom: 16 }}>
        <label className="realm-label">
          Workshop plot
          <select
            className="realm-input"
            value={selectedPlotId}
            onChange={(e) => onSelectPlot(e.target.value)}
            style={{ minWidth: 160 }}
          >
            {eligiblePlots.map((p) => (
              <option key={p.id} value={p.id}>
                {p.shortLabel}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="realm-btn realm-btn--ghost"
          disabled={disabled || validating}
          onClick={() => void runValidate()}
        >
          {validating ? "Validating…" : "Validate chain"}
        </button>
        <button type="button" className="realm-btn realm-btn--ghost" disabled={disabled || chain.length === 0} onClick={clearChain}>
          Clear chain
        </button>
      </div>

      {validation ? (
        validation.ok ? (
          <p style={{ color: "var(--realm-ok, #6bbf6b)", marginBottom: 14, fontSize: 14 }}>
            {validation.source === "client" ? (
              <>
                Chain looks feasible offline (engine unreachable — using the same rules in your browser). Outputs compound through the steps.
              </>
            ) : (
              <>
                <strong>Engine confirms</strong> this chain is feasible with your current inventory (simulated outputs compound through the steps).
              </>
            )}
          </p>
        ) : (
          <div
            role="alert"
            style={{
              marginBottom: 14,
              padding: "10px 12px",
              borderRadius: 8,
              background: "rgba(220, 80, 80, 0.12)",
              border: "1px solid rgba(220, 80, 80, 0.35)",
              fontSize: 13,
            }}
          >
            <strong>Validation failed</strong>
            <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
              {validation.errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          </div>
        )
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.1fr)", gap: 16 }}>
        <div>
          <h4 className="realm-help" style={{ margin: "0 0 8px", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.06em", opacity: 0.85 }}>
            Recipe palette
          </h4>
          <div
            style={{
              maxHeight: 320,
              overflowY: "auto",
              border: "1px solid var(--realm-border, rgba(255,255,255,0.12))",
              borderRadius: 8,
              padding: 8,
            }}
          >
            {recipes.length === 0 ? (
              <span className="realm-help">No recipes in world snapshot.</span>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {recipes.map((r) => (
                  <li key={r.id} style={{ marginBottom: 6 }}>
                    <button
                      type="button"
                      className="realm-list-btn"
                      disabled={disabled}
                      onClick={() => addRecipe(r.id)}
                      title={`Add ${r.display_name} to chain`}
                    >
                      <span style={{ fontWeight: 600 }}>{r.display_name}</span>
                      <span style={{ display: "block", opacity: 0.85, fontSize: 11, marginTop: 2 }}>
                        {Object.entries(r.inputs)
                          .map(([k, v]) => `${v}× ${displayMaterial(k)}`)
                          .join(" · ")}{" "}
                        →{" "}
                        {Object.entries(r.outputs)
                          .map(([k, v]) => `${v}× ${displayMaterial(k)}`)
                          .join(" · ")}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div>
          <h4 className="realm-help" style={{ margin: "0 0 8px", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.06em", opacity: 0.85 }}>
            Chain (drag to reorder)
          </h4>
          {chain.length === 0 ? (
            <p className="realm-help" style={{ minHeight: 120, padding: 12 }}>
              Add recipes from the palette. Order matters: outputs from step N are available for step N+1.
            </p>
          ) : (
            <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {chain.map((rid, index) => {
                const r = recipeById.get(rid);
                const label = r?.display_name ?? rid;
                const active = dragIndex === index;
                return (
                  <li key={`${rid}-${index}`} style={{ marginBottom: 0 }}>
                    <div
                      draggable={!disabled}
                      onDragStart={onDragStart(index)}
                      onDragOver={onDragOver}
                      onDrop={onDropOnIndex(index)}
                      onDragEnd={onDragEnd}
                      style={{
                        display: "flex",
                        alignItems: "stretch",
                        gap: 8,
                        marginBottom: 4,
                        opacity: active ? 0.65 : 1,
                        cursor: disabled ? "default" : "grab",
                      }}
                    >
                      <div
                        style={{
                          flex: 1,
                          padding: "8px 10px",
                          borderRadius: 8,
                          border: "1px solid var(--realm-border, rgba(255,255,255,0.15))",
                          background: "var(--realm-panel-2, rgba(0,0,0,0.2))",
                        }}
                      >
                        <span style={{ fontSize: 11, opacity: 0.6, marginRight: 8 }}>{index + 1}.</span>
                        <strong>{label}</strong>
                        {r ? (
                          <div style={{ fontSize: 11, opacity: 0.85, marginTop: 4 }}>
                            {Object.entries(r.outputs)
                              .map(([k, v]) => `${v}× ${displayMaterial(k)}`)
                              .join(" · ")}
                          </div>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        className="realm-btn realm-btn--ghost realm-btn--sm"
                        disabled={disabled}
                        onClick={() => removeAt(index)}
                        aria-label={`Remove ${label}`}
                      >
                        ✕
                      </button>
                    </div>
                    {index < chain.length - 1 ? (
                      <div style={{ textAlign: "center", fontSize: 18, opacity: 0.35, lineHeight: 1, margin: "2px 0 6px" }}>
                        ↓
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
    </>
  );
}
