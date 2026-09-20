export function riskTier(prob: number): { label: string; color: string; bg: string } {
  if (prob >= 0.2) return { label: "High Risk", color: "var(--crimson)", bg: "color-mix(in srgb, var(--crimson) 12%, transparent)" };
  if (prob >= 0.08) return { label: "Watch-list", color: "var(--amber)", bg: "color-mix(in srgb, var(--amber) 12%, transparent)" };
  return { label: "Healthy", color: "var(--emerald)", bg: "color-mix(in srgb, var(--emerald) 12%, transparent)" };
}

/**
 * `quiet` renders Healthy loans as plain muted text instead of a green pill,
 * so color in a long list is reserved for loans that need attention.
 * It defaults to false, so every existing use of <RiskBadge prob={...} /> looks the same as before.
 */
export default function RiskBadge({ prob, quiet = false }: { prob: number; quiet?: boolean }) {
  const t = riskTier(prob);
  const pct = (prob * 100).toFixed(1);

  if (quiet && t.label === "Healthy") {
    return (
      <span
        className="inline-flex items-center whitespace-nowrap px-2.5 py-1 text-xs tabular-nums"
        style={{ color: "var(--text-dim)" }}
      >
        Healthy · {pct}%
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs tabular-nums"
      style={{ color: t.color, background: t.bg, fontWeight: t.label === "High Risk" ? 600 : 500 }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: t.color }} />
      {t.label} · {pct}%
    </span>
  );
}