"""
Explainability & Fairness Audit
===================================
A risk score nobody can explain doesn't survive contact with a real credit
committee. This produces three things a reviewer or regulator would
actually ask for:

  1. TreeSHAP global feature importance + a worked local example — exactly
     which features pushed one specific loan's risk up or down, and by how
     much (the same SHAP values the Bedrock copilot's memos reference).
  2. A calibration reliability diagnostic — when the model says "12% risk",
     do 12% of those loans actually default? (Expected Calibration Error.)
  3. A fairness / disparate-impact audit across credit tiers and states —
     the four-fifths rule from US fair-lending guidance, applied to model
     flag rates rather than left as an assumption.

Usage: python training/explainability.py (run after train_prediction_models.py)
"""

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "ingest_pipeline"))

from lib.feature_engineer import engineer_panel_features, get_feature_columns  # noqa: E402
from splitter import time_aware_split  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = ROOT / "data" / "raw"
MODELS_DIR = ROOT / "backend" / "ingest_pipeline" / "models"
TARGET = "next_12m_default_flag"


def compute_shap_explanations(clf, X: pd.DataFrame, n_local_examples: int = 3) -> dict:
    explainer = shap.TreeExplainer(clf)
    shap_values = explainer.shap_values(X)
    if isinstance(shap_values, list):  # binary classifiers sometimes return [class0, class1]
        shap_values = shap_values[1]

    global_importance = (
        pd.Series(np.abs(shap_values).mean(axis=0), index=X.columns)
        .sort_values(ascending=False)
        .round(4)
    )

    # Worked local examples: the highest-risk loans in this sample, so the
    # explanation is actually interesting rather than a random Current loan.
    risk_order = clf.predict_proba(X)[:, 1].argsort()[::-1][:n_local_examples]
    local_examples = []
    for i in risk_order:
        row_shap = pd.Series(shap_values[i], index=X.columns).sort_values(key=abs, ascending=False)
        local_examples.append({
            "row_index": int(i),
            "predicted_prob": round(float(clf.predict_proba(X.iloc[[i]])[:, 1][0]), 4),
            "base_value": round(float(explainer.expected_value if not isinstance(explainer.expected_value, (list, np.ndarray)) else explainer.expected_value[1]), 4),
            "top_drivers": [
                {"feature": f, "shap_contribution": round(float(v), 4), "feature_value": round(float(X.iloc[i][f]), 4)}
                for f, v in row_shap.head(5).items()
            ],
        })

    return {
        "global_importance_top15": global_importance.head(15).to_dict(),
        "worked_local_examples": local_examples,
    }


def compute_calibration_diagnostics(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> dict:
    bins = np.linspace(0, 1, n_bins + 1)
    bin_idx = np.clip(np.digitize(y_prob, bins) - 1, 0, n_bins - 1)

    ece = 0.0
    curve = []
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.sum() == 0:
            continue
        bin_conf = float(y_prob[mask].mean())
        bin_acc = float(y_true[mask].mean())
        weight = mask.sum() / len(y_true)
        ece += weight * abs(bin_acc - bin_conf)
        curve.append({"predicted_bin_mean": round(bin_conf, 4), "actual_empirical_rate": round(bin_acc, 4), "n": int(mask.sum())})

    return {"expected_calibration_error": round(ece, 4), "reliability_curve": curve}


def audit_fairness(df: pd.DataFrame, group_col: str, y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.10) -> dict:
    y_pred = (y_prob >= threshold).astype(int)
    overall_pos_rate = float(y_pred.mean())
    groups = {}
    for g in sorted(df[group_col].dropna().unique()):
        mask = (df[group_col] == g).values
        if mask.sum() < 30:
            continue
        g_true, g_pred, g_prob = y_true[mask], y_pred[mask], y_prob[mask]
        pos_rate = float(g_pred.mean())
        neg_mask = g_true == 0
        groups[str(g)] = {
            "n": int(mask.sum()),
            "actual_default_rate": round(float(g_true.mean()), 4),
            "predicted_positive_rate": round(pos_rate, 4),
            "demographic_parity_ratio": round(pos_rate / (overall_pos_rate + 1e-9), 4),
            "false_positive_rate": round(float(g_pred[neg_mask].mean()), 4) if neg_mask.sum() else 0.0,
            "subgroup_auc": round(float(roc_auc_score(g_true, g_prob)), 4) if len(np.unique(g_true)) > 1 else None,
        }

    ratios = [m["demographic_parity_ratio"] for m in groups.values()]
    passes_four_fifths = bool(ratios) and min(ratios) >= 0.80

    return {
        "threshold": threshold,
        "by_group": groups,
        "four_fifths_rule": {
            "description": "Demographic parity ratio between 0.80 and 1.25 across groups is the standard US fair-lending threshold.",
            "min_ratio_observed": round(min(ratios), 4) if ratios else None,
            "passes": passes_four_fifths,
        },
    }


def main():
    train_path = RAW_DIR / "loan_monthly_performance_train.csv"
    model_path = MODELS_DIR / f"lgbm_{TARGET}.joblib"
    if not train_path.exists() or not model_path.exists():
        log.error("Missing training data or model — run generate_data.py and train_prediction_models.py first.")
        sys.exit(1)

    df = pd.read_csv(train_path)
    _, val_raw = time_aware_split(df, val_cutoff="2020-01-01")
    val_feat = engineer_panel_features(val_raw)
    features = get_feature_columns()
    X_val = val_feat[features].fillna(0)

    clf = joblib.load(model_path)
    y_true = val_feat[TARGET].values
    y_prob = clf.predict_proba(X_val)[:, 1]

    log.info("Computing TreeSHAP global + local explanations...")
    shap_report = compute_shap_explanations(clf, X_val)
    log.info(f"  Top 3 global drivers: {list(shap_report['global_importance_top15'].keys())[:3]}")

    log.info("Computing calibration reliability diagnostics...")
    cal_report = compute_calibration_diagnostics(y_true, y_prob)
    log.info(f"  Expected Calibration Error: {cal_report['expected_calibration_error']}")

    log.info("Running fairness / disparate-impact audit across credit bands and states...")
    fairness_credit = audit_fairness(val_feat, "credit_score_band", y_true, y_prob)
    top_states = val_feat["state"].value_counts().head(10).index
    state_mask = val_feat["state"].isin(top_states)
    fairness_state = audit_fairness(val_feat[state_mask], "state", y_true[state_mask.values], y_prob[state_mask.values])
    log.info(f"  Four-fifths rule (credit band): passes={fairness_credit['four_fifths_rule']['passes']}")

    report = {
        "evaluated_target": TARGET,
        "shap_explanations": shap_report,
        "calibration_diagnostics": cal_report,
        "fairness_audit": {"by_credit_band": fairness_credit, "by_state": fairness_state},
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODELS_DIR / "explainability_report.json", "w") as f:
        json.dump(report, f, indent=2)
    log.info(f"Done. Written to {MODELS_DIR / 'explainability_report.json'}")


if __name__ == "__main__":
    main()
