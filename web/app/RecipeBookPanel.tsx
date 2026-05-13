"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { displayMaterial } from "./formatters";

type RecipeBookRow = {
  mineral: string;
  stage: number;
  max_stage: number;
  last_hint: string;
};

type AssayJob = {
  id: string;
  party: string;
  plot_id: string;
  mineral: string;
  stage_at_submit: number;
  started_at_tick: number;
  completes_at_tick: number;
};

type AssayBookResponse = {
  known: string[];
  progress: RecipeBookRow[];
  active_jobs: AssayJob[];
};

type RecipeBookPanelProps = {
  /** Player's currently known recipe ids — snapshot from /world (or omit to fetch /assay/book). */
  knownRecipeIds?: readonly string[];
  /** Optional override for the player's party id (e.g. ``"player"``). */
  party?: string;
  /** Solo dev origin for the realm engine. */
  apiBase?: string;
  /** Optional: callback so the parent can refresh world state after a successful assay. */
  onAssaySubmitted?: () => void;
};

const ASSAY_RECIPES_BY_MINERAL: Record<string, readonly string[]> = {
  sulfur_ore: ["mine_sulfur_ore", "hand_mine_sulfur", "refine_sulfur", "make_sulfuric_acid"],
  saltpeter_ore: ["mine_saltpeter", "refine_saltpeter", "make_gunpowder"],
  tin_ore: ["mine_tin_ore", "hand_mine_tin", "smelt_tin", "make_bronze"],
  lead_ore: ["mine_lead_ore", "smelt_lead"],
  phosphate_ore: ["mine_phosphate", "process_phosphate"],
  raw_silica: ["mine_raw_silica", "fuse_silica"],
  platinum_ore: ["mine_platinum", "refine_platinum"],
  oil_shale: ["mine_oil_shale", "process_shale"],
  rare_earth_ore: ["mine_rare_earth"],
};

function stagePill(stage: number, maxStage: number): { bg: string; fg: string; label: string } {
  if (stage >= maxStage) return { bg: "rgba(96, 213, 159, 0.25)", fg: "#9defc6", label: `${stage}/${maxStage} unlocked` };
  if (stage >= 1) return { bg: "rgba(255, 209, 102, 0.18)", fg: "#ffe8a6", label: `${stage}/${maxStage}` };
  return { bg: "rgba(120, 132, 156, 0.18)", fg: "#9aa3b5", label: `0/${maxStage}` };
}

