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
};

const SERIES = ["grain", "timber", "coal", "clay", "electricity"] as const;
const COLORS = ["#79c0ff", "#56d364", "#ffa657", "#d2a8ff", "#ff7b72"];

export function MarketHistoryChart({ history }: { history: MarketHistorySnap[] }) {
  const data = history.map((h) => {
    const row: Record<string, number | undefined> = { tick: h.tick };
    const asks = h.best_asks_cents ?? {};
    for (const m of SERIES) {
      row[m] = asks[m];
    }
    return row;
  });

  if (data.length < 1) {
    return (
      <p style={{ margin: 0, opacity: 0.7, fontSize: 12 }}>
        No market snapshots yet. Advance ticks to record best ask prices.
      </p>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <XAxis dataKey="tick" tick={{ fontSize: 10 }} />
        <YAxis tick={{ fontSize: 10 }} width={36} domain={["auto", "auto"]} />
        <Tooltip />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {SERIES.map((m, i) => (
          <Line
            key={m}
            type="monotone"
            dataKey={m}
            name={m}
            stroke={COLORS[i]}
            strokeWidth={2}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
