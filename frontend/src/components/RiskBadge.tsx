export function riskTier(prob: number): { label: string; color: string; bg: string } {
  if (prob >= 0.2) return { label: "High Risk", color: "var(--crimson)", bg: "color-mix(in srgb, var(--crimson) 12%, transparent)" };
  if (prob >= 0.08) return { label: "Watch-list", color: "var(--amber)", bg: "color-mix(in srgb, var(--amber) 12%, transparent)" };
  return { label: "Healthy", color: "var(--emerald)", bg: "color-mix(in srgb, var(--emerald) 12%, transparent)" };
}

export default function RiskBadge({ prob }: { prob: number }) {
  const t = riskTier(prob);
  return (
    <span
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium"
      style={{ color: t.color, background: t.bg }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: t.color }} />
      {t.label} · {(prob * 100).toFixed(1)}%
    </span>
  );
}
