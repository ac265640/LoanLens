"""
Macro Scenario Segment Breakdowns
=====================================
The Shockwave sliders (scripts/precompute_stress_grid.py) give a live,
portfolio-wide view of stress impact. This complements it with the
question a risk committee actually asks next: "stress hits the portfolio
overall, but which *segment* absorbs most of it?" Runs the same 3 named
macro scenarios from data/macro_scenarios.csv (base / adverse_credit /
high_prepayment) and breaks the resulting 12M default rate down by credit
band, vintage era, and top states.

Usage: python training/scenario_segments.py (run after train_prediction_models.py)
"""

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "ingest_pipeline"))

from lib.feature_engineer import engineer_panel_features, get_feature_columns  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = ROOT / "data" / "raw"
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "backend" / "ingest_pipeline" / "models"


def apply_scenario(feat_df: pd.DataFrame, X: pd.DataFrame, clf, scenario: pd.Series) -> np.ndarray:
    rate_shock = float(scenario["rate_shock_bps"]) / 100.0
    unemp_delta = float(scenario["unemployment_delta_pct"])
    hpa_delta = float(scenario["hpa_delta_pct"])
    def_mult = float(scenario["default_multiplier"])

    X_stress = X.copy()
    X_stress["interest_rate_imputed"] += rate_shock
    X_stress["rate_to_market_spread"] += rate_shock
    if hpa_delta < 0:
        X_stress["ltv_ordinal"] = np.clip(X_stress["ltv_ordinal"] + 1, 1, 6)
    if unemp_delta > 0:
        X_stress["dti_ordinal"] = np.clip(X_stress["dti_ordinal"] + 1, 1, 5)

    raw_probs = clf.predict_proba(X_stress)[:, 1]
    return np.clip(raw_probs * def_mult, 0.0, 0.99)


def segment_breakdown(feat_df: pd.DataFrame, stressed_prob: pd.Series, group_col: str, top_n: int = None) -> dict:
    df = feat_df.copy()
    df["stressed_prob"] = stressed_prob
    groups = df.groupby(group_col)["stressed_prob"].agg(["mean", "count"])
    if top_n:
        groups = groups.loc[df[group_col].value_counts().head(top_n).index]
    return {
        str(idx): {"mean_12m_default_prob_pct": round(float(row["mean"] * 100), 2), "n_loans": int(row["count"])}
        for idx, row in groups.iterrows()
    }


def main():
    train_path = RAW_DIR / "loan_monthly_performance_train.csv"
    scenarios_path = DATA_DIR / "macro_scenarios.csv"
    model_path = MODELS_DIR / "calibrated_lgbm_next_12m_default_flag.joblib"
    if not train_path.exists() or not scenarios_path.exists() or not model_path.exists():
        log.error("Missing inputs — run generate_data.py and train_prediction_models.py first.")
        sys.exit(1)

    df = pd.read_csv(train_path)
    feat_df = engineer_panel_features(df)
    feat_df = feat_df.sort_values("reporting_month").groupby("loan_id").last().reset_index()
    features = get_feature_columns()
    X = feat_df[features].fillna(0)

    feat_df["vintage_era"] = np.where(
        feat_df["orig_year"] <= 2010, "Pre-2010",
        np.where(feat_df["orig_year"] <= 2018, "2011-2018", "2019+"),
    )

    clf = joblib.load(model_path)
    scenarios = pd.read_csv(scenarios_path)

    results = {}
    for _, scenario in scenarios.iterrows():
        name = scenario["scenario_name"]
        log.info(f"Applying scenario '{name}': rate={scenario['rate_shock_bps']}bps, "
                  f"unemployment={scenario['unemployment_delta_pct']:+.1f}pp, HPI={scenario['hpa_delta_pct']:+.1f}%...")
        stressed_prob = apply_scenario(feat_df, X, clf, scenario)

        results[name] = {
            "description": scenario["description"],
            "portfolio_mean_12m_default_pct": round(float(stressed_prob.mean() * 100), 2),
            "by_credit_band": segment_breakdown(feat_df, stressed_prob, "credit_score_band"),
            "by_vintage_era": segment_breakdown(feat_df, stressed_prob, "vintage_era"),
            "by_top_5_states": segment_breakdown(feat_df, stressed_prob, "state", top_n=5),
        }
        log.info(f"  portfolio mean 12M default: {results[name]['portfolio_mean_12m_default_pct']}%")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODELS_DIR / "scenario_segment_report.json", "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"Done. Written to {MODELS_DIR / 'scenario_segment_report.json'}")


if __name__ == "__main__":
    main()
