"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import type { LabPresetDetail, LabOverrideSchema } from "../../labsTypes";

function LabsLaunchInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const presetId = searchParams.get("preset") ?? "";

  const [preset, setPreset] = useState<LabPresetDetail | null>(null);
  const [seed, setSeed] = useState(42);
  const [mapScalePct, setMapScalePct] = useState(100);
  const [cashScalePct, setCashScalePct] = useState(100);
  const [settlerCount, setSettlerCount] = useState<number | null>(null);
  const [simSpeed, setSimSpeed] = useState(2);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!presetId) {
      setError("No preset selected.");
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const r = await fetch(`/api/engine/labs/presets/${encodeURIComponent(presetId)}`);
        if (!r.ok) throw new Error(await r.text());
        const j = (await r.json()) as { preset: LabPresetDetail };
        if (cancelled) return;
        setPreset(j.preset);
        setSeed(j.preset.default_seed);
        setSimSpeed(j.preset.default_sim_speed);
        const schema = j.preset.override_schema;
        if (schema.map_scale_pct?.default != null) setMapScalePct(schema.map_scale_pct.default);
        if (schema.cash_scale_pct?.default != null) setCashScalePct(schema.cash_scale_pct.default);
        if (schema.settler_count?.default != null) setSettlerCount(schema.settler_count.default);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [presetId]);

  const schema: LabOverrideSchema = preset?.override_schema ?? {};

  const startLab = useCallback(async () => {
    if (!preset) return;
    setBusy(true);
    setError(null);
    try {
      const overrides: Record<string, number> = {
        map_scale_pct: mapScalePct,
        cash_scale_pct: cashScalePct,
        sim_speed: simSpeed,
      };
      if (settlerCount != null && schema.settler_count) {
        overrides.settler_count = settlerCount;
      }
      const r = await fetch("/api/engine/labs/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preset_id: preset.id,
          seed,
          overrides,
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      router.push("/labs/run");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [preset, seed, mapScalePct, cashScalePct, settlerCount, simSpeed, schema.settler_count, router]);

  if (!presetId) {
    return (
      <main className="realm-shell realm-app realm-labs-launch">
        <p className="realm-error">Pick a preset from the catalog.</p>
        <Link href="/labs">← Labs catalog</Link>
      </main>
    );
  }

  return (
    <main className="realm-shell realm-app realm-labs-launch">
      <header className="realm-labs-launch__header">
        <Link href="/labs" className="realm-labs-hub__back">
          ← Catalog
        </Link>
        {loading ? (
          <h1 className="realm-labs-hub__title">Loading…</h1>
        ) : preset ? (
          <>
            <h1 className="realm-labs-hub__title">{preset.title}</h1>
            <p className="realm-help">{preset.description}</p>
            <p className="realm-help">
              {preset.category} · {preset.grid_label} · {preset.base}
              {preset.tags.length > 0 ? ` · ${preset.tags.slice(0, 5).join(", ")}` : ""}
            </p>
          </>
        ) : null}
      </header>

      {error ? (
        <div className="realm-error" role="alert">
          {error}
        </div>
      ) : null}

      {preset && !loading ? (
        <section className="realm-labs-launch__tuning">
          <h2 className="realm-section-title">Run tuning</h2>

          <label className="realm-labs-launch__field">
            <span>Seed</span>
            <input
              type="number"
              className="realm-input"
              min={schema.seed?.min ?? 1}
              max={schema.seed?.max ?? 999999}
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
            />
          </label>

          <label className="realm-labs-launch__field">
            <span>Map scale ({mapScalePct}%)</span>
            <input
              type="range"
              min={schema.map_scale_pct?.min ?? 50}
              max={schema.map_scale_pct?.max ?? 150}
              step={schema.map_scale_pct?.step ?? 10}
              value={mapScalePct}
              onChange={(e) => setMapScalePct(Number(e.target.value))}
            />
          </label>

          <label className="realm-labs-launch__field">
            <span>Starting cash ({cashScalePct}%)</span>
            <input
              type="range"
              min={schema.cash_scale_pct?.min ?? 25}
              max={schema.cash_scale_pct?.max ?? 400}
              step={schema.cash_scale_pct?.step ?? 25}
              value={cashScalePct}
              onChange={(e) => setCashScalePct(Number(e.target.value))}
            />
          </label>

          {schema.settler_count ? (
            <label className="realm-labs-launch__field">
              <span>Settlers ({settlerCount ?? schema.settler_count.default})</span>
              <input
                type="range"
                min={schema.settler_count.min ?? 0}
                max={schema.settler_count.max ?? 80}
                value={settlerCount ?? schema.settler_count.default ?? 0}
                onChange={(e) => setSettlerCount(Number(e.target.value))}
              />
            </label>
          ) : null}

          <label className="realm-labs-launch__field">
            <span>Sim speed</span>
            <select
              className="realm-input"
              value={simSpeed}
              onChange={(e) => setSimSpeed(Number(e.target.value))}
            >
              <option value={0}>Slow</option>
              <option value={1}>Normal</option>
              <option value={2}>Fast</option>
            </select>
          </label>

          <div className="realm-labs-launch__actions">
            <button type="button" className="realm-btn realm-btn--primary" disabled={busy} onClick={() => void startLab()}>
              {busy ? "Starting…" : "Start lab"}
            </button>
            <Link href="/labs" className="realm-btn realm-btn--ghost">
              Cancel
            </Link>
          </div>
        </section>
      ) : null}
    </main>
  );
}

export default function LabsLaunchPage() {
  return (
    <Suspense fallback={<main className="realm-shell realm-app realm-labs-launch">Loading…</main>}>
      <LabsLaunchInner />
    </Suspense>
  );
}
