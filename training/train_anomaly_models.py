"""
Anomaly & Exception Model Training
=====================================
Two-component hybrid anomaly engine:

  1. Isolation Forest (unsupervised) — learns what "normal" looks like
     across the engineered feature space and scores how isolated / unusual
     each record is. Catches patterns nobody wrote an explicit rule for.
  2. Deterministic rule engine (VR001-VR005, see backend/ingest_pipeline/
     lib/rules.py) — hand-written, 100%-precision logical constraints
     (e.g. a "Paid Off" loan can't still carry a balance).

A hybrid LightGBM classifier then combines both signal families to predict
whether a record needs a human exception review, and what kind. Neither
signal alone is enough: rules catch only what's explicitly encoded, and
the Isolation Forest alone can't explain itself to a reviewer.

Usage: python training/train_anomaly_models.py (run after train_prediction_models.py)
"""

import logging
import sys
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import f1_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "ingest_pipeline"))

from lib.feature_engineer import engineer_panel_features, get_feature_columns  # noqa: E402
from lib.rules import compute_rule_violation_signals  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = ROOT / "data" / "raw"
MODELS_DIR = ROOT / "backend" / "ingest_pipeline" / "models"


def train_isolation_forest(feat_df: pd.DataFrame) -> np.ndarray:
    features = get_feature_columns()
    X = feat_df[features].fillna(0)

    log.info(f"Training Isolation Forest on {len(X):,} records, {len(features)} features...")
    iso = IsolationForest(n_estimators=150, max_samples="auto", contamination=0.03, random_state=42, n_jobs=-1)
    iso.fit(X)

    raw_scores = iso.decision_function(X)
    min_s, max_s = raw_scores.min(), raw_scores.max()
    scores = np.clip(1.0 - ((raw_scores - min_s) / (max_s - min_s + 1e-8)), 0.0, 1.0)

    joblib.dump({"model": iso, "features": features, "min_score": float(min_s), "max_score": float(max_s)}, MODELS_DIR / "isolation_forest.joblib")
    log.info(f"  anomaly score range=[{scores.min():.4f}, {scores.max():.4f}], mean={scores.mean():.4f}")
    return scores


def train_exception_models(feat_df: pd.DataFrame, anomaly_scores: np.ndarray):
    features = get_feature_columns()
    rule_df = compute_rule_violation_signals(feat_df)
    X = pd.concat([feat_df[features].fillna(0), rule_df, pd.Series(anomaly_scores, name="learned_anomaly_score", index=feat_df.index)], axis=1)

    # exception_required: binary
    y_req = feat_df["exception_required"].values
    scale_weight = max(1.0, float((len(y_req) - y_req.sum()) / max(y_req.sum(), 1)))
    log.info(f"Training exception_required classifier (pos={int(y_req.sum())}/{len(y_req)}, scale_pos_weight={scale_weight:.2f})...")

    clf_req = lgb.LGBMClassifier(n_estimators=150, learning_rate=0.05, num_leaves=31, scale_pos_weight=scale_weight, random_state=42, n_jobs=-1, verbose=-1)
    clf_req.fit(X, y_req)
    req_probs = clf_req.predict_proba(X)[:, 1]
    req_auc = round(float(roc_auc_score(y_req, req_probs)), 4)
    req_f1 = round(float(f1_score(y_req, (req_probs >= 0.5).astype(int), zero_division=0)), 4)
    log.info(f"  exception_required -> roc_auc={req_auc}, f1={req_f1}")
    joblib.dump(clf_req, MODELS_DIR / "exception_required_model.joblib")

    # exception_type: multiclass
    y_type_str = feat_df["exception_type"].astype(str)
    classes = sorted(y_type_str.unique())
    type_to_idx = {c: i for i, c in enumerate(classes)}
    idx_to_type = {i: c for c, i in type_to_idx.items()}

    log.info(f"Training exception_type classifier across {len(classes)} classes...")
    clf_type = lgb.LGBMClassifier(objective="multiclass", num_class=len(classes), n_estimators=150, learning_rate=0.05, class_weight="balanced", random_state=42, n_jobs=-1, verbose=-1)
    clf_type.fit(X, y_type_str.map(type_to_idx).values)
    macro_f1 = round(float(f1_score(y_type_str.map(type_to_idx).values, clf_type.predict(X), average="macro", zero_division=0)), 4)
    log.info(f"  exception_type -> macro_f1={macro_f1}")

    joblib.dump({"model": clf_type, "type_to_idx": type_to_idx, "idx_to_type": idx_to_type, "features": list(X.columns)}, MODELS_DIR / "exception_type_model.joblib")

    return {"exception_required": {"roc_auc": req_auc, "f1": req_f1}, "exception_type": {"macro_f1": macro_f1, "classes": classes}}


def main():
    train_path = RAW_DIR / "loan_monthly_performance_train.csv"
    if not train_path.exists():
        log.error(f"{train_path} not found — run training/generate_data.py first.")
        sys.exit(1)

    df = pd.read_csv(train_path)
    feat_df = engineer_panel_features(df)

    anomaly_scores = train_isolation_forest(feat_df)
    metrics = train_exception_models(feat_df, anomaly_scores)

    log.info(f"Done. {metrics}")


if __name__ == "__main__":
    main()
