"""
Multi-Horizon Risk Prediction Training
=========================================
Trains one LightGBM model per business question a portfolio team actually
asks, rather than a single generic "risk score":

  next_3m_delinquency_flag   -> who needs a call this quarter (early warning)
  next_6m_delinquency_flag   -> watch-list for the next two quarters
  next_12m_default_flag      -> capital provisioning horizon
  next_12m_prepayment_flag   -> cash-flow / refinance planning
  next_state                 -> month-over-month status transition

Binary targets are then Platt-calibrated (sigmoid CalibratedClassifierCV)
on the held-out validation cohort so a "12% default probability" means the
same thing across the whole portfolio, not just a rank ordering.

Usage: python training/train_prediction_models.py
"""

import json
import logging
import sys
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "ingest_pipeline"))

from lib.feature_engineer import engineer_panel_features, get_feature_columns  # noqa: E402
from splitter import time_aware_split  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = ROOT / "data" / "raw"
MODELS_DIR = ROOT / "backend" / "ingest_pipeline" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

BINARY_TARGETS = {
    "next_3m_delinquency_flag": dict(n_estimators=150, learning_rate=0.05, num_leaves=31, max_depth=6, min_child_samples=25),
    "next_6m_delinquency_flag": dict(n_estimators=150, learning_rate=0.05, num_leaves=31, max_depth=6, min_child_samples=25),
    "next_12m_default_flag": dict(n_estimators=180, learning_rate=0.04, num_leaves=31, max_depth=6, min_child_samples=30),
    "next_12m_prepayment_flag": dict(n_estimators=120, learning_rate=0.04, num_leaves=25, max_depth=5, min_child_samples=40),
}


def train_binary_targets(X_train, y_train_df, X_val, y_val_df) -> dict:
    report = {}
    for target, cfg in BINARY_TARGETS.items():
        y_train, y_val = y_train_df[target].values, y_val_df[target].values
        log.info(f"Training {target} (pos={int(y_train.sum())}/{len(y_train)})...")

        clf = lgb.LGBMClassifier(
            **cfg, subsample=0.85, colsample_bytree=0.85, random_state=42, n_jobs=-1, verbose=-1
        )
        clf.fit(X_train, y_train)
        joblib.dump(clf, MODELS_DIR / f"lgbm_{target}.joblib")

        # Platt calibration on the held-out validation cohort
        calibrated = CalibratedClassifierCV(estimator=clf, method="sigmoid", cv="prefit")
        calibrated.fit(X_val, y_val)
        joblib.dump(calibrated, MODELS_DIR / f"calibrated_lgbm_{target}.joblib")

        probs = calibrated.predict_proba(X_val)[:, 1]
        preds = (probs >= 0.5).astype(int)
        metrics = {
            "roc_auc": round(float(roc_auc_score(y_val, probs)), 4),
            "pr_auc": round(float(average_precision_score(y_val, probs)), 4),
            "brier": round(float(brier_score_loss(y_val, probs)), 4),
            "f1": round(float(f1_score(y_val, preds, zero_division=0)), 4),
        }
        log.info(f"  {target} -> {metrics}")
        report[target] = metrics
    return report


def train_next_state(X_train, y_train_df, X_val, y_val_df) -> dict:
    log.info("Training next_state (multiclass)...")
    y_train_str = y_train_df["next_state"].astype(str)
    y_val_str = y_val_df["next_state"].astype(str)
    classes = sorted(y_train_str.unique())
    class_to_idx = {c: i for i, c in enumerate(classes)}
    idx_to_class = {i: c for c, i in class_to_idx.items()}

    clf = lgb.LGBMClassifier(
        objective="multiclass", num_class=len(classes), n_estimators=200,
        learning_rate=0.06, num_leaves=31, max_depth=6, class_weight="balanced",
        random_state=42, n_jobs=-1, verbose=-1,
    )
    clf.fit(X_train, y_train_str.map(class_to_idx).values)

    val_preds = clf.predict(X_val)
    macro_f1 = round(float(f1_score(y_val_str.map(class_to_idx).values, val_preds, average="macro", zero_division=0)), 4)
    log.info(f"  next_state -> macro_f1={macro_f1}")

    joblib.dump({"model": clf, "class_to_idx": class_to_idx, "idx_to_class": idx_to_class}, MODELS_DIR / "lgbm_next_state.joblib")
    return {"macro_f1": macro_f1, "classes": classes}


def main():
    train_path = RAW_DIR / "loan_monthly_performance_train.csv"
    if not train_path.exists():
        log.error(f"{train_path} not found — run training/generate_data.py first.")
        sys.exit(1)

    df = pd.read_csv(train_path)
    train_raw, val_raw = time_aware_split(df, val_cutoff="2020-01-01")

    train_feat = engineer_panel_features(train_raw)
    val_feat = engineer_panel_features(val_raw)
    features = get_feature_columns()
    X_train, X_val = train_feat[features].fillna(0), val_feat[features].fillna(0)

    report = {}
    report.update(train_binary_targets(X_train, train_feat, X_val, val_feat))
    report["next_state"] = train_next_state(X_train, train_feat, X_val, val_feat)

    with open(MODELS_DIR / "prediction_metrics.json", "w") as f:
        json.dump(report, f, indent=2)
    log.info(f"Done. Metrics written to {MODELS_DIR / 'prediction_metrics.json'}")


if __name__ == "__main__":
    main()
