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

export type MarketHistorySnap = {
  tick: number;
  best_asks_cents: Record<string, number>;
  /** Highest resting limit bid (¢/u) per material, if any. */
  best_bids_cents?: Record<string, number>;
};

const SERIES = ["grain", "timber", "coal", "clay", "electricity"] as const;
const COLORS = ["#6ee7ff", "#7bed9f", "#ffd84a", "#c9a8ff", "#ff8a7a"];

export function MarketHistoryChart({ history }: { history: MarketHistorySnap[] }) {
  const data = history.map((h) => {
    const row: Record<string, number | undefined> = { tick: h.tick };
    const asks = h.best_asks_cents ?? {};
    const bids = h.best_bids_cents ?? {};
    for (const m of SERIES) {
      row[m] = asks[m];
      row[`${m}_bid`] = bids[m];
    }
    return row;
  });

  if (data.length < 1) {
    return (
      <p className="realm-help" style={{ margin: 0 }}>
        No market snapshots yet. Advance ticks to record best ask and bid prices.
      </p>
    );
  }

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
          width={40}
          domain={["auto", "auto"]}
          stroke="rgba(107, 90, 138, 0.5)"
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
        />
        <Legend wrapperStyle={{ fontSize: 13, color: "#a894c4", fontFamily: "VT323, ui-monospace, monospace" }} />
        {SERIES.map((m, i) => (
          <Line
            key={`ask-${m}`}
            type="monotone"
            dataKey={m}
            name={`${m} ask`}
            stroke={COLORS[i]}
            strokeWidth={2}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        ))}
        {SERIES.map((m, i) => (
          <Line
            key={`bid-${m}`}
            type="monotone"
            dataKey={`${m}_bid`}
            name={`${m} bid`}
            stroke={COLORS[i]}
            strokeWidth={1.5}
            strokeDasharray="5 4"
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
