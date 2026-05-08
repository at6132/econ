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
      <p className="realm-help" style={{ margin: 0 }}>
        No market snapshots yet. Advance ticks to record best ask prices.
      </p>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <XAxis
          dataKey="tick"
          tick={{ fontSize: 10, fill: "#9db0c4" }}
          stroke="rgba(120,160,200,0.25)"
        />
        <YAxis
          tick={{ fontSize: 10, fill: "#9db0c4" }}
          width={36}
          domain={["auto", "auto"]}
          stroke="rgba(120,160,200,0.25)"
        />
        <Tooltip
          contentStyle={{
            background: "#111822",
            border: "1px solid rgba(120,160,200,0.25)",
            borderRadius: 10,
            fontSize: 12,
            color: "#e8f0f8",
          }}
          labelStyle={{ color: "#6b7d92" }}
        />
        <Legend wrapperStyle={{ fontSize: 11, color: "#9db0c4" }} />
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
