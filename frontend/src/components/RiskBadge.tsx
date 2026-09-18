export function riskTier(prob: number): { label: string; color: string; bg: string } {
  if (prob >= 0.2) return { label: "High Risk", color: "#f87171", bg: "rgba(248,113,113,0.12)" };
  if (prob >= 0.08) return { label: "Watch-list", color: "#fbbf24", bg: "rgba(251,191,36,0.12)" };
  return { label: "Healthy", color: "#34d399", bg: "rgba(52,211,153,0.12)" };
}

export default function RiskBadge({ prob }: { prob: number }) {
  const t = riskTier(prob);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
      style={{ color: t.color, background: t.bg }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: t.color }} />
      {t.label} · {(prob * 100).toFixed(1)}%
    </span>
  );
}
