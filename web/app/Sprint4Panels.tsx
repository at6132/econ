/**
 * Sprint 4 UI panels — minimal but functional.
 *
 * Renders four discrete sections the player can interact with:
 *  - Intelligence  : survey-report market (browse / buy / your owned reports)
 *  - Analytics     : purchase analytics products, view past purchases
 *  - Alerts        : configure price alerts (passive feed entries on trigger)
 *  - Forwards      : forward contracts (propose / accept / deliver)
 *
 * The component is intentionally self-contained: it fetches the public
 * world snapshot from `/api/engine/world` whenever the user takes an
 * action, so the parent page.tsx does not need to thread refresh hooks
 * through. The presentation style mirrors the dense data-UI used by the
 * rest of the app (no big visual flourish).
 */

"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";

type ApiBase = string;

type IntelListing = {
  listing_id: string;
  seller: string;
  report_id: string;
  plot_id: string;
  survey_type: "standard" | "deep" | string;
  is_deep: boolean;
  conducted_at_tick: number;
  ask_price_cents: number;
  listed_at_tick: number;
};

type OwnedReport = {
  report_id: string;
  plot_id: string;
  conducted_by: string;
  conducted_at_tick: number;
  survey_type: string;
  is_deep: boolean;
  grades: Record<string, number>;
};

type AnalyticsPurchase = {
  tick: number;
  party: string;
  product: string;
  params: Record<string, unknown>;
  cost_cents: number;
  summary: string;
  data: unknown;
};

type PriceAlert = {
  alert_id: string;
  material: string;
  condition: "below" | "above";
  threshold_cents: number;
  triggered_at_tick: number | null;
  active: boolean;
};

type ForwardContract = {
  contract_id?: string;
  kind: string;
  seller: string;
  buyer: string;
  material: string;
  qty: number;
  price_per_unit_cents: number;
  delivery_tick: number;
  deposit_cents: number;
  status: string;
  created_at_tick?: number;
};

export type Sprint4Snapshot = {
  tick: number;
  intel_listings: IntelListing[];
  player_owned_reports: OwnedReport[];
  analytics_purchases: AnalyticsPurchase[];
  player_price_alerts: PriceAlert[];
  forward_contracts: ForwardContract[];
};

function formatUsdFromCents(cents: number | null | undefined): string {
  if (cents == null) return "—";
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const dollars = Math.floor(abs / 100);
  const rem = abs % 100;
  return `${sign}$${dollars.toLocaleString()}.${rem.toString().padStart(2, "0")}`;
}

const sectionStyle: CSSProperties = {
  marginBottom: 18,
  padding: "10px 12px",
  background: "var(--realm-panel-2, #1a1d24)",
  border: "1px solid var(--realm-border, #2a2f3a)",
  borderRadius: 6,
};

const titleStyle: CSSProperties = {
  margin: "0 0 8px 0",
  fontSize: 13,
  fontWeight: 700,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  color: "var(--realm-fg-soft, #c5cad5)",
};

const helpStyle: CSSProperties = {
  fontSize: 12,
  lineHeight: 1.4,
  margin: "0 0 8px 0",
  color: "var(--realm-fg-muted, #8a92a3)",
};

const tableStyle: CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 12,
};

const thStyle: CSSProperties = {
  textAlign: "left",
  padding: "4px 6px",
  borderBottom: "1px solid var(--realm-border, #2a2f3a)",
  fontWeight: 600,
};

const tdStyle: CSSProperties = {
  padding: "3px 6px",
  borderBottom: "1px solid var(--realm-border, #20242c)",
};

const inputStyle: CSSProperties = {
  background: "var(--realm-panel-1, #20242c)",
  color: "var(--realm-fg, #e7e9ee)",
  border: "1px solid var(--realm-border, #2a2f3a)",
  padding: "3px 6px",
  fontSize: 12,
  borderRadius: 4,
};

const btnStyle: CSSProperties = {
  background: "var(--realm-accent, #4a8cf7)",
  color: "#0b0d12",
  border: "none",
  borderRadius: 4,
  padding: "3px 8px",
  fontSize: 12,
  cursor: "pointer",
};

