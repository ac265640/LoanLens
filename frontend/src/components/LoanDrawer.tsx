import { useState } from "react";
import type { Loan, CedarResult } from "../api";
import { cedarAuthorize, copilotMemo, ltvPct } from "../api";
import RiskBadge from "./RiskBadge";
import RichText from "./RichText";

const ROLES = ["JuniorUnderwriter", "SeniorUnderwriter", "RiskCommittee"];
const ACTIONS = ["ApproveLoan", "OverrideAnomaly"];

const DRIVER_LABELS: Record<string, string> = {
  days_past_due: "Days Past Due",
  credit_score_ordinal: "Credit Score Tier",
  balance_to_orig_ratio: "Balance vs. Original",
  interest_rate_imputed: "Interest Rate",
  dpd_roll_max_6m: "6M Max DPD",
  balance_change_1m_pct: "1M Balance Change",
};

export default function LoanDrawer({ loan, onClose }: { loan: Loan; onClose: () => void }) {
  const [role, setRole] = useState("JuniorUnderwriter");
  const [action, setAction] = useState("ApproveLoan");
  const [cedarResult, setCedarResult] = useState<CedarResult | null>(null);
  const [cedarLoading, setCedarLoading] = useState(false);
  const [memo, setMemo] = useState<string | null>(null);
  const [memoLoading, setMemoLoading] = useState(false);
  const [memoModel, setMemoModel] = useState("");

  async function checkCedar() {
    setCedarLoading(true);
    setCedarResult(null);
    try {
      const r = await cedarAuthorize("demo-user", role, action, loan);
      setCedarResult(r);
    } catch (e) {
      setCedarResult({ decision: "deny", determining_policies: [e instanceof Error ? e.message : "error"] });
    } finally {
      setCedarLoading(false);
    }
  }

  async function generateMemo() {
    setMemoLoading(true);
    setMemo(null);
    try {
      const r = await copilotMemo(loan.loan_id);
      setMemo(r.output);
      setMemoModel(r.fallback ? "Template answer — no language model could be reached" : `Answered by ${r.model_name}`);
    } catch (e) {
      setMemo(e instanceof Error ? e.message : "Memo generation failed.");
    } finally {
      setMemoLoading(false);
    }
  }

  const drivers = [loan.top_driver_1, loan.top_driver_2, loan.top_driver_3].filter(Boolean);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="glass relative flex h-full w-full max-w-lg flex-col overflow-y-auto p-6" style={{ borderLeft: "1px solid var(--border)" }}>
        <div className="mb-4 flex items-start justify-between">
          <div>
            <p className="font-mono text-xs" style={{ color: "var(--text-dim)" }}>
              {loan.loan_id}
            </p>
            <h2 className="text-lg font-semibold" style={{ color: "var(--text)" }}>
              {loan.state} · {loan.credit_score_band} credit
            </h2>
          </div>
          <button onClick={onClose} className="rounded-lg px-2 py-1 text-sm" style={{ color: "var(--text-dim)" }}>
            ✕
          </button>
        </div>

        <div className="mb-5 flex flex-wrap gap-2">
          <RiskBadge prob={loan.prob_next_12m_default} />
          {loan.exception_required === 1 && (
            <span className="rounded-full px-2.5 py-1 text-xs font-medium" style={{ color: "var(--crimson)", background: "rgba(248,113,113,0.12)" }}>
              ⚠ {loan.exception_type}
            </span>
          )}
        </div>

        <Section title="Risk Probabilities">
          <Metric label="3M Delinquency" value={`${(loan.prob_next_3m_delinquency * 100).toFixed(1)}%`} />
          <Metric label="6M Delinquency" value={`${(loan.prob_next_6m_delinquency * 100).toFixed(1)}%`} />
          <Metric label="12M Default" value={`${(loan.prob_next_12m_default * 100).toFixed(1)}%`} />
          <Metric label="12M Prepayment" value={`${(loan.prob_next_12m_prepayment * 100).toFixed(1)}%`} />
        </Section>

        <Section title="Top Risk Drivers (deviation from portfolio median)">
          {drivers.map((d, i) => (
            <div key={d} className="mb-1.5 flex items-center gap-2">
              <span className="w-4 text-xs" style={{ color: "var(--text-dim)" }}>
                {i + 1}
              </span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
                <div className="h-full rounded-full" style={{ width: `${100 - i * 28}%`, background: "var(--accent)" }} />
              </div>
              <span className="text-xs" style={{ color: "var(--text)" }}>
                {DRIVER_LABELS[d] || d}
              </span>
            </div>
          ))}
        </Section>

        <Section title="Cedar Policy Compliance Gate">
          <div className="flex items-center gap-2">
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="rounded-lg border px-2 py-1.5 text-xs"
              style={{ background: "var(--bg-panel-2)", borderColor: "var(--border)", color: "var(--text)" }}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <button
              onClick={checkCedar}
              disabled={cedarLoading}
              className="rounded-lg px-3 py-1.5 text-xs font-medium"
              style={{ background: "var(--accent)", color: "#0a0d14" }}
            >
              {cedarLoading ? "Evaluating…" : `Check ${action}`}
            </button>
          </div>
          <div className="mt-2">
            <select
              value={action}
              onChange={(e) => {
                setAction(e.target.value);
                setCedarResult(null);
              }}
              className="rounded-lg border px-2 py-1.5 text-xs"
              style={{ background: "var(--bg-panel-2)", borderColor: "var(--border)", color: "var(--text)" }}
            >
              {ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
          <p className="mt-2 text-[11px]" style={{ color: "var(--text-dim)" }}>
            Policy inputs: risk {(loan.prob_next_12m_default * 100).toFixed(0)}% · LTV ≤ {ltvPct(loan.ltv_band)}% · exception flag{" "}
            {loan.exception_required === 1 ? "yes" : "no"}
          </p>
          {cedarResult && (
            <div
              className="mt-2 rounded-lg px-3 py-2 text-xs"
              style={{
                background: cedarResult.decision === "allow" ? "rgba(52,211,153,0.1)" : "rgba(248,113,113,0.1)",
                color: cedarResult.decision === "allow" ? "var(--emerald)" : "var(--crimson)",
              }}
            >
              <strong>{cedarResult.decision === "allow" ? "✓ ALLOW" : "✕ DENY"}</strong> — policy:{" "}
              {cedarResult.determining_policies.join(", ") || "no matching policy"}
            </div>
          )}
        </Section>

        <Section title="Reviewer Memo">
          <button
            onClick={generateMemo}
            disabled={memoLoading}
            className="rounded-lg px-3 py-1.5 text-xs font-medium"
            style={{ background: "var(--accent)", color: "#0a0d14" }}
          >
            {memoLoading ? "Generating…" : "Generate Credit Committee Memo"}
          </button>
          {memo && (
            <div className="mt-2 rounded-lg p-3 text-xs leading-relaxed" style={{ background: "var(--bg-panel-2)", color: "var(--text)" }}>
              <p className="mb-1 text-[10px] uppercase tracking-wide" style={{ color: "var(--text-dim)" }}>
                {memoModel}
              </p>
              <RichText text={memo} />
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5 border-t pt-4" style={{ borderColor: "var(--border)" }}>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-dim)" }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="mb-1 flex justify-between text-sm">
      <span style={{ color: "var(--text-dim)" }}>{label}</span>
      <span style={{ color: "var(--text)" }}>{value}</span>
    </div>
  );
}
