"use client";

import Link from "next/link";
import { useEffect } from "react";

import { REALM_LAST_MODE_STORAGE_KEY } from "./labsConstants";

export default function HomeLauncher() {
  useEffect(() => {
    try {
      localStorage.setItem(REALM_LAST_MODE_STORAGE_KEY, "frontier");
    } catch {
      /* ignore */
    }
  }, []);

  return (
    <main className="realm-shell realm-app realm-home">
      <div className="realm-home__inner">
        <header className="realm-home__header">
          <h1 className="realm-home__title">Realm</h1>
          <p className="realm-home__tagline">
            Player-run economy simulation — claim land, invent businesses, trade on emergent markets.
          </p>
        </header>

        <div className="realm-home__cards">
          <Link href="/play" className="realm-home__card realm-home__card--primary">
            <span className="realm-home__card-kicker">Campaign</span>
            <span className="realm-home__card-title">Play Frontier</span>
            <span className="realm-home__card-desc">
              Full solo slice — map, bazaar, contracts, chronicle saves. Continue your world or start fresh.
            </span>
          </Link>

          <Link href="/labs" className="realm-home__card">
            <span className="realm-home__card-kicker">Sandboxes</span>
            <span className="realm-home__card-title">Labs</span>
            <span className="realm-home__card-desc">
              200+ contained presets — strategy tests, market stress, social dynamics. Tune seed, map, and cash, then run.
            </span>
          </Link>
        </div>

        <p className="realm-home__foot realm-help">
          Same engine rules everywhere — conservation, determinism, geography matters.
        </p>
      </div>
    </main>
  );
}
