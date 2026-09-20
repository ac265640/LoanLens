import { useEffect, useState, useCallback } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { copilotExplainStress, queryStress, type StressResult } from "../api";
import RichText from "./RichText";

function useDebouncedEffect(fn: () => void, deps: unknown[], delay: number) {
  useEffect(() => {
    const t = setTimeout(fn, delay);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export default function ShockwavePanel() {
  const [rate, setRate] = useState(0);
  const [unemp, setUnemp] = useState(0);
  const [result, setResult] = useState<StressResult | null>(null);
  const [history, setHistory] = useState<{ label: string; el: number }[]>([]);
  const [loading, setLoading] = useState(false);
  const [explanation, setExplanation] = useState<{ text: string; note: string; fallback: boolean } | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [stressError, setStressError] = useState(false);

  const fetchStress = useCallback(async (r: number, u: number) => {
    setLoading(true);
    setExplanation(null); // an explanation of the previous scenario is stale once the sliders move
    try {
      const res = await queryStress(r, u);
      setResult(res);
      setStressError(false);
      setHistory((h) => [...h.slice(-19), { label: `${r >= 0 ? "+" : ""}${r}bps / ${u >= 0 ? "+" : ""}${u}%`, el: res.expected_loss_usd }]);
    } catch {
      setStressError(true); // keep the last result on screen, but say it is stale
    } finally {
      setLoading(false);
    }
  }, []);

  async function explainScenario() {
    if (!result) return;
    setExplaining(true);
    try {
      const r = await copilotExplainStress(result);
      setExplanation({
        text: r.output,
        fallback: !!r.fallback,
        note: r.fallback ? "Template answer — no language model could be reached" : `Answered by ${r.model_name}`,
      });
    } catch (e) {
      setExplanation({ text: e instanceof Error ? e.message : "Could not explain this scenario.", note: "Error", fallback: true });
    } finally {
      setExplaining(false);
    }
  }

  useDebouncedEffect(() => {
    fetchStress(rate, unemp);
  }, [rate, unemp], 180);

  return (
    <div className="glass rounded-2xl p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          Shockwave — Live Macro Stress Simulator
        </h3>
        {loading && <span className="text-xs animate-pulse-soft" style={{ color: "var(--accent)" }}>recomputing…</span>}
        {!loading && stressError && (
          <span className="text-xs" role="alert" style={{ color: "var(--amber)" }}>
            Stress service unreachable. Move a slider to retry.
          </span>
        )}
      </div>

      <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SliderField
          label="Interest Rate Shock"
          value={rate}
          min={-300}
          max={300}
          step={10}
          unit="bps"
          onChange={setRate}
        />
        <SliderField
          label="Unemployment Shock"
          value={unemp}
          min={0}
          max={8}
          step={0.25}
          unit="pp"
          onChange={setUnemp}
        />
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="12M Default Rate" value={result ? `${result.mean_default_prob_pct.toFixed(2)}%` : "—"} />
        <StatTile label="Expected Loss" value={result ? `$${(result.expected_loss_usd / 1e6).toFixed(2)}M` : "—"} accent="var(--amber)" />
        <StatTile label="Capital (CAR) Impact" value={result ? `${result.car_impact_pct.toFixed(1)}%` : "—"} />
        <StatTile label="VaR 99%" value={result ? `$${(result.var99_usd / 1e6).toFixed(2)}M` : "—"} accent="var(--crimson)" />
      </div>

      <div className="mb-3">
        <button
          onClick={explainScenario}
          disabled={!result || explaining}
          className="rounded-lg px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          style={{ background: "var(--accent)", color: "#0a0d14" }}
        >
          {explaining ? "Explaining…" : "Explain this scenario"}
        </button>
        {explanation && (
          <div className="mt-2 rounded-lg p-3 text-xs leading-relaxed" style={{ background: "var(--bg-panel-2)", color: "var(--text)" }}>
            <p className="mb-1 text-[10px] uppercase tracking-wide" style={{ color: explanation.fallback ? "var(--amber)" : "var(--text-dim)" }}>
              {explanation.note}
            </p>
            <RichText text={explanation.text} />
          </div>
        )}
      </div>

      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={history}>
            <defs>
              <linearGradient id="elGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.4} />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="label" hide />
            <YAxis hide domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{ background: "var(--bg-panel-2)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
              formatter={(v) => [`$${(Number(v) / 1e6).toFixed(2)}M`, "Expected Loss"]}
            />
            <Area type="monotone" dataKey="el" stroke="var(--accent)" fill="url(#elGradient)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-[10px]" style={{ color: "var(--text-dim)" }}>
        LGD, capital base, and VaR are illustrative constants layered on real model output — see README for the exact assumptions.
      </p>
    </div>
  );
}

function SliderField({
  label, value, min, max, step, unit, onChange,
}: { label: string; value: number; min: number; max: number; step: number; unit: string; onChange: (v: number) => void }) {
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-xs">
        <span style={{ color: "var(--text-dim)" }}>{label}</span>
        <span style={{ color: "var(--accent)" }}>
          {value >= 0 ? "+" : ""}
          {value} {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[var(--accent)]"
      />
    </div>
  );
}

function StatTile({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl p-3" style={{ background: "var(--bg-panel-2)" }}>
      <p className="text-[10px] uppercase tracking-wide" style={{ color: "var(--text-dim)" }}>
        {label}
      </p>
      <p className="mt-0.5 text-base font-semibold" style={{ color: accent || "var(--text)" }}>
        {value}
      </p>
    </div>
  );
}
