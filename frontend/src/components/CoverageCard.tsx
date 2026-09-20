import type { PortfolioSummary } from "../api";

const SAMPLE_RATE = 0.05;

const STYLES = `
.cc-fill { transform-origin: left center; animation: cc-grow .7s cubic-bezier(.16,1,.3,1) both; }
@keyframes cc-grow { from { transform: scaleX(0); } }
@media (prefers-reduced-motion: reduce) { .cc-fill { animation: none; } }
`;

/**
 * Probability that a random sample of `reviewed` loans (drawn without replacement)
 * contains none of the `attention` problem loans in a tape of `total`.
 */
function chanceSampleMissesAll(total: number, attention: number, reviewed: number): number {
  let p = 1;
  for (let j = 0; j < attention; j++) {
    const num = total - reviewed - j;
    if (num <= 0) return 0;
    p *= num / (total - j);
  }
  return p;
}

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
  const pct = SAMPLE_RATE * 100;

  const missChance = chanceSampleMissesAll(total, attention, reviewed) * 100;
  const missText = missChance < 1 ? "<1%" : `${Math.round(missChance)}%`;

  return (
    <section className="glass rounded-2xl p-4" aria-label="Coverage compared with a manual sample">
      <style>{STYLES}</style>

      <p className="text-[10.5px] font-semibold uppercase tracking-wide" style={{ color: "var(--text-dim)" }}>
        Coverage check
      </p>

      {attention === 0 ? (
        <p className="mt-2 text-sm leading-snug" style={{ color: "var(--text)" }}>
          No problem loans flagged in this tape. All {total} loans were scored.
        </p>
      ) : (
        <>
          <p className="mt-2 text-sm leading-snug" style={{ color: "var(--text)" }}>
            A manual {pct}% sample would expect to see{" "}
            <strong className="tabular-nums" style={{ color: "var(--amber)" }}>
              {expectedCaught.toFixed(1)}
            </strong>{" "}
            of your {attention} problem loans. LoanLens flagged{" "}
            <strong style={{ color: "var(--emerald)" }}>all {attention}</strong>.
          </p>

          <div className="mt-4 space-y-3.5">
            <Row
              label={`Manual ${pct}% sample`}
              value={`~${expectedCaught.toFixed(1)} of ${attention}`}
              sub={`problem loans expected to be seen, from ~${reviewed} of ${total} reviewed`}
              frac={expectedCaught / attention}
              color="var(--amber)"
            />
            <Row
              label="LoanLens"
              value={`${attention} of ${attention}`}
              sub={`problem loans flagged, from ${total} of ${total} scored`}
              frac={1}
              color="var(--emerald)"
            />
          </div>

          <div className="mt-4 flex items-center gap-3 border-t pt-3" style={{ borderColor: "var(--border)" }}>
            <span className="text-xl font-semibold tabular-nums" style={{ color: "var(--amber)" }}>
              {missText}
            </span>
            <span className="text-xs leading-snug" style={{ color: "var(--text-dim)" }}>
              chance a random {pct}% sample misses every one of them
            </span>
          </div>
        </>
      )}

      <p className="mt-3 text-[10.5px] leading-relaxed" style={{ color: "var(--text-dim)" }}>
        Problem loans are High Risk (20%+ default probability) or rule-engine exceptions. Assumes the manual sample is drawn at random.
      </p>
    </section>
  );
}

function Row({
  label, value, sub, frac, color,
}: { label: string; value: string; sub: string; frac: number; color: string }) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium" style={{ color: "var(--text)" }}>
          {label}
        </span>
        <span className="text-sm font-semibold tabular-nums" style={{ color }}>
          {value}
        </span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full"
        style={{ background: "color-mix(in srgb, var(--text-dim) 18%, transparent)" }}
        aria-hidden="true"
      >
        <div className="cc-fill h-full rounded-full" style={{ width: `${Math.max(2, frac * 100)}%`, background: color }} />
      </div>
      <p className="mt-1 text-[11px] leading-snug" style={{ color: "var(--text-dim)" }}>
        {sub}
      </p>
    </div>
  );
}