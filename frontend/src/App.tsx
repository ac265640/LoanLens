import { useCallback, useEffect, useState } from "react";
import { listLoans, type Loan, type PortfolioSummary } from "./api";
import UploadDropzone from "./components/UploadDropzone";
import PortfolioTable from "./components/PortfolioTable";
import LoanDrawer from "./components/LoanDrawer";
import ShockwavePanel from "./components/ShockwavePanel";
import CopilotChat from "./components/CopilotChat";
import CoverageCard from "./components/CoverageCard";

export default function App() {
  const [loans, setLoans] = useState<Loan[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [selected, setSelected] = useState<Loan | null>(null);
  const [filter, setFilter] = useState<"all" | "high_risk" | "exceptions">("all");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filter === "high_risk") params.min_default_prob = "0.20";
      if (filter === "exceptions") params.exceptions_only = "true";
      const r = await listLoans(params);
      setLoans(r.loans);
      setSummary(r.summary);
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

  return (
    <div className="min-h-screen px-4 pt-24 pb-6 sm:px-8 sm:pt-28">
      <main className="mx-auto grid max-w-7xl grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          {/* On mobile screens, show summary chips at the top */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:hidden">
            <SummaryChip label="Loans Scored" value={summary?.total_loans ?? "—"} />
            <SummaryChip label="High Risk" value={summary?.high_risk_count ?? "—"} accent="var(--crimson)" />
            <SummaryChip label="Exceptions" value={summary?.exception_count ?? "—"} accent="var(--amber)" />
            <SummaryChip
              label="Total Exposure"
              value={summary ? `$${(summary.total_exposure_usd / 1e6).toFixed(1)}M` : "—"}
              accent="var(--emerald)"
            />
          </div>

          <UploadDropzone onComplete={refresh} />

          <div className="glass rounded-2xl p-1">
            <div className="flex gap-1 p-2">
              {(["all", "high_risk", "exceptions"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
                  style={{
                    background: filter === f ? "var(--accent)" : "transparent",
                    color: filter === f ? "#0a0d14" : "var(--text-dim)",
                  }}
                >
                  {f === "all" ? "All Loans" : f === "high_risk" ? "High Risk" : "Exceptions"}
                </button>
              ))}
            </div>
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

          <PortfolioTable loans={loans} loading={loading} onSelect={setSelected} />
          <ShockwavePanel />
        </div>

        <div className="space-y-5">
          {/* On desktop, summary chips sit at the top of this column, aligned with UploadDropzone */}
          <div className="hidden grid-cols-2 gap-3 lg:grid">
            <SummaryChip label="Loans Scored" value={summary?.total_loans ?? "—"} />
            <SummaryChip label="High Risk" value={summary?.high_risk_count ?? "—"} accent="var(--crimson)" />
            <SummaryChip label="Exceptions" value={summary?.exception_count ?? "—"} accent="var(--amber)" />
            <SummaryChip
              label="Total Exposure"
              value={summary ? `$${(summary.total_exposure_usd / 1e6).toFixed(1)}M` : "—"}
              accent="var(--emerald)"
            />
          </div>

          <CoverageCard summary={summary} />

          <CopilotChat />
        </div>
      </main>

      {selected && <LoanDrawer loan={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function SummaryChip({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="glass rounded-xl px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide" style={{ color: "var(--text-dim)" }}>
        {label}
      </p>
      <p className="text-sm font-semibold" style={{ color: accent || "var(--text)" }}>
        {value}
      </p>
    </div>
  );
}
