import type { Loan } from "../api";
import RiskBadge from "./RiskBadge";

// en-US on purpose: the browser default was producing Indian digit grouping ("$1,18,324")
const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const HEADERS: { label: string; right?: boolean }[] = [
  { label: "Loan ID" },
  { label: "State" },
  { label: "Status" },
  { label: "Balance", right: true },
  { label: "12M Default Risk" },
  { label: "Anomaly" },
  { label: "Action" },
];

const STYLES = `
.pt-th {
  box-shadow: inset 0 -1px 0 var(--border);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  white-space: nowrap;
}
.pt-row { transition: background-color .12s; }
.pt-row:hover { background: color-mix(in srgb, var(--accent) 6%, transparent); }
.pt-row:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
`;

const Warn = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 3l10 18H2z" />
    <path d="M12 10v5M12 18.5v.01" />
  </svg>
);

export default function PortfolioTable({
  loans,
  loading,
  onSelect,
}: {
  loans: Loan[];
  loading: boolean;
  onSelect: (loan: Loan) => void;
}) {
  return (
    <div className="glass overflow-hidden rounded-2xl">
      <style>{STYLES}</style>
      <div className="max-h-[560px] overflow-auto">
        <table className="w-full min-w-[760px] text-left text-sm" aria-busy={loading}>
          <caption className="sr-only">Scored loans</caption>
          <thead className="sticky top-0 z-10" style={{ background: "var(--bg-panel-2)" }}>
            <tr style={{ color: "var(--text-dim)" }}>
              {HEADERS.map((h) => (
                <th key={h.label} scope="col" className={`pt-th px-4 py-3 ${h.right ? "text-right" : ""}`}>
                  {h.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody style={{ opacity: loading ? 0.5 : 1, transition: "opacity 150ms" }}>
            {loading &&
              loans.length === 0 &&
              Array.from({ length: 6 }, (_, r) => (
                <tr key={r} className="border-t" style={{ borderColor: "var(--border)" }} aria-hidden="true">
                  {HEADERS.map((_, c) => (
                    <td key={c} className="px-4 py-3">
                      <div
                        className="animate-pulse-soft h-3 rounded"
                        style={{ width: c === 0 ? 84 : c === 6 ? 140 : 52, background: "var(--bg-panel-2)" }}
                      />
                    </td>
                  ))}
                </tr>
              ))}

            {!loading && loans.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center" style={{ color: "var(--text-dim)" }}>
                  No loans scored yet — drop a loan tape above to get started.
                </td>
              </tr>
            )}

            {loans.map((loan) => {
              const flagged = loan.exception_required === 1;
              const action = loan.recommended_action || "";
              const routine = /^standard/i.test(action);
              const delinquent = !!loan.current_status && loan.current_status !== "Current";

              return (
                <tr
                  key={loan.loan_id}
                  onClick={() => onSelect(loan)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(loan);
                    }
                  }}
                  tabIndex={0}
                  className="pt-row cursor-pointer border-t"
                  style={{ borderColor: "var(--border)" }}
                >
                  {/* Loan ID (accent bar on the left edge for flagged loans) */}
                  <td
                    className="px-4 py-2.5 font-mono text-xs whitespace-nowrap"
                    style={{ color: "var(--text)", boxShadow: flagged ? "inset 3px 0 0 var(--crimson)" : undefined }}
                  >
                    {loan.loan_id}
                  </td>

                  <td className="px-4 py-2.5" style={{ color: "var(--text-dim)" }}>
                    {loan.state}
                  </td>

                  {/* Status: quiet when Current, emphasized when not */}
                  <td
                    className="px-4 py-2.5 whitespace-nowrap"
                    style={{ color: delinquent ? "var(--text)" : "var(--text-dim)" }}
                  >
                    {delinquent && (
                      <span
                        className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle"
                        style={{ background: "var(--amber)" }}
                      />
                    )}
                    {loan.current_status}
                  </td>

                  <td className="px-4 py-2.5 text-right tabular-nums" style={{ color: "var(--text)" }}>
                    {loan.current_balance != null ? usd.format(loan.current_balance) : "—"}
                  </td>

                  <td className="px-4 py-2.5">
                    <RiskBadge prob={loan.prob_next_12m_default} quiet />
                  </td>

                  {/* Anomaly: nothing at all when there isn't one */}
                  <td className="px-4 py-2.5">
                    {flagged && (
                      <span
                        className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium"
                        style={{
                          color: "var(--crimson)",
                          background: "color-mix(in srgb, var(--crimson) 12%, transparent)",
                        }}
                      >
                        <Warn />
                        {loan.exception_type}
                      </span>
                    )}
                  </td>

                  {/* Action: routine text collapses to a small tag, full text on hover */}
                  <td className="max-w-[260px] px-4 py-2.5 text-xs" title={action || undefined}>
                    {!action ? (
                      <span style={{ color: "var(--text-dim)" }}>—</span>
                    ) : routine ? (
                      <span
                        className="rounded-md px-1.5 py-0.5"
                        style={{ background: "var(--bg-panel-2)", color: "var(--text-dim)" }}
                      >
                        Standard
                      </span>
                    ) : (
                      <span
                        style={{
                          color: "var(--text)",
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {action}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}