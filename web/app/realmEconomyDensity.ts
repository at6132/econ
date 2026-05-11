export type EconomyDensityTone = "sparse" | "thin" | "developing" | "active";

export type EconomyDensity = {
  tone: EconomyDensityTone;
  /** Compact numeric snapshot (dense HUD). */
  facts: string;
  /** One sentence: where the sim sits vs “empty economy” (doc 01). */
  assessment: string;
};

type DensityInput = {
  tick: number;
  plotCount: number;
  claimedPlots: number;
  partyCount: number;
  productionRuns: number;
  shipmentsInFlight: number;
};

/**
 * Authoritative-world snapshot language — not flavor text.
 * Thresholds mirror the old mood helper but output is diagnostic.
 */
export function computeEconomyDensity(w: DensityInput): EconomyDensity {
  const { tick, plotCount, claimedPlots, partyCount, productionRuns, shipmentsInFlight } = w;
  const claimRatio = plotCount > 0 ? claimedPlots / plotCount : 0;
  const flow = productionRuns + shipmentsInFlight;

  const facts = `Plots titled ${claimedPlots}/${plotCount} · parties ${partyCount} · production ${productionRuns} · in transit ${shipmentsInFlight}`;

  if (tick < 12 && claimRatio < 0.04) {
    return {
      tone: "sparse",
      facts,
      assessment:
        "Cold start: geography is instantiated; ownership and economic flows are still largely undistributed.",
    };
  }
  if (claimRatio < 0.07 && partyCount <= 3 && flow === 0) {
    return {
      tone: "thin",
      facts,
      assessment: "Thin participation: some plots titled; production and logistics volumes negligible.",
    };
  }
  if (claimRatio < 0.22 && flow < 6) {
    return {
      tone: "developing",
      facts,
      assessment: "Developing flows: concurrent production and/or shipments visible across parties.",
    };
  }
  return {
    tone: "active",
    facts,
    assessment: "High concurrent activity — use Markets, Logistics, and Contracts for underlying detail.",
  };
}
