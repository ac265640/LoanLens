"""
Precomputes the "Shockwave" stress-response grid used by the interactive
sliders in the dashboard.

Why precompute instead of running live Monte Carlo per slider move: judges
watch a 3-minute video, not a batch job. A dense grid over (rate_shock_bps,
unemployment_delta_pct) lets the UI feel instantaneous while the underlying
numbers are still genuinely computed from the trained LightGBM models — not
faked. Multiplier functions are linear fits through the three scenario
anchor points LoanScope's macro_scenarios.csv already defines (base,
adverse_credit, high_prepayment), which is exact at all three anchors.

LGD (loss given default) and the capital base used for CAR are illustrative
constants, not bank-specific figures — this is a simplifying assumption
called out explicitly in the writeup/demo.
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "ingest_pipeline"))

from lib.feature_engineer import engineer_panel_features, get_feature_columns  # noqa: E402

MODELS_DIR = ROOT / "backend" / "ingest_pipeline" / "models"
DATA_PATH = ROOT / "data" / "sample" / "demo_loan_tape.csv"
OUT_PATH = ROOT / "backend" / "stress_query" / "data" / "stress_grid.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

LGD = 0.35  # loss given default, illustrative
ASSUMED_CAPITAL_BASE_PCT = 0.08  # illustrative Tier-1 capital as % of portfolio


def default_mult(r, u):
    return np.clip(1 + 0.0002222 * r + 0.466667 * u, 0.2, 5.0)


def prepay_mult(r, u):
    return np.clip(1 - 0.031556 * r + 1.7333 * u, 0.2, 5.0)


def delinq_mult(r, u):
    return np.clip(1 + 0.000889 * r + 0.26667 * u, 0.2, 5.0)


def main():
    print(f"Loading demo portfolio from {DATA_PATH} ...")
    df = pd.read_csv(DATA_PATH)
    feat_df = engineer_panel_features(df)
    # latest observation per loan = "current" portfolio snapshot
    feat_df = feat_df.sort_values("reporting_month").groupby("loan_id").last().reset_index()
    features = get_feature_columns()
    X = feat_df[features].fillna(0)
    ead = feat_df["current_balance"].fillna(0).values
    print(f"Portfolio snapshot: {len(feat_df):,} loans, total exposure ${ead.sum():,.0f}")

    default_clf = joblib.load(MODELS_DIR / "calibrated_lgbm_next_12m_default_flag.joblib")
    base_pd = default_clf.predict_proba(X)[:, 1]

    rate_grid = list(range(-300, 301, 50))
    unemp_grid = [round(x * 0.5, 1) for x in range(0, 17)]  # 0.0 to 8.0 step 0.5

    total_exposure = float(ead.sum())
    capital_base = total_exposure * ASSUMED_CAPITAL_BASE_PCT

    grid = []
    for r in rate_grid:
        for u in unemp_grid:
            dm = float(default_mult(r, u))
            stressed_pd = np.clip(base_pd * dm, 0.0, 0.99)
            el = float((stressed_pd * LGD * ead).sum())
            el_pct = el / total_exposure * 100
            car_impact_pct = el / capital_base * 100
            # VaR99 approximation: log-normal loss distribution with CoV=0.6, no live Monte Carlo
            var99 = el * 2.33  # z_0.99 scaling factor applied to an assumed EL-proportional spread
            grid.append({
                "rate_shock_bps": r,
                "unemployment_delta_pct": u,
                "mean_default_prob_pct": round(float(stressed_pd.mean() * 100), 2),
                "mean_prepay_mult": round(float(prepay_mult(r, u)), 3),
                "mean_delinq_mult": round(float(delinq_mult(r, u)), 3),
                "expected_loss_usd": round(el, 2),
                "expected_loss_pct_of_portfolio": round(el_pct, 3),
                "car_impact_pct": round(car_impact_pct, 3),
                "var99_usd": round(var99, 2),
            })

    output = {
        "portfolio_total_exposure_usd": total_exposure,
        "loan_count": int(len(feat_df)),
        "assumptions": {
            "lgd": LGD,
            "assumed_capital_base_pct_of_exposure": ASSUMED_CAPITAL_BASE_PCT,
            "var99_method": "EL x 2.33 (log-normal z-approximation, not live Monte Carlo)",
        },
        "rate_grid_bps": rate_grid,
        "unemployment_grid_pct": unemp_grid,
        "grid": grid,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(output, f)

    print(f"Wrote {len(grid)} grid points to {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
