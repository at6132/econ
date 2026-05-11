export type EconomyMoodTone = "dormant" | "quiet" | "warming" | "alive";

export type EconomyMood = {
  tone: EconomyMoodTone;
  /** One-line status for the HUD — evokes empty economy waking up. */
  line: string;
};

type MoodInput = {
  tick: number;
  plotCount: number;
  claimedPlots: number;
  partyCount: number;
  productionRuns: number;
  shipmentsInFlight: number;
};

/**
 * Derives a short mood line from coarse world stats (no randomness).
 * Tuned for “empty economy → emergent activity” solo play.
 */
export function computeEconomyMood(w: MoodInput): EconomyMood {
  const { tick, plotCount, claimedPlots, partyCount, productionRuns, shipmentsInFlight } = w;
  const claimRatio = plotCount > 0 ? claimedPlots / plotCount : 0;
  const flow = productionRuns + shipmentsInFlight;

  if (tick < 12 && claimRatio < 0.04) {
    return {
      tone: "dormant",
      line: "Ledger mostly blank — the frontier is yours to price, route, and fill.",
    };
  }
  if (claimRatio < 0.07 && partyCount <= 3 && flow === 0) {
    return {
      tone: "quiet",
      line: "Whisper-thin market: a few claims, almost no convoys yet.",
    };
  }
  if (claimRatio < 0.22 && flow < 6) {
    return {
      tone: "warming",
      line: "Rails warming — workshops and shipments are starting to braid the map.",
    };
  }
  return {
    tone: "alive",
    line: "Dense flows — capital, matter, and contracts all moving at once.",
  };
}
