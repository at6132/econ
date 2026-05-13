/**
 * Sprint 5 UI panels — business identity, sub-accounts, NPC bank.
 *
 * Renders three discrete sections:
 *  - Identity       : register a business name (one-time, 1,000c fee)
 *  - Accounts       : list sub-accounts, transfer between them, create new
 *  - Bank           : rates by reputation tier, active loans, apply / repay
 *
 * Self-contained: fetches the public world snapshot on every mutation.
 */

"use client";

import { useMemo, useState, type CSSProperties } from "react";

type ApiBase = string;

type BusinessRecord = {
  party_id: string;
  business_name: string;
  description: string;
  registered_at_tick: number;
};

type AccountView = {
  label: string;
  account_id: string;
  balance_cents: number;
  is_primary: boolean;
  pnl_7day: { credits_cents: number; debits_cents: number; net_cents: number };
};

type BankRateTier = {
  tier: string;
  min_honored: number;
  max_honored: number | null;
  rate_bps_per_cycle: number;
  rate_pct_per_cycle: number;
  max_principal_cents: number;
  current_for_party: boolean;
};

type BankRatesView = {
  tiers: BankRateTier[];
  cycle_ticks: number;
  honored_for_party: number;
  current_tier: string;
};

type BankLoan = {
  id: string;
  kind: string;
  status: string;
  lender: string;
  borrower: string;
  principal_cents: number;
  interest_rate_bps: number;
  cycle_ticks: number;
  num_cycles: number;
  payments_made: number;
  missed_payments?: number;
  next_due_tick: number;
  collateral_plot_id?: string | null;
  tier_at_origination?: string;
};

