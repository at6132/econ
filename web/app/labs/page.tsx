"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { LabCategory, LabPresetSummary, LabsPresetsResponse } from "../labsTypes";

const PAGE_SIZE = 48;

const CATEGORIES: (LabCategory | "All")[] = [
  "All",
  "Strategy",
  "Markets",
  "Social",
  "Production",
  "Stress",
  "Tutorial",
];

export default function LabsCatalogPage() {
  const [presets, setPresets] = useState<LabPresetSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [category, setCategory] = useState<LabCategory | "All">("All");
  const [featuredOnly, setFeaturedOnly] = useState(false);
  const [q, setQ] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<{ total: number; featured: number } | null>(null);

  const fetchPage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        offset: String(offset),
        limit: String(PAGE_SIZE),
      });
      if (category !== "All") params.set("category", category);
      if (featuredOnly) params.set("featured_only", "true");
      if (q.trim()) params.set("q", q.trim());
      const r = await fetch(`/api/engine/labs/presets?${params.toString()}`);
      if (!r.ok) throw new Error(await r.text());
      const j = (await r.json()) as LabsPresetsResponse;
      setPresets(j.presets);
      setTotal(j.total);
      setStats(j.stats);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [offset, category, featuredOnly, q]);

  useEffect(() => {
    void fetchPage();
  }, [fetchPage]);

  useEffect(() => {
    setOffset(0);
  }, [category, featuredOnly, q]);

  const pageCount = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);
  const pageIndex = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <main className="realm-shell realm-app realm-labs-hub">
      <header className="realm-labs-hub__header">
        <div>
          <Link href="/" className="realm-labs-hub__back">
            ← Home
          </Link>
          <h1 className="realm-labs-hub__title">Labs</h1>
          <p className="realm-help">
            {stats
              ? `${stats.total} presets (${stats.featured} featured) — contained sandboxes for experiments.`
              : "Contained economic sandboxes for experiments."}
          </p>
        </div>
      </header>

      <div className="realm-labs-hub__toolbar">
        <input
          type="search"
          className="realm-input realm-labs-hub__search"
          placeholder="Search presets…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") setQ(searchInput);
          }}
        />
        <button type="button" className="realm-btn realm-btn--ghost" onClick={() => setQ(searchInput)}>
          Search
        </button>
        <label className="realm-labs-hub__featured">
          <input
            type="checkbox"
            checked={featuredOnly}
            onChange={(e) => setFeaturedOnly(e.target.checked)}
          />
          Featured only
        </label>
      </div>

      <div className="realm-labs-hub__layout">
        <nav className="realm-labs-hub__categories" aria-label="Categories">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              className={`realm-labs-hub__cat${category === c ? " realm-labs-hub__cat--active" : ""}`}
              onClick={() => setCategory(c)}
            >
              {c}
            </button>
          ))}
        </nav>

        <section className="realm-labs-hub__grid-wrap">
          {error ? (
            <div className="realm-error" role="alert">
              {error}
            </div>
          ) : null}
          {loading && presets.length === 0 ? (
            <p className="realm-help">Loading catalog…</p>
          ) : null}
          <div className="realm-labs-hub__grid">
            {presets.map((p) => (
              <Link key={p.id} href={`/labs/new?preset=${encodeURIComponent(p.id)}`} className="realm-labs-card">
                {p.featured ? <span className="realm-labs-card__badge">Featured</span> : null}
                <span className="realm-labs-card__category">{p.category}</span>
                <span className="realm-labs-card__title">{p.title}</span>
                <span className="realm-labs-card__desc">{p.description}</span>
                <span className="realm-labs-card__meta">
                  {p.grid_label} · {p.base}
                </span>
              </Link>
            ))}
          </div>
          {!loading && presets.length === 0 ? (
            <p className="realm-help">No presets match your filters.</p>
          ) : null}
          <div className="realm-labs-hub__pager">
            <button
              type="button"
              className="realm-btn realm-btn--ghost"
              disabled={offset <= 0 || loading}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            >
              Previous
            </button>
            <span className="realm-help">
              Page {pageIndex} of {pageCount} · {total} total
            </span>
            <button
              type="button"
              className="realm-btn realm-btn--ghost"
              disabled={offset + PAGE_SIZE >= total || loading}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
