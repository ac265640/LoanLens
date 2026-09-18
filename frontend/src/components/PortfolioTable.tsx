import type { Loan } from "../api";
import RiskBadge from "./RiskBadge";

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
      <div className="max-h-[560px] overflow-y-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 z-10" style={{ background: "var(--bg-panel-2)" }}>
            <tr style={{ color: "var(--text-dim)" }}>
              <th className="px-4 py-3 font-medium">Loan ID</th>
              <th className="px-4 py-3 font-medium">State</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Balance</th>
              <th className="px-4 py-3 font-medium">12M Default Risk</th>
              <th className="px-4 py-3 font-medium">Anomaly</th>
              <th className="px-4 py-3 font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center animate-pulse-soft" style={{ color: "var(--text-dim)" }}>
                  Loading portfolio…
                </td>
              </tr>
            )}
            {!loading && loans.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center" style={{ color: "var(--text-dim)" }}>
                  No loans scored yet — drop a loan tape above to get started.
                </td>
              </tr>
            )}
            {loans.map((loan) => (
              <tr
                key={loan.loan_id}
                onClick={() => onSelect(loan)}
                className="cursor-pointer border-t transition-colors hover:bg-white/[0.03]"
                style={{ borderColor: "var(--border)" }}
              >
                <td className="px-4 py-3 font-mono text-xs" style={{ color: "var(--text)" }}>
                  {loan.loan_id}
                </td>
                <td className="px-4 py-3" style={{ color: "var(--text-dim)" }}>
                  {loan.state}
                </td>
                <td className="px-4 py-3" style={{ color: "var(--text-dim)" }}>
                  {loan.current_status}
                </td>
                <td className="px-4 py-3" style={{ color: "var(--text)" }}>
                  ${loan.current_balance?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </td>
                <td className="px-4 py-3">
                  <RiskBadge prob={loan.prob_next_12m_default} />
                </td>
                <td className="px-4 py-3">
                  {loan.exception_required === 1 ? (
                    <span className="text-xs font-medium" style={{ color: "var(--crimson)" }}>
                      ⚠ {loan.exception_type}
                    </span>
                  ) : (
                    <span className="text-xs" style={{ color: "var(--text-dim)" }}>
                      —
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs" style={{ color: "var(--text-dim)" }}>
                  {loan.recommended_action}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
