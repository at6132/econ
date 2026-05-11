"use client";

import { useCallback, useEffect, useRef } from "react";

type DevScenario = "frontier" | "bootstrapper" | "speculator" | "cartel" | "millrace" | "archive";

type Props = {
  open: boolean;
  onClose: () => void;
  busy: boolean;
  simPaused: boolean;
  onTogglePause: () => void;
  simSpeedIdx: 0 | 1 | 2;
  simSpeedLabels: readonly [string, string, string];
  simSpeedsMs: readonly [number, number, number];
  onSetSimSpeedIdx: (i: 0 | 1 | 2) => void;
  showDevReset: boolean;
  devResetScenario: DevScenario;
  onDevResetScenario: (s: DevScenario) => void;
  onDevResetWorld: () => void | Promise<void>;
};

export function FrontierSettingsModal({
  open,
  onClose,
  busy,
  simPaused,
  onTogglePause,
  simSpeedIdx,
  simSpeedLabels,
  simSpeedsMs,
  onSetSimSpeedIdx,
  showDevReset,
  devResetScenario,
  onDevResetScenario,
  onDevResetWorld,
}: Props) {
  const panelRef = useRef<HTMLDivElement>(null);

  const onBackdropMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const id = window.requestAnimationFrame(() => panelRef.current?.querySelector<HTMLElement>("button, [href], input, select, textarea")?.focus());
    return () => cancelAnimationFrame(id);
  }, [open]);

  if (!open) return null;

  return (
    <div className="realm-settings-backdrop" role="presentation" onMouseDown={onBackdropMouseDown}>
      <div
        ref={panelRef}
        className="realm-settings-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="realm-settings-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="realm-settings-dialog__head">
          <h2 id="realm-settings-title" className="realm-settings-dialog__title">
            Settings
          </h2>
          <button type="button" className="realm-btn realm-btn--ghost realm-btn--sm" onClick={onClose} aria-label="Close settings">
            ✕
          </button>
        </div>

        <div className="realm-settings-dialog__body">
          <section className="realm-settings-section" aria-labelledby="realm-settings-sim">
            <h3 id="realm-settings-sim" className="realm-settings-section__title">
              Simulation
            </h3>
            <p className="realm-help" style={{ marginTop: 0 }}>
              Solo pacing: real-time gap between automatic engine ticks. Use header <strong>Pause</strong> to freeze auto-advance; <strong>Run</strong> resumes
              the timer. While paused you can still trade, produce, and use other actions that call the engine.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginTop: 10 }}>
              <button
                type="button"
                className={`realm-btn realm-btn--sm ${simPaused ? "realm-btn--ghost" : "realm-btn--primary"}`}
                disabled={busy}
                onClick={onTogglePause}
              >
                {simPaused ? "Run" : "Pause"}
              </button>
              <span className="realm-help" style={{ margin: 0 }}>
                Clock is {simPaused ? <strong>paused</strong> : <strong>running</strong>}.
              </span>
            </div>
            <p className="realm-help" style={{ marginBottom: 6 }}>
              Tick interval (not wall-clock canon for multiplayer):
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {([0, 1, 2] as const).map((i) => (
                <button
                  key={i}
                  type="button"
                  className={`realm-btn realm-btn--sm ${simSpeedIdx === i ? "realm-btn--primary" : "realm-btn--ghost"}`}
                  disabled={busy}
                  onClick={() => onSetSimSpeedIdx(i)}
                >
                  {simSpeedLabels[i]} ({(simSpeedsMs[i] / 1000).toFixed(1)}s)
                </button>
              ))}
            </div>
          </section>

          {showDevReset ? (
            <section className="realm-settings-section" aria-labelledby="realm-settings-dev">
              <h3 id="realm-settings-dev" className="realm-settings-section__title">
                Dev · world reset
              </h3>
              <p className="realm-help" style={{ marginTop: 0 }}>
                Rebuilds the in-memory bootstrap world (seed 42). Unsaved play is lost unless you saved a SQLite snapshot first.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end", marginTop: 8 }}>
                <label className="realm-label">
                  Scenario
                  <select
                    className="realm-input"
                    style={{ minWidth: 160 }}
                    value={devResetScenario}
                    disabled={busy}
                    onChange={(e) => onDevResetScenario(e.target.value as DevScenario)}
                  >
                    <option value="frontier">frontier</option>
                    <option value="bootstrapper">bootstrapper</option>
                    <option value="speculator">speculator</option>
                    <option value="cartel">cartel</option>
                    <option value="millrace">millrace</option>
                    <option value="archive">archive</option>
                  </select>
                </label>
                <button type="button" className="realm-btn realm-btn--ghost" disabled={busy} onClick={() => void onDevResetWorld()}>
                  Dev: reset world
                </button>
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}
