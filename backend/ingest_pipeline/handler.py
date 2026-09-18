"""
Ingest Pipeline Lambda
=======================
Triggered by Step Functions after a new loan tape lands in S3. Scores 100%
of the uploaded portfolio (vs. the ~5% manual sample review that's standard
in the industry) across 5 LightGBM targets, the hybrid anomaly/exception
model, and the deterministic rule engine — then writes one item per loan
to DynamoDB so the dashboard updates without a page reload.
"""

import io
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import joblib
import numpy as np
import pandas as pd

from lib.feature_engineer import engineer_panel_features, get_feature_columns
from lib.rules import compute_rule_violation_signals

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent / "models"
TABLE_NAME = os.environ.get("LOANS_TABLE", "loanlens-loans")
RUNS_TABLE_NAME = os.environ.get("RUNS_TABLE", "loanlens-runs")

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

_MODEL_CACHE = {}


def _load(name: str):
    if name not in _MODEL_CACHE:
        _MODEL_CACHE[name] = joblib.load(MODELS_DIR / name)
    return _MODEL_CACHE[name]


def _predict_anomaly_scores(df: pd.DataFrame) -> np.ndarray:
    artifact = _load("isolation_forest.joblib")
    iso, features = artifact["model"], artifact["features"]
    min_score, max_score = artifact["min_score"], artifact["max_score"]
    X = df[features].fillna(0)
    raw = iso.decision_function(X)
    norm = 1.0 - ((raw - min_score) / (max_score - min_score + 1e-8))
    return np.clip(norm, 0.0, 1.0)


def score_loan_tape(df: pd.DataFrame) -> pd.DataFrame:
    feat_df = engineer_panel_features(df)
    features = get_feature_columns()
    X = feat_df[features].fillna(0)

    prob_dict = {}
    for target in ["next_3m_delinquency_flag", "next_6m_delinquency_flag", "next_12m_default_flag", "next_12m_prepayment_flag"]:
        clf = _load(f"calibrated_lgbm_{target}.joblib")
        prob_dict[target] = clf.predict_proba(X)[:, 1]

    mc_dict = _load("lgbm_next_state.joblib")
    pred_idx = mc_dict["model"].predict(X)
    pred_next_states = [mc_dict["idx_to_class"][i] for i in pred_idx]

    anom_scores = _predict_anomaly_scores(feat_df)
    feat_df["learned_anomaly_score"] = anom_scores

    rule_df = compute_rule_violation_signals(feat_df)
    hybrid_X = pd.concat([X, rule_df, pd.Series(anom_scores, name="learned_anomaly_score", index=feat_df.index)], axis=1)

    clf_req = _load("exception_required_model.joblib")
    pred_req = (clf_req.predict_proba(hybrid_X)[:, 1] >= 0.5).astype(int)

    type_dict = _load("exception_type_model.joblib")
    type_preds_idx = type_dict["model"].predict(hybrid_X)
    pred_types = [type_dict["idx_to_type"][i] for i in type_preds_idx]
    pred_types = ["None" if pd.isna(t) or str(t) == "nan" else str(t) for t in pred_types]

    medians = X.median()
    top_driver_1, top_driver_2, top_driver_3, actions, confidences = [], [], [], [], []
    driver_cols = ["days_past_due", "credit_score_ordinal", "balance_to_orig_ratio",
                   "interest_rate_imputed", "dpd_roll_max_6m", "balance_change_1m_pct"]

    for idx, row in feat_df.iterrows():
        p_def = prob_dict["next_12m_default_flag"][idx]
        p_del = prob_dict["next_3m_delinquency_flag"][idx]
        anom = anom_scores[idx]
        e_req = pred_req[idx]

        devs = {f: abs(float(row.get(f, 0)) - float(medians.get(f, 0))) / (abs(float(medians.get(f, 0))) + 1e-4) for f in driver_cols}
        sorted_devs = sorted(devs.items(), key=lambda x: x[1], reverse=True)
        top_driver_1.append(sorted_devs[0][0])
        top_driver_2.append(sorted_devs[1][0])
        top_driver_3.append(sorted_devs[2][0])

        if e_req == 1 or anom >= 0.65:
            act = "Audit & Data Quality Exception Review"
        elif p_def >= 0.20:
            act = "Active Credit Workout & Pre-Foreclosure Outreach"
        elif p_del >= 0.25:
            act = "Early Payment Reminder & Watchlist Monitoring"
        elif prob_dict["next_12m_prepayment_flag"][idx] >= 0.35:
            act = "Refinance Retention Campaign"
        else:
            act = "Standard Portfolio Surveillance"
        actions.append(act)
        confidences.append(max(0.60, float(round(abs(p_def - 0.5) * 2.0, 4))))

    result = pd.DataFrame({
        "loan_id": feat_df["loan_id"],
        "reporting_month": feat_df["reporting_month"],
        "state": feat_df.get("state", ""),
        "current_status": feat_df["current_status"],
        "days_past_due": feat_df["days_past_due"],
        "current_balance": feat_df["current_balance"],
        "credit_score_band": feat_df.get("credit_score_band", ""),
        "prob_next_3m_delinquency": np.round(prob_dict["next_3m_delinquency_flag"], 4),
        "prob_next_6m_delinquency": np.round(prob_dict["next_6m_delinquency_flag"], 4),
        "prob_next_12m_default": np.round(prob_dict["next_12m_default_flag"], 4),
        "prob_next_12m_prepayment": np.round(prob_dict["next_12m_prepayment_flag"], 4),
        "next_state": pred_next_states,
        "exception_required": pred_req,
        "exception_type": pred_types,
        "anomaly_score": np.round(anom_scores, 4),
        "top_driver_1": top_driver_1,
        "top_driver_2": top_driver_2,
        "top_driver_3": top_driver_3,
        "recommended_action": actions,
        "confidence": confidences,
    })

    # Latest observation per loan — this is the "state of the portfolio today" view
    return result.sort_values("reporting_month").groupby("loan_id").last().reset_index()