export type Sprint5Snapshot = {
  tick: number;
  business_registry: Record<string, BusinessRecord>;
  player_accounts: AccountView[];
  bank_rates: BankRatesView | null;
  bank_loans: BankLoan[];
  bank_plot_id: string | null;
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

const pillStyle: CSSProperties = {
  display: "inline-block",
  padding: "1px 6px",
  borderRadius: 8,
  fontSize: 11,
  background: "var(--realm-panel-1, #20242c)",
  color: "var(--realm-fg, #e7e9ee)",
  border: "1px solid var(--realm-border, #2a2f3a)",
};

// ────────────────────────────────────────────────────────────────────────
// Identity panel
// ────────────────────────────────────────────────────────────────────────

function IdentitySection({
  snap,
  apiBase,
  onMutate,
}: {
  snap: Sprint5Snapshot;
  apiBase: ApiBase;
  onMutate: () => void;
}) {
  const playerRecord = snap.business_registry?.player;
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function register() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/business/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ party: "player", name: name.trim(), description: desc }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(typeof body.detail === "string" ? body.detail : "registration failed");
        return;
      }
      setName("");
      setDesc("");
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={sectionStyle}>
      <h3 style={titleStyle}>Business identity</h3>
      {playerRecord ? (
        <div style={{ fontSize: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>
            {playerRecord.business_name}
            <span style={{ ...pillStyle, marginLeft: 8 }}>
              Est. t{playerRecord.registered_at_tick}
            </span>
          </div>
          {playerRecord.description ? (
            <div style={{ color: "var(--realm-fg-muted, #8a92a3)" }}>
              &ldquo;{playerRecord.description}&rdquo;
            </div>
          ) : null}
        </div>
      ) : (
        <>
          <p style={helpStyle}>
            Register a business name (1,000¢ one-time fee). Your name flows through every
            market event, contract, and feed entry. 3–40 characters; letters, digits, spaces,
            and apostrophes / periods / ampersands.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            <input
              style={{ ...inputStyle, minWidth: 200 }}
              placeholder="Business name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={40}
            />
            <input
              style={{ ...inputStyle, flex: 1, minWidth: 240 }}
              placeholder="Description (optional)"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              maxLength={240}
            />
            <button
              type="button"
              style={btnStyle}
              disabled={busy || name.trim().length < 3}
              onClick={() => void register()}
            >
              Register (1,000¢)
            </button>
          </div>
          {error ? (
            <div style={{ marginTop: 6, color: "#e07a7a", fontSize: 12 }}>{error}</div>
          ) : null}
        </>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Accounts panel
// ────────────────────────────────────────────────────────────────────────

function AccountsSection({
  snap,
  apiBase,
  onMutate,
}: {
  snap: Sprint5Snapshot;
  apiBase: ApiBase;
  onMutate: () => void;
}) {
  const accounts = snap.player_accounts ?? [];
  const [newLabel, setNewLabel] = useState("");
  const [from, setFrom] = useState("cash");
  const [to, setTo] = useState("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const labels = useMemo(() => accounts.map((a) => a.label), [accounts]);

  async function createAccount() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/accounts/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ party: "player", label: newLabel.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(typeof body.detail === "string" ? body.detail : "create failed");
        return;
      }
      setNewLabel("");
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  async function doTransfer() {
    setBusy(true);
    setError(null);
    try {
      const cents = Math.round(Number(amount));
      if (!Number.isFinite(cents) || cents <= 0) {
        setError("amount must be a positive number of cents");
        return;
      }
      const res = await fetch(`${apiBase}/accounts/transfer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ party: "player", from_label: from, to_label: to, cents }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(typeof body.detail === "string" ? body.detail : "transfer failed");
        return;
      }
      setAmount("");
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={sectionStyle}>
      <h3 style={titleStyle}>Accounts</h3>
      <p style={helpStyle}>
        Operate your money across multiple labelled accounts. Transfers between your own
        accounts are instant and free. 7-day P&amp;L is shown per account.
      </p>
      {accounts.length === 0 ? (
        <p style={helpStyle}>No accounts.</p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Label</th>
              <th style={thStyle}>Balance</th>
              <th style={thStyle}>7d in</th>
              <th style={thStyle}>7d out</th>
              <th style={thStyle}>7d net</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((a) => (
              <tr key={a.account_id}>
                <td style={tdStyle}>
                  {a.label} {a.is_primary ? <span style={pillStyle}>primary</span> : null}
                </td>
                <td style={tdStyle}>{formatUsdFromCents(a.balance_cents)}</td>
                <td style={tdStyle}>{formatUsdFromCents(a.pnl_7day?.credits_cents)}</td>
                <td style={tdStyle}>{formatUsdFromCents(a.pnl_7day?.debits_cents)}</td>
                <td
                  style={{
                    ...tdStyle,
                    color: (a.pnl_7day?.net_cents ?? 0) >= 0 ? "#7ac98a" : "#e07a7a",
                  }}
                >
                  {formatUsdFromCents(a.pnl_7day?.net_cents)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div
        style={{
          marginTop: 10,
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
          alignItems: "center",
        }}
      >
        <input
          style={{ ...inputStyle, minWidth: 130 }}
          placeholder="New label (e.g. reserve)"
          value={newLabel}
          onChange={(e) => setNewLabel(e.target.value)}
          maxLength={24}
        />
        <button
          type="button"
          style={btnStyle}
          disabled={busy || newLabel.trim().length < 2}
          onClick={() => void createAccount()}
        >
          New account
        </button>
      </div>
      <div
        style={{
          marginTop: 8,
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
          alignItems: "center",
        }}
      >
        <select style={inputStyle} value={from} onChange={(e) => setFrom(e.target.value)}>
          {labels.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <span style={{ fontSize: 12 }}>→</span>
        <select style={inputStyle} value={to} onChange={(e) => setTo(e.target.value)}>
          <option value="">choose…</option>
          {labels
            .filter((l) => l !== from)
            .map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
        </select>
        <input
          style={{ ...inputStyle, width: 110 }}
          placeholder="amount (¢)"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          inputMode="numeric"
        />
        <button
          type="button"
          style={ghostBtnStyle}
          disabled={busy || !to || !amount}
          onClick={() => void doTransfer()}
        >
          Transfer
        </button>
      </div>
      {error ? <div style={{ marginTop: 6, color: "#e07a7a", fontSize: 12 }}>{error}</div> : null}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Bank panel
// ────────────────────────────────────────────────────────────────────────

function BankSection({
  snap,
  apiBase,
  onMutate,
}: {
  snap: Sprint5Snapshot;
  apiBase: ApiBase;
  onMutate: () => void;
}) {
  const rates = snap.bank_rates;
  const loans = snap.bank_loans ?? [];
  const [principal, setPrincipal] = useState("");
  const [cycles, setCycles] = useState("3");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!rates) {
    return (
      <div style={sectionStyle}>
        <h3 style={titleStyle}>First Bank of the Frontier</h3>
        <p style={helpStyle}>
          The bank is not active in this scenario.
        </p>
      </div>
    );
  }

  async function apply() {
    setBusy(true);
    setError(null);
    try {
      const principalCents = Math.round(Number(principal));
      const numCycles = Math.round(Number(cycles));
      if (!Number.isFinite(principalCents) || principalCents <= 0) {
        setError("principal must be a positive number of cents");
        return;
      }
      if (!Number.isFinite(numCycles) || numCycles < 1 || numCycles > 12) {
        setError("cycles must be between 1 and 12");
        return;
      }
      const res = await fetch(`${apiBase}/bank/loan/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          party: "player",
          principal_cents: principalCents,
          num_cycles: numCycles,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(typeof body.detail === "string" ? body.detail : "loan application failed");
        return;
      }
      setPrincipal("");
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  async function repay(loanId: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/bank/loan/${loanId}/repay`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ party: "player" }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(typeof body.detail === "string" ? body.detail : "repayment failed");
        return;
      }
      onMutate();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={sectionStyle}>
      <h3 style={titleStyle}>First Bank of the Frontier</h3>
      <p style={helpStyle}>
        Posted rates by reputation tier. Your tier:{" "}
        <span style={pillStyle}>{rates.current_tier}</span> ({rates.honored_for_party}{" "}
        honored contracts). The bank does not message — visit when you need to.
      </p>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>Tier</th>
            <th style={thStyle}>Honored ≥</th>
            <th style={thStyle}>Rate / 30d</th>
            <th style={thStyle}>Max principal</th>
          </tr>
        </thead>
        <tbody>
          {rates.tiers.map((t) => (
            <tr
              key={t.tier}
              style={{
                background: t.current_for_party
                  ? "var(--realm-panel-1, #20242c)"
                  : "transparent",
              }}
            >
              <td style={tdStyle}>{t.tier}</td>
              <td style={tdStyle}>{t.min_honored}</td>
              <td style={tdStyle}>{t.rate_pct_per_cycle.toFixed(2)}%</td>
              <td style={tdStyle}>{formatUsdFromCents(t.max_principal_cents)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div
        style={{
          marginTop: 10,
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
          alignItems: "center",
        }}
      >
        <input
          style={{ ...inputStyle, width: 130 }}
          placeholder="principal (¢)"
          value={principal}
          onChange={(e) => setPrincipal(e.target.value)}
          inputMode="numeric"
        />
        <input
          style={{ ...inputStyle, width: 70 }}
          placeholder="cycles"
          value={cycles}
          onChange={(e) => setCycles(e.target.value)}
          inputMode="numeric"
        />
        <button
          type="button"
          style={btnStyle}
          disabled={busy || !principal}
          onClick={() => void apply()}
        >
          Apply for loan
        </button>
      </div>
      {error ? <div style={{ marginTop: 6, color: "#e07a7a", fontSize: 12 }}>{error}</div> : null}

      <h4 style={{ ...titleStyle, marginTop: 14 }}>Active loans</h4>
      {loans.length === 0 ? (
        <p style={helpStyle}>No active loans.</p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Loan</th>
              <th style={thStyle}>Status</th>
              <th style={thStyle}>Principal</th>
              <th style={thStyle}>Rate</th>
              <th style={thStyle}>Cycles paid</th>
              <th style={thStyle}>Next due</th>
              <th style={thStyle}>Action</th>
            </tr>
          </thead>
          <tbody>
            {loans.map((l) => (
              <tr key={l.id}>
                <td style={tdStyle}>{l.id}</td>
                <td style={tdStyle}>{l.status}</td>
                <td style={tdStyle}>{formatUsdFromCents(l.principal_cents)}</td>
                <td style={tdStyle}>{(l.interest_rate_bps / 100).toFixed(2)}%</td>
                <td style={tdStyle}>
                  {l.payments_made} / {l.num_cycles}
                </td>
                <td style={tdStyle}>t{l.next_due_tick}</td>
                <td style={tdStyle}>
                  {l.status === "active" ? (
                    <button
                      type="button"
                      style={btnStyle}
                      disabled={busy}
                      onClick={() => void repay(l.id)}
                    >
                      Repay cycle
                    </button>
                  ) : null}
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
// Public components
// ────────────────────────────────────────────────────────────────────────

export function Sprint5MarketSection({
  snap,
  apiBase,
  onMutate,
}: {
  snap: Sprint5Snapshot;
  apiBase: ApiBase;
  onMutate: () => void;
}) {
  return (
    <>
      <IdentitySection snap={snap} apiBase={apiBase} onMutate={onMutate} />
      <AccountsSection snap={snap} apiBase={apiBase} onMutate={onMutate} />
      <BankSection snap={snap} apiBase={apiBase} onMutate={onMutate} />
    </>
  );
}
