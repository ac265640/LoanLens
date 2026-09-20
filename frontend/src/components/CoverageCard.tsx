import type { PortfolioSummary } from "../api";

const SAMPLE_RATE = 0.05;

/**
 * What full coverage buys, computed from the live portfolio: a manual review
 * that samples 5% of the tape at random is expected to see 5% of the loans that
 * need attention. The sample rate is an assumption, and the card says so.
 */
export default function CoverageCard({ summary }: { summary: PortfolioSummary | null }) {
  if (!summary || summary.total_loans === 0) return null;

  const { total_loans: total, attention_count: attention } = summary;
  const reviewed = Math.round(total * SAMPLE_RATE);
  const expectedCaught = attention * SAMPLE_RATE;

  return (
    <div className="glass rounded-2xl p-4" aria-label="Coverage compared with a manual sample">
      <p className="text-[10px] uppercase tracking-wide" style={{ color: "var(--text-dim)" }}>
        Coverage check
      </p>
      <div className="mt-2 grid grid-cols-2 gap-3">
        <div className="rounded-xl p-3" style={{ background: "var(--bg-panel-2)" }}>
          <p className="text-[11px]" style={{ color: "var(--text-dim)" }}>
            Manual {SAMPLE_RATE * 100}% sample
          </p>
          <p className="mt-1 text-lg font-semibold" style={{ color: "var(--amber)" }}>
            ~{expectedCaught.toFixed(1)} of {attention}
          </p>
          <p className="text-[11px] leading-snug" style={{ color: "var(--text-dim)" }}>
            problem loans expected to be seen, from ~{reviewed} of {total} reviewed
          </p>
        </div>
        <div className="rounded-xl p-3" style={{ background: "var(--bg-panel-2)" }}>
          <p className="text-[11px]" style={{ color: "var(--text-dim)" }}>
            LoanLens
          </p>
          <p className="mt-1 text-lg font-semibold" style={{ color: "var(--emerald)" }}>
            {attention} of {attention}
          </p>
          <p className="text-[11px] leading-snug" style={{ color: "var(--text-dim)" }}>
            problem loans flagged, from {total} of {total} scored
          </p>
        </div>
      </div>
      <p className="mt-2 text-[10.5px]" style={{ color: "var(--text-dim)" }}>
        Problem loans are High Risk (20%+ default probability) or rule-engine exceptions. Assumes the manual sample is drawn at random.
      </p>
    </div>
  );
}
