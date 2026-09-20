import { useCallback, useEffect, useMemo, useState } from "react";
import { listLoans, type Loan, type PortfolioSummary } from "./api";
import UploadDropzone from "./components/UploadDropzone";
import PortfolioTable from "./components/PortfolioTable";
import LoanDrawer from "./components/LoanDrawer";
import ShockwavePanel from "./components/ShockwavePanel";
import CopilotChat from "./components/CopilotChat";
import CoverageCard from "./components/CoverageCard";
import { riskTier } from "./components/RiskBadge";

type Filter = "all" | "high_risk" | "exceptions";

const nf = new Intl.NumberFormat("en-US");

export default function App() {
  const [loans, setLoans] = useState<Loan[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [allSummary, setAllSummary] = useState<PortfolioSummary | null>(null); // last summary seen on the "all" tab, for stable tab counts
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [selected, setSelected] = useState<Loan | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filter === "high_risk") params.min_default_prob = "0.20";
      if (filter === "exceptions") params.exceptions_only = "true";
      const r = await listLoans(params);
      setLoans(r.loans);
      setSummary(r.summary);
      if (filter === "all") setAllSummary(r.summary);
      setLoadFailed(false);
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Display order only: loans that need attention first, then by default risk, highest first.
  const ordered = useMemo(() => {
    const needsAttention = (l: Loan) =>
      l.exception_required === 1 || riskTier(l.prob_next_12m_default).label === "High Risk";
    return [...loans].sort((a, b) => {
      const d = Number(needsAttention(b)) - Number(needsAttention(a));
      return d !== 0 ? d : b.prob_next_12m_default - a.prob_next_12m_default;
    });
  }, [loans]);

  const counts = allSummary ?? summary;
  const tabs: { key: Filter; label: string; count?: number }[] = [
    { key: "all", label: "All loans", count: counts?.total_loans },
    { key: "high_risk", label: "High risk", count: counts?.high_risk_count },
    { key: "exceptions", label: "Exceptions", count: counts?.exception_count },
  ];

  return (
    <div className="min-h-screen px-4 pt-24 pb-10 sm:px-8 sm:pt-28">
      <main className="mx-auto max-w-7xl space-y-6">

        {/* ── 1. Page header ── */}
        <header className="glass rounded-2xl px-5 py-4 sm:px-7 sm:py-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2.5 mb-2">
                {/* live pulse dot */}
                <span className="relative flex h-2.5 w-2.5">
                  <span
                    className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
                    style={{ background: "var(--emerald)" }}
                  />
                  <span
                    className="relative inline-flex rounded-full h-2.5 w-2.5"
                    style={{ background: "var(--emerald)" }}
                  />
                </span>
                <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--emerald)" }}>
                  Live
                </span>
              </div>
              <h1 className="text-2xl font-bold sm:text-3xl" style={{ color: "var(--text)" }}>
                Live Platform
              </h1>
              <p className="mt-1.5 text-sm" style={{ color: "var(--text-dim)" }}>
                {loading
                  ? "Loading portfolio…"
                  : !summary
                  ? "No portfolio loaded yet — upload a loan tape to get started."
                  : `${nf.format(summary.total_loans)} loans scored across your tape.`}
              </p>
            </div>

            {/* attention badge */}
            {summary && (
              <div
                className="flex flex-col items-center justify-center rounded-xl px-5 py-3 text-center min-w-[110px]"
                style={{
                  background: summary.attention_count > 0 ? "color-mix(in srgb, var(--crimson) 12%, transparent)" : "color-mix(in srgb, var(--emerald) 12%, transparent)",
                  border: `1px solid ${summary.attention_count > 0 ? "color-mix(in srgb, var(--crimson) 30%, transparent)" : "color-mix(in srgb, var(--emerald) 30%, transparent)"}`,
                }}
              >
                <span
                  className="text-3xl font-bold tabular-nums"
                  style={{ color: summary.attention_count > 0 ? "var(--crimson)" : "var(--emerald)" }}
                >
                  {nf.format(summary.attention_count)}
                </span>
                <span className="mt-1 text-xs font-medium" style={{ color: "var(--text-dim)" }}>
                  {summary.attention_count === 0 ? "all clear" : "need attention"}
                </span>
              </div>
            )}
          </div>
        </header>

        {/* ── 2. Upload — entry point, first action ── */}
        <UploadDropzone onComplete={refresh} />

        {/* ── 3. Stats — what was scored ── */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat
            label="Loans scored"
            value={summary ? nf.format(summary.total_loans) : "—"}
            sub="100% of the tape"
          />
          <Stat
            label="High risk"
            value={summary ? nf.format(summary.high_risk_count) : "—"}
            sub="20%+ default probability"
            accent={summary && summary.high_risk_count > 0 ? "var(--crimson)" : undefined}
          />
          <Stat
            label="Exceptions"
            value={summary ? nf.format(summary.exception_count) : "—"}
            sub="flagged by the rule engine"
            accent={summary && summary.exception_count > 0 ? "var(--amber)" : undefined}
          />
          <Stat
            label="Total exposure"
            value={summary ? `$${(summary.total_exposure_usd / 1e6).toFixed(1)}M` : "—"}
            sub="outstanding balance"
          />
        </div>

        {/* ── 4. Filter tabs + Portfolio table — browse & investigate ── */}
        <div className="space-y-3">
          <div className="glass flex flex-wrap gap-1 rounded-2xl p-2">
            {tabs.map((t) => {
              const active = filter === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => setFilter(t.key)}
                  aria-pressed={active}
                  className="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
                  style={{
                    background: active ? "var(--accent)" : "transparent",
                    color: active ? "#0a0d14" : "var(--text-dim)",
                  }}
                >
                  {t.label}
                  {t.count != null && <span className="ml-1.5 tabular-nums opacity-70">{nf.format(t.count)}</span>}
                </button>
              );
            })}
          </div>

          {loadFailed && (
            <div
              className="glass flex items-center justify-between gap-3 rounded-2xl px-4 py-3 text-sm"
              role="alert"
              style={{ color: "var(--amber)" }}
            >
              <span>Could not reach the LoanLens API. Your connection may be unstable.</span>
              <button
                onClick={refresh}
                className="rounded-lg px-3 py-1.5 text-xs font-medium"
                style={{ background: "var(--accent)", color: "#0a0d14" }}
              >
                Retry
              </button>
            </div>
          )}

          <PortfolioTable loans={ordered} loading={loading} onSelect={setSelected} />
        </div>

        {/* ── 5. Coverage check — insight on the data above ── */}
        <CoverageCard summary={summary} />

        {/* ── 6. Shockwave stress test — macro scenario modelling ── */}
        <ShockwavePanel />

        {/* ── 7. Portfolio Copilot — ask questions about everything above ── */}
        <CopilotChat />

      </main>

      {selected && <LoanDrawer loan={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub: string;
  accent?: string;
}) {
  return (
    <div className="glass rounded-2xl px-4 py-3.5">
      <p className="text-[10.5px] font-semibold uppercase tracking-wide" style={{ color: "var(--text-dim)" }}>
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums" style={{ color: accent || "var(--text)" }}>
        {value}
      </p>
      <p className="mt-0.5 text-[11px]" style={{ color: "var(--text-dim)" }}>
        {sub}
      </p>
    </div>
  );
}