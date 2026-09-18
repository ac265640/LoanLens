"""
Split Conformal Prediction Intervals
========================================
A calibrated probability is still a point estimate — "12%" doesn't say how
confident the model is in that specific 12%. Split conformal prediction
gives a genuine, distribution-free guarantee: at 90% target coverage, the
true outcome falls inside the reported [lower, upper] band for at least
90% of loans, with no assumption about the underlying probability
distribution — only that the calibration and eval sets are exchangeable.

Method: nonconformity score = |y - p_hat| on a held-out calibration split
carved out of the validation cohort; the interval half-width is the
(1-alpha)-quantile of those scores, applied uniformly. This is the
textbook inductive/split-conformal approach, deliberately simple and
auditable rather than an adaptive (locally-varying) variant.

Usage: python training/conformal_intervals.py (run after train_prediction_models.py)
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
from splitter import time_aware_split  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = ROOT / "data" / "raw"
MODELS_DIR = ROOT / "backend" / "ingest_pipeline" / "models"
TARGET = "next_12m_default_flag"
ALPHA = 0.10  # 90% target coverage


def compute_conformal_interval(clf, X_calib, y_calib, X_eval, alpha: float = ALPHA):
    p_calib = clf.predict_proba(X_calib)[:, 1]
    nonconformity = np.abs(y_calib - p_calib)

    n = len(nonconformity)
    q_level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    half_width = float(np.quantile(nonconformity, q_level))

    p_eval = clf.predict_proba(X_eval)[:, 1]
    lower = np.clip(p_eval - half_width, 0.0, 1.0)
    upper = np.clip(p_eval + half_width, 0.0, 1.0)
    return p_eval, lower, upper, half_width


def empirical_coverage(y_true: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    return float(((y_true >= lower) & (y_true <= upper)).mean())


def main():
    train_path = RAW_DIR / "loan_monthly_performance_train.csv"
    model_path = MODELS_DIR / f"lgbm_{TARGET}.joblib"
    if not train_path.exists() or not model_path.exists():
        log.error("Missing training data or model — run generate_data.py and train_prediction_models.py first.")
        sys.exit(1)

    df = pd.read_csv(train_path)
    train_raw, val_raw = time_aware_split(df, val_cutoff="2020-01-01")
    val_feat = engineer_panel_features(val_raw)
    features = get_feature_columns()

    # Split the validation cohort itself into a conformal calibration half
    # and an eval half, by loan_id so no loan appears in both.
    loan_ids = val_feat["loan_id"].unique()
    rng = np.random.RandomState(42)
    rng.shuffle(loan_ids)
    split_point = len(loan_ids) // 2
    calib_ids, eval_ids = set(loan_ids[:split_point]), set(loan_ids[split_point:])

    calib_df = val_feat[val_feat["loan_id"].isin(calib_ids)]
    eval_df = val_feat[val_feat["loan_id"].isin(eval_ids)]
    log.info(f"Conformal calibration set: {len(calib_df):,} rows, eval set: {len(eval_df):,} rows")

    clf = joblib.load(model_path)
    X_calib, y_calib = calib_df[features].fillna(0), calib_df[TARGET].values
    X_eval, y_eval = eval_df[features].fillna(0), eval_df[TARGET].values

    p_eval, lower, upper, half_width = compute_conformal_interval(clf, X_calib, y_calib, X_eval)
    coverage = empirical_coverage(y_eval, lower, upper)
    mean_width = float((upper - lower).mean())

    log.info(f"Target coverage: {(1-ALPHA)*100:.0f}%, half-width={half_width:.4f}")
    log.info(f"Empirical coverage on held-out eval set: {coverage*100:.2f}% "
              f"(should be >= target since split-conformal is conservative)")
    log.info(f"Mean interval width: {mean_width:.4f}")

    # A few worked examples for the report
    examples = []
    top_idx = np.argsort(-p_eval)[:5]
    eval_loan_ids = eval_df["loan_id"].values
    for i in top_idx:
        examples.append({
            "loan_id": str(eval_loan_ids[i]),
            "point_estimate": round(float(p_eval[i]), 4),
            "interval_90pct": [round(float(lower[i]), 4), round(float(upper[i]), 4)],
            "actual_outcome": int(y_eval[i]),
        })

    report = {
        "target_coverage": 1 - ALPHA,
        "method": "split conformal (inductive), nonconformity = |y - p_hat|, uniform half-width",
        "calibration_set_size": int(len(calib_df)),
        "eval_set_size": int(len(eval_df)),
        "interval_half_width": round(half_width, 4),
        "empirical_coverage_on_eval": round(coverage, 4),
        "mean_interval_width": round(mean_width, 4),
        "worked_examples_highest_risk": examples,
    }

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODELS_DIR / "conformal_intervals_report.json", "w") as f:
        json.dump(report, f, indent=2)
    log.info(f"Done. Written to {MODELS_DIR / 'conformal_intervals_report.json'}")


if __name__ == "__main__":
    main()
