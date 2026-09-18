"""
Counterfactual Explanations
==============================
For a borderline high-risk loan, "why is this risky" (SHAP) is only half
the useful question. The other half a servicer actually acts on is "what
would change the outcome" — if this borrower's DTI band improved one
level, or their DPD were cured, what would the model actually say?

Unlike a hand-tuned proxy heuristic, this re-runs the *real* trained,
calibrated LightGBM model on the perturbed feature vector — the reported
probability delta is a genuine model output, not an approximation.

Usage: python training/counterfactuals.py (run after train_prediction_models.py)
"""

import json
import logging
import sys
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "ingest_pipeline"))

from lib.feature_engineer import engineer_panel_features, get_feature_columns  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = ROOT / "data" / "raw"
MODELS_DIR = ROOT / "backend" / "ingest_pipeline" / "models"
TARGET = "next_12m_default_flag"


def generate_counterfactuals_for_loan(clf, X_row: pd.DataFrame, features: list) -> list:
    base_prob = float(clf.predict_proba(X_row[features])[:, 1][0])
    counterfactuals = []

    perturbations = {
        "credit_score_ordinal": ("credit score improved one tier", +1, 6),
        "dti_ordinal": ("DTI improved one tier", -1, 1),
        "ltv_ordinal": ("LTV improved one tier", -1, 1),
        "days_past_due": ("DPD cured to 0", None, 0),  # special-cased below
    }

    for feature, (label, step, bound) in perturbations.items():
        if feature not in X_row.columns:
            continue
        current_val = X_row[feature].iloc[0]

        perturbed = X_row.copy()
        if feature == "days_past_due":
            if current_val <= 0:
                continue
            perturbed[feature] = 0
            perturbed["is_currently_delinquent"] = 0
        else:
            new_val = current_val + step
            if (step > 0 and new_val > bound) or (step < 0 and new_val < bound) or new_val == current_val:
                continue
            perturbed[feature] = new_val

        new_prob = float(clf.predict_proba(perturbed[features])[:, 1][0])
        counterfactuals.append({
            "feature": feature,
            "change": label,
            "current_value": float(current_val),
            "counterfactual_value": float(perturbed[feature].iloc[0]),
            "base_probability": round(base_prob, 4),
            "counterfactual_probability": round(new_prob, 4),
            "probability_reduction": round(base_prob - new_prob, 4),
        })

    counterfactuals.sort(key=lambda c: c["probability_reduction"], reverse=True)
    return counterfactuals


def main():
    train_path = RAW_DIR / "loan_monthly_performance_train.csv"
    model_path = MODELS_DIR / f"calibrated_lgbm_{TARGET}.joblib"
    if not train_path.exists() or not model_path.exists():
        log.error("Missing training data or model — run generate_data.py and train_prediction_models.py first.")
        sys.exit(1)

    df = pd.read_csv(train_path)
    feat_df = engineer_panel_features(df)
    feat_df = feat_df.sort_values("reporting_month").groupby("loan_id").last().reset_index()
    features = get_feature_columns()

    clf = joblib.load(model_path)
    probs = clf.predict_proba(feat_df[features].fillna(0))[:, 1]
    feat_df["_risk"] = probs

    # Borderline/high-risk candidates — this is where counterfactuals are
    # actually decision-relevant, not a random Current loan at 3% risk.
    candidates = feat_df[feat_df["_risk"] >= 0.08].sort_values("_risk", ascending=False).head(10)
    if len(candidates) == 0:
        candidates = feat_df.sort_values("_risk", ascending=False).head(10)
    log.info(f"Generating counterfactuals for {len(candidates)} borderline/high-risk loans...")

    results = []
    for _, row in candidates.iterrows():
        X_row = row.to_frame().T[features].fillna(0)
        cfs = generate_counterfactuals_for_loan(clf, X_row, features)
        results.append({
            "loan_id": row["loan_id"],
            "base_probability": round(float(row["_risk"]), 4),
            "counterfactuals": cfs,
        })
        if cfs:
            best = cfs[0]
            log.info(f"  {row['loan_id']}: base={row['_risk']:.1%} -> best lever '{best['change']}' "
                      f"drops it to {best['counterfactual_probability']:.1%}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODELS_DIR / "counterfactuals_report.json", "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"Done. Written to {MODELS_DIR / 'counterfactuals_report.json'}")


if __name__ == "__main__":
    main()