export function RecipeBookPanel(props: RecipeBookPanelProps) {
  const apiBase = props.apiBase ?? "/api/engine";
  const party = props.party ?? "player";
  const [book, setBook] = useState<AssayBookResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  const fetchBook = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${apiBase}/assay/book?party=${encodeURIComponent(party)}`);
      if (!r.ok) {
        throw new Error(`HTTP ${r.status}`);
      }
      const data = (await r.json()) as AssayBookResponse;
      setBook(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [apiBase, party]);

  useEffect(() => {
    void fetchBook();
  }, [fetchBook]);

  const knownIds = useMemo(() => book?.known ?? props.knownRecipeIds ?? [], [book?.known, props.knownRecipeIds]);

  const assayAgain = useCallback(
    async (plotId: string, mineralId: string) => {
      setPending(`${plotId}|${mineralId}`);
      setError(null);
      try {
        const r = await fetch(
          `${apiBase}/assay?party=${encodeURIComponent(party)}&plot_id=${encodeURIComponent(plotId)}&mineral_id=${encodeURIComponent(mineralId)}`,
          { method: "POST" },
        );
        if (!r.ok) {
          const detail = await r.json().catch(() => null);
          throw new Error(detail?.detail ?? `HTTP ${r.status}`);
        }
        await fetchBook();
        props.onAssaySubmitted?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setPending(null);
      }
    },
    [apiBase, fetchBook, party, props],
  );

  const knownByMineral = useMemo(() => {
    const sets = new Map<string, Set<string>>();
    for (const [mineral, recipes] of Object.entries(ASSAY_RECIPES_BY_MINERAL)) {
      sets.set(mineral, new Set(recipes.filter((r) => knownIds.includes(r))));
    }
    return sets;
  }, [knownIds]);

  return (
    <div className="realm-recipe-book">
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <h3 className="realm-section-title">Recipe book & assay</h3>
        <span style={{ fontSize: 11, opacity: 0.65 }}>
          {knownIds.length} known recipes · {book?.active_jobs.length ?? 0} assay in progress
        </span>
        <button
          type="button"
          className="realm-btn realm-btn--secondary"
          style={{ marginLeft: "auto", fontSize: 11, padding: "4px 10px" }}
          onClick={() => void fetchBook()}
          disabled={loading}
        >
          {loading ? "…" : "Refresh"}
        </button>
      </div>

      {error ? (
        <p className="realm-help" style={{ color: "#ff8c8c", marginTop: 6 }}>
          {error}
        </p>
      ) : null}

      <p className="realm-help" style={{ marginTop: 6, marginBottom: 8 }}>
        Tier-1 recipes are open to everyone. Tier-2/Tier-3 are gated by <strong>assay</strong> — three successful attempts
        on a mineral-rich plot ($5 each, one game-day) unlock the full chain.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <div>
          <SectionLabel>Known recipes</SectionLabel>
          {knownIds.length === 0 ? (
            <p className="realm-help" style={{ marginTop: 4 }}>None yet.</p>
          ) : (
            <ul className="realm-recipe-book__list" style={{ maxHeight: 180, overflowY: "auto" }}>
              {[...knownIds].sort().map((rid) => (
                <li key={rid} style={{ fontSize: 12, lineHeight: 1.35 }}>
                  <code>{rid}</code>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <SectionLabel>Assay progress</SectionLabel>
          {(book?.progress ?? []).length === 0 ? (
            <p className="realm-help" style={{ marginTop: 4 }}>
              No assays attempted. Build an <code>assay_lab</code> on a Tier-2-rich plot to start.
            </p>
          ) : (
            <ul className="realm-recipe-book__list" style={{ maxHeight: 180, overflowY: "auto" }}>
              {(book?.progress ?? []).map((row) => {
                const pill = stagePill(row.stage, row.max_stage);
                const minedSet = knownByMineral.get(row.mineral);
                const unlocked = minedSet ? minedSet.size : 0;
                return (
                  <li key={row.mineral} style={{ marginBottom: 8, fontSize: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <strong>{displayMaterial(row.mineral)}</strong>
                      <span
                        style={{
                          fontSize: 10,
                          padding: "2px 6px",
                          borderRadius: 4,
                          background: pill.bg,
                          color: pill.fg,
                        }}
                      >
                        {pill.label}
                      </span>
                      {unlocked > 0 ? (
                        <span style={{ fontSize: 10, opacity: 0.65 }}>· {unlocked} recipe(s) unlocked</span>
                      ) : null}
                    </div>
                    {row.last_hint ? (
                      <p
                        className="realm-help"
                        style={{ margin: "4px 0 0", fontSize: 11, lineHeight: 1.4 }}
                      >
                        {row.last_hint}
                      </p>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {(book?.active_jobs ?? []).length > 0 ? (
        <div style={{ marginTop: 10 }}>
          <SectionLabel>In-flight assays</SectionLabel>
          <ul className="realm-recipe-book__list" style={{ marginTop: 4 }}>
            {(book?.active_jobs ?? []).map((j) => (
              <li key={j.id} style={{ fontSize: 12, marginBottom: 4 }}>
                <code>{j.id}</code> · {displayMaterial(j.mineral)} on{" "}
                <code>{j.plot_id}</code> · completes tick <strong>{j.completes_at_tick}</strong>
                <button
                  type="button"
                  className="realm-btn realm-btn--secondary"
                  style={{ marginLeft: 8, fontSize: 10, padding: "2px 8px", opacity: 0.7 }}
                  disabled
                  title="One assay per mineral may run at a time"
                >
                  pending
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {pending ? (
        <p className="realm-help" style={{ marginTop: 6, fontSize: 11 }}>
          submitting {pending}…
        </p>
      ) : null}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 10,
        textTransform: "uppercase",
        letterSpacing: 1,
        opacity: 0.55,
        marginBottom: 4,
      }}
    >
      {children}
    </div>
  );
}
