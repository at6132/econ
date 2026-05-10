"use client";

import {
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { displayMaterial } from "./formatters";

export type MarketHistorySnap = {
  tick: number;
  best_asks_cents: Record<string, number>;
  /** Highest resting limit bid (¢/u) per material, if any. */
  best_bids_cents?: Record<string, number>;
};

const ASK_STROKE = "#6ee7ff";
const BID_STROKE = "#ffd84a";

type Props = {
  history: MarketHistorySnap[];
  /** Engine material id (e.g. grain). Chart shows best ask + best bid for this symbol only. */
  symbol: string;
};

export function MarketHistoryChart({ history, symbol }: Props) {
  const sym = symbol.trim();
  const data = history.map((h) => {
    const asks = h.best_asks_cents ?? {};
    const bids = h.best_bids_cents ?? {};
    return {
      tick: h.tick,
      ask: asks[sym],
      bid: bids[sym],
    };
  });

  if (data.length < 1) {
    return (
      <p className="realm-help" style={{ margin: 0 }}>
        No market snapshots yet. The chart fills as the simulation runs (each tick records best bid/ask).
      </p>
    );
  }

  const label = displayMaterial(sym || "—");

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <XAxis
          dataKey="tick"
          tick={{ fontSize: 11, fill: "#a894c4" }}
          stroke="rgba(107, 90, 138, 0.5)"
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#a894c4" }}
          width={44}
          domain={["auto", "auto"]}
          stroke="rgba(107, 90, 138, 0.5)"
          tickFormatter={(v) => `$${(Number(v) / 100).toFixed(2)}`}
        />
        <Tooltip
          contentStyle={{
            background: "#12081f",
            border: "2px solid #000",
            borderRadius: 0,
            fontSize: 14,
            color: "#f4ead8",
            fontFamily: "VT323, ui-monospace, monospace",
          }}
          labelStyle={{ color: "#8a7a98" }}
          formatter={(value: unknown) => {
            const n = typeof value === "number" ? value : Number(value);
            if (value == null || !Number.isFinite(n)) return ["—", ""];
            return [`$${(n / 100).toFixed(2)}/u`, ""];
          }}
        />
        <Legend wrapperStyle={{ fontSize: 13, color: "#a894c4", fontFamily: "VT323, ui-monospace, monospace" }} />
        <Line
          type="monotone"
          dataKey="ask"
          name={`${label} · best ask`}
          stroke={ASK_STROKE}
          strokeWidth={2}
          dot={false}
          connectNulls
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="bid"
          name={`${label} · best bid`}
          stroke={BID_STROKE}
          strokeWidth={2}
          strokeDasharray="6 4"
          dot={false}
          connectNulls
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