const ghostBtnStyle: CSSProperties = {
  ...btnStyle,
  background: "transparent",
  color: "var(--realm-fg, #e7e9ee)",
  border: "1px solid var(--realm-border, #2a2f3a)",
};

// ────────────────────────────────────────────────────────────────────────
// Intelligence panel (survey-report market)
// ────────────────────────────────────────────────────────────────────────

function IntelligenceSection({
  snap,
  apiBase,
  onMutate,
}: {
  snap: Sprint4Snapshot;
  apiBase: ApiBase;
  onMutate: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function buyListing(listingId: string) {
    setBusy(true);
    try {
      await fetch(`${apiBase}/intel/buy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ buyer: "player", listing_id: listingId }),
      });
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  const listings = snap.intel_listings ?? [];
  const owned = snap.player_owned_reports ?? [];

  return (
    <div style={sectionStyle}>
      <h3 style={titleStyle}>Intelligence — survey reports</h3>
      <p style={helpStyle}>
        Survey reports are tradeable documents. Listed reports show the plot id and
        survey type only — the grades are revealed once you own the report.
      </p>
      {listings.length === 0 ? (
        <p style={helpStyle}>No reports currently listed on the intelligence market.</p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Listing</th>
              <th style={thStyle}>Plot</th>
              <th style={thStyle}>Type</th>
              <th style={thStyle}>Seller</th>
              <th style={thStyle}>Conducted</th>
              <th style={thStyle}>Ask</th>
              <th style={thStyle}></th>
            </tr>
          </thead>
          <tbody>
            {listings.slice(0, 15).map((row) => (
              <tr key={row.listing_id}>
                <td style={tdStyle}>{row.listing_id}</td>
                <td style={tdStyle}>{row.plot_id}</td>
                <td style={tdStyle}>{row.is_deep ? "deep" : "standard"}</td>
                <td style={tdStyle}>{row.seller}</td>
                <td style={tdStyle}>t{row.conducted_at_tick}</td>
                <td style={tdStyle}>{formatUsdFromCents(row.ask_price_cents)}</td>
                <td style={tdStyle}>
                  <button
                    type="button"
                    style={btnStyle}
                    disabled={busy || row.seller === "player"}
                    onClick={() => void buyListing(row.listing_id)}
                  >
                    Buy
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h4 style={{ ...titleStyle, fontSize: 12, marginTop: 14 }}>
        Your reports ({owned.length})
      </h4>
      {owned.length === 0 ? (
        <p style={helpStyle}>You don&apos;t own any survey reports yet.</p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Report</th>
              <th style={thStyle}>Plot</th>
              <th style={thStyle}>Type</th>
              <th style={thStyle}>Top grades</th>
            </tr>
          </thead>
          <tbody>
            {owned.slice(0, 20).map((rep) => {
              const top = Object.entries(rep.grades)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 3)
                .map(([k, v]) => `${k.replace("_grade", "")} ${v.toFixed(2)}`)
                .join(", ");
              return (
                <tr key={rep.report_id}>
                  <td style={tdStyle}>{rep.report_id}</td>
                  <td style={tdStyle}>{rep.plot_id}</td>
                  <td style={tdStyle}>{rep.is_deep ? "deep" : "standard"}</td>
                  <td style={tdStyle}>{top}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Analytics panel (purchasable signals)
// ────────────────────────────────────────────────────────────────────────

const ANALYTICS_PRODUCTS: { id: string; label: string; cost_cents: number; description: string; needsMaterial?: boolean; needsRegion?: boolean; needsParty?: boolean }[] = [
  {
    id: "price_history",
    label: "Price history (30 days)",
    cost_cents: 300,
    description: "Best-ask snapshots for the last 30 game-days.",
    needsMaterial: true,
  },
  {
    id: "regional_survey",
    label: "Regional survey aggregate",
    cost_cents: 500,
    description: "Average grade for a mineral across a region.",
    needsMaterial: true,
    needsRegion: true,
  },
  {
    id: "party_volume",
    label: "Party trade volume",
    cost_cents: 800,
    description: "Categorical buy/sell signals for a party (last 7 days).",
    needsParty: true,
  },
  {
    id: "supply_shortage",
    label: "Supply shortage alert",
    cost_cents: 400,
    description: "Materials with <10 ask units on the order book.",
  },
];

function AnalyticsSection({
  snap,
  apiBase,
  onMutate,
}: {
  snap: Sprint4Snapshot;
  apiBase: ApiBase;
  onMutate: () => void;
}) {
  const [product, setProduct] = useState("price_history");
  const [material, setMaterial] = useState("coal");
  const [region, setRegion] = useState("r-0-0");
  const [partyId, setPartyId] = useState("settler_001");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AnalyticsPurchase | null>(null);

  const cfg = ANALYTICS_PRODUCTS.find((p) => p.id === product)!;

  async function purchase() {
    setBusy(true);
    setResult(null);
    try {
      const params: Record<string, string> = {};
      if (cfg.needsMaterial) {
        if (product === "regional_survey") params.mineral = material;
        else params.material = material;
      }
      if (cfg.needsRegion) params.region_id = region;
      if (cfg.needsParty) params.party_id = partyId;
      const r = await fetch(`${apiBase}/analytics/purchase`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ party: "player", product, params }),
      });
      const j = await r.json();
      if (j.ok) setResult(j as AnalyticsPurchase);
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={sectionStyle}>
      <h3 style={titleStyle}>Analytics — purchasable signals</h3>
      <p style={helpStyle}>
        Frontier Analytics Bureau sells data, not advice. Every product is a
        signal you interpret yourself.
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end", marginBottom: 8 }}>
        <label style={{ fontSize: 12 }}>
          Product
          <br />
          <select style={inputStyle} value={product} onChange={(e) => setProduct(e.target.value)}>
            {ANALYTICS_PRODUCTS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label} — {formatUsdFromCents(p.cost_cents)}
              </option>
            ))}
          </select>
        </label>
        {cfg.needsMaterial ? (
          <label style={{ fontSize: 12 }}>
            {product === "regional_survey" ? "Mineral" : "Material"}
            <br />
            <input style={inputStyle} value={material} onChange={(e) => setMaterial(e.target.value)} />
          </label>
        ) : null}
        {cfg.needsRegion ? (
          <label style={{ fontSize: 12 }}>
            Region id
            <br />
            <input style={inputStyle} value={region} onChange={(e) => setRegion(e.target.value)} />
          </label>
        ) : null}
        {cfg.needsParty ? (
          <label style={{ fontSize: 12 }}>
            Target party
            <br />
            <input style={inputStyle} value={partyId} onChange={(e) => setPartyId(e.target.value)} />
          </label>
        ) : null}
        <button type="button" style={btnStyle} disabled={busy} onClick={() => void purchase()}>
          Purchase
        </button>
      </div>

      <p style={helpStyle}>{cfg.description}</p>

      {result ? (
        <pre
          style={{
            margin: 0,
            padding: "8px 10px",
            background: "var(--realm-panel-1, #20242c)",
            borderRadius: 4,
            fontSize: 11,
            lineHeight: 1.4,
            maxHeight: 200,
            overflow: "auto",
            fontFamily: "var(--realm-mono, monospace)",
          }}
        >
          {JSON.stringify(result, null, 2)}
        </pre>
      ) : null}

      <h4 style={{ ...titleStyle, fontSize: 12, marginTop: 14 }}>Past purchases</h4>
      {snap.analytics_purchases.length === 0 ? (
        <p style={helpStyle}>No analytics purchases yet.</p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Tick</th>
              <th style={thStyle}>Product</th>
              <th style={thStyle}>Cost</th>
              <th style={thStyle}>Summary</th>
            </tr>
          </thead>
          <tbody>
            {snap.analytics_purchases.slice(-10).reverse().map((p, i) => (
              <tr key={`${p.tick}-${i}`}>
                <td style={tdStyle}>{p.tick}</td>
                <td style={tdStyle}>{p.product}</td>
                <td style={tdStyle}>{formatUsdFromCents(p.cost_cents)}</td>
                <td style={tdStyle}>{p.summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Alerts panel
// ────────────────────────────────────────────────────────────────────────

function AlertsSection({
  snap,
  apiBase,
  onMutate,
}: {
  snap: Sprint4Snapshot;
  apiBase: ApiBase;
  onMutate: () => void;
}) {
  const [material, setMaterial] = useState("coal");
  const [condition, setCondition] = useState<"below" | "above">("below");
  const [threshold, setThreshold] = useState("55");
  const [busy, setBusy] = useState(false);

  async function addAlert() {
    setBusy(true);
    try {
      await fetch(`${apiBase}/alerts/price`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          material,
          condition,
          threshold: Number.parseInt(threshold, 10),
        }),
      });
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  async function removeAlert(alertId: string) {
    setBusy(true);
    try {
      await fetch(`${apiBase}/alerts/price/${alertId}`, { method: "DELETE" });
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  const alerts = snap.player_price_alerts ?? [];

  return (
    <div style={sectionStyle}>
      <h3 style={titleStyle}>Price alerts</h3>
      <p style={helpStyle}>
        Configured alerts emit passively to your world feed when their threshold
        is crossed. No popups.
      </p>

      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 8 }}>
        <label style={{ fontSize: 12 }}>
          Material
          <br />
          <input style={inputStyle} value={material} onChange={(e) => setMaterial(e.target.value)} />
        </label>
        <label style={{ fontSize: 12 }}>
          Condition
          <br />
          <select style={inputStyle} value={condition} onChange={(e) => setCondition(e.target.value as "below" | "above")}>
            <option value="below">below</option>
            <option value="above">above</option>
          </select>
        </label>
        <label style={{ fontSize: 12 }}>
          Threshold (¢)
          <br />
          <input style={inputStyle} value={threshold} onChange={(e) => setThreshold(e.target.value)} />
        </label>
        <button type="button" style={btnStyle} disabled={busy} onClick={() => void addAlert()}>
          Add alert
        </button>
      </div>

      {alerts.length === 0 ? (
        <p style={helpStyle}>No active alerts.</p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Alert</th>
              <th style={thStyle}>Material</th>
              <th style={thStyle}>Condition</th>
              <th style={thStyle}>Threshold</th>
              <th style={thStyle}>Triggered</th>
              <th style={thStyle}></th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.alert_id}>
                <td style={tdStyle}>{a.alert_id}</td>
                <td style={tdStyle}>{a.material}</td>
                <td style={tdStyle}>{a.condition}</td>
                <td style={tdStyle}>{a.threshold_cents}¢</td>
                <td style={tdStyle}>{a.triggered_at_tick ?? "—"}</td>
                <td style={tdStyle}>
                  <button type="button" style={ghostBtnStyle} disabled={busy} onClick={() => void removeAlert(a.alert_id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Forward contracts panel
// ────────────────────────────────────────────────────────────────────────

function ForwardsSection({
  snap,
  apiBase,
  onMutate,
}: {
  snap: Sprint4Snapshot;
  apiBase: ApiBase;
  onMutate: () => void;
}) {
  // Phase 7A: pop hubs are gone — default to Kessler (consolidator) as a
  // common forward-buyer counterparty; the input still accepts any party id.
  const [buyer, setBuyer] = useState("genesis_consolidator");
  const [material, setMaterial] = useState("coal");
  const [qty, setQty] = useState("20");
  const [price, setPrice] = useState("80");
  const [deliveryTicksOut, setDeliveryTicksOut] = useState("2880");
  const [busy, setBusy] = useState(false);

  async function propose() {
    setBusy(true);
    try {
      await fetch(`${apiBase}/contracts/forward/propose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          seller: "player",
          buyer,
          material,
          qty: Number.parseInt(qty, 10),
          price_per_unit_cents: Number.parseInt(price, 10),
          delivery_tick: snap.tick + Number.parseInt(deliveryTicksOut, 10),
        }),
      });
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  async function accept(contractId: string) {
    setBusy(true);
    try {
      await fetch(`${apiBase}/contracts/forward/${contractId}/accept`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ party: "player" }),
      });
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  async function deliver(contractId: string) {
    setBusy(true);
    try {
      await fetch(`${apiBase}/contracts/forward/${contractId}/deliver`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ party: "player" }),
      });
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  const forwards = snap.forward_contracts ?? [];

  return (
    <div style={sectionStyle}>
      <h3 style={titleStyle}>Forward contracts</h3>
      <p style={helpStyle}>
        Lock in a price now, deliver later. The seller posts a 10% deposit that is
        forfeit on default. Buyers get certainty of supply; sellers get certainty
        of payment — at the cost of upside if spot moves their way.
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end", marginBottom: 8 }}>
        <label style={{ fontSize: 12 }}>
          Buyer
          <br />
          <input style={inputStyle} value={buyer} onChange={(e) => setBuyer(e.target.value)} />
        </label>
        <label style={{ fontSize: 12 }}>
          Material
          <br />
          <input style={inputStyle} value={material} onChange={(e) => setMaterial(e.target.value)} />
        </label>
        <label style={{ fontSize: 12 }}>
          Qty
          <br />
          <input style={inputStyle} value={qty} onChange={(e) => setQty(e.target.value)} />
        </label>
        <label style={{ fontSize: 12 }}>
          Price ¢/unit
          <br />
          <input style={inputStyle} value={price} onChange={(e) => setPrice(e.target.value)} />
        </label>
        <label style={{ fontSize: 12 }}>
          Delivery in N ticks
          <br />
          <input style={inputStyle} value={deliveryTicksOut} onChange={(e) => setDeliveryTicksOut(e.target.value)} />
        </label>
        <button type="button" style={btnStyle} disabled={busy} onClick={() => void propose()}>
          Propose forward
        </button>
      </div>

      {forwards.length === 0 ? (
        <p style={helpStyle}>No forward contracts involving you yet.</p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Contract</th>
              <th style={thStyle}>Status</th>
              <th style={thStyle}>Seller → Buyer</th>
              <th style={thStyle}>Material</th>
              <th style={thStyle}>Qty</th>
              <th style={thStyle}>Price</th>
              <th style={thStyle}>Deliver by</th>
              <th style={thStyle}>Deposit</th>
              <th style={thStyle}></th>
            </tr>
          </thead>
          <tbody>
            {forwards.map((c, i) => {
              const cid = String(c.contract_id ?? `unknown-${i}`);
              const youAreSeller = c.seller === "player";
              const youAreBuyer = c.buyer === "player";
              const canAccept = youAreBuyer && c.status === "proposed";
              const canDeliver = youAreSeller && c.status === "active" && snap.tick <= c.delivery_tick;
              return (
                <tr key={cid}>
                  <td style={tdStyle}>{cid}</td>
                  <td style={tdStyle}>{c.status}</td>
                  <td style={tdStyle}>
                    {c.seller} → {c.buyer}
                  </td>
                  <td style={tdStyle}>{c.material}</td>
                  <td style={tdStyle}>{c.qty}</td>
                  <td style={tdStyle}>{c.price_per_unit_cents}¢</td>
                  <td style={tdStyle}>t{c.delivery_tick}</td>
                  <td style={tdStyle}>{formatUsdFromCents(c.deposit_cents)}</td>
                  <td style={tdStyle}>
                    {canAccept ? (
                      <button type="button" style={btnStyle} disabled={busy} onClick={() => void accept(cid)}>
                        Accept
                      </button>
                    ) : null}
                    {canDeliver ? (
                      <button type="button" style={btnStyle} disabled={busy} onClick={() => void deliver(cid)}>
                        Deliver
                      </button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Public component
// ────────────────────────────────────────────────────────────────────────

export function Sprint4MarketSection({
  snap,
  apiBase,
  onMutate,
}: {
  snap: Sprint4Snapshot;
  apiBase: ApiBase;
  onMutate: () => void;
}) {
  return (
    <>
      <IntelligenceSection snap={snap} apiBase={apiBase} onMutate={onMutate} />
      <AnalyticsSection snap={snap} apiBase={apiBase} onMutate={onMutate} />
      <AlertsSection snap={snap} apiBase={apiBase} onMutate={onMutate} />
    </>
  );
}

export function Sprint4PactsSection({
  snap,
  apiBase,
  onMutate,
}: {
  snap: Sprint4Snapshot;
  apiBase: ApiBase;
  onMutate: () => void;
}) {
  return <ForwardsSection snap={snap} apiBase={apiBase} onMutate={onMutate} />;
}
