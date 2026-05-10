"use client";

import {
  CartesianGrid,
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

  const label = displayMaterial(sym || "—");

  if (data.length < 1) {
    return (
      <div className="realm-chart-empty" role="status">
        <p className="realm-help" style={{ margin: 0 }}>
          No market snapshots yet. Advance the simulation (header <strong>Run</strong> / speed controls) so ticks record best bid and ask for watched materials —
          the chart will fill in here.
        </p>
      </div>
    );
  }

  const hasSeries = data.some((d) => Number.isFinite(d.ask) || Number.isFinite(d.bid));
  if (!hasSeries) {
    return (
      <div className="realm-chart-empty" role="status">
        <p className="realm-help" style={{ margin: 0 }}>
          No bid or ask prints for <strong>{label}</strong> in recorded history yet. Run the clock or place orders so the book
          has resting liquidity for this symbol.
        </p>
      </div>
    );
  }

  const last = data[data.length - 1];
  const lastAsk = last && Number.isFinite(last.ask) ? last.ask : null;
  const lastBid = last && Number.isFinite(last.bid) ? last.bid : null;
  const spreadCents =
    lastAsk != null && lastBid != null && lastAsk >= lastBid ? lastAsk - lastBid : null;

  return (
    <div>
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 10, left: 0, bottom: 4 }}>
        <CartesianGrid
          stroke="rgba(107, 90, 138, 0.22)"
          strokeDasharray="4 6"
          vertical={false}
        />
        <XAxis
          dataKey="tick"
          tick={{ fontSize: 11, fill: "#a894c4" }}
          stroke="rgba(107, 90, 138, 0.5)"
          label={{ value: "World tick", position: "insideBottom", offset: -4, fill: "#8a7a98", fontSize: 12 }}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#a894c4" }}
          width={44}
          domain={["auto", "auto"]}
          stroke="rgba(107, 90, 138, 0.5)"
          tickFormatter={(v) => `$${(Number(v) / 100).toFixed(2)}`}
          label={{ value: "$/unit", angle: -90, position: "insideLeft", fill: "#8a7a98", fontSize: 12 }}
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
          labelFormatter={(tick) => `Tick ${tick}`}
          formatter={(value: unknown, name: unknown) => {
            const n = typeof value === "number" ? value : Number(value);
            const labelStr = typeof name === "string" ? name : String(name);
            if (value == null || !Number.isFinite(n)) return ["—", labelStr];
            return [`$${(n / 100).toFixed(2)}/u`, labelStr];
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
    {last ? (
      <p className="realm-help" style={{ margin: "8px 0 0", fontSize: 12 }}>
        Last snapshot tick <strong>{last.tick}</strong>
        {spreadCents != null ? (
          <>
            {" "}
            · spread <strong>${(spreadCents / 100).toFixed(2)}</strong>
          </>
        ) : null}
        {lastAsk != null ? (
          <>
            {" "}
            · ask <strong>${(lastAsk / 100).toFixed(2)}</strong>
          </>
        ) : null}
        {lastBid != null ? (
          <>
            {" "}
            · bid <strong>${(lastBid / 100).toFixed(2)}</strong>
          </>
        ) : null}
      </p>
    ) : null}
    </div>
  );
}