def _write_to_dynamodb(scored: pd.DataFrame, run_id: str) -> dict:
    table = dynamodb.Table(TABLE_NAME)
    now = datetime.now(timezone.utc).isoformat()
    counts = {"total": 0, "high_risk": 0, "exceptions": 0}

    with table.batch_writer(overwrite_by_pkeys=["loan_id"]) as batch:
        for _, row in scored.iterrows():
            item = row.to_dict()
            item["loan_id"] = str(item["loan_id"])
            item["scored_at"] = now
            item["run_id"] = run_id
            for k, v in item.items():
                if isinstance(v, (np.floating,)):
                    item[k] = round(float(v), 4)
                elif isinstance(v, (np.integer,)):
                    item[k] = int(v)
                elif isinstance(v, float):
                    item[k] = round(v, 4)
            batch.put_item(Item=item)
            counts["total"] += 1
            if item["prob_next_12m_default"] >= 0.20:
                counts["high_risk"] += 1
            if item["exception_required"] == 1:
                counts["exceptions"] += 1

    return counts


def handler(event, context):
    """
    event: { "bucket": "...", "key": "raw/tape.csv", "run_id": "..." }
    """
    bucket = event["bucket"]
    key = event["key"]
    run_id = event.get("run_id", str(int(time.time())))

    log.info(f"Scoring loan tape s3://{bucket}/{key} (run_id={run_id})")
    obj = s3.get_object(Bucket=bucket, Key=key)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))
    log.info(f"Loaded {len(df):,} rows across {df['loan_id'].nunique():,} loans")

    scored = score_loan_tape(df)
    counts = _write_to_dynamodb(scored, run_id)

    runs_table = dynamodb.Table(RUNS_TABLE_NAME)
    runs_table.put_item(Item={
        "run_id": run_id,
        "status": "COMPLETE",
        "source_key": key,
        "loans_scored": counts["total"],
        "high_risk_count": counts["high_risk"],
        "exception_count": counts["exceptions"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })

    log.info(f"Run {run_id} complete: {counts}")
    return {"run_id": run_id, **counts}
