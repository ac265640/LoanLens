"""
Data Intelligence & Quality Profiling
=========================================
Before anything gets modeled or scored, this asks: can we trust the data?
Computes a per-record Data Quality (DQ) score from explicit, documented
penalties (not a black-box heuristic), and separately diagnoses *why*
values are missing — a missing credit score on a 2005-vintage loan and a
missing credit score on a 2023-vintage loan are not the same kind of
problem, and treating them the same (e.g. naive mean-imputation) would
quietly bias every downstream model.

Usage: python training/profile_data.py (run after training/generate_data.py)
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "backend" / "ingest_pipeline" / "models"

# Penalty points, clamped to [0, 100] — each is an explicit, auditable rule
# rather than an opaque score, so a reviewer can trace exactly why a batch
# of records scored low.
PENALTIES = {
    "date_anomaly": 35.0,       # reporting_month < origination_month
    "paidoff_balance": 30.0,    # Paid Off / Prepaid but balance > $1,000
    "default_low_dpd": 25.0,    # Default status but DPD < 60
    "rate_outlier": 15.0,       # interest_rate > 15%
    "balance_outlier": 15.0,    # current_balance > 2x original_balance
    "missing_credit_score": 10.0,
    "missing_interest_rate": 5.0,
    "missing_document": 5.0,
}


def compute_record_quality_scores(df: pd.DataFrame) -> pd.Series:
    scores = np.full(len(df), 100.0)

    rep_dt = pd.to_datetime(df["reporting_month"] + "-01", errors="coerce")
    orig_dt = pd.to_datetime(df["origination_month"] + "-01", errors="coerce")
    scores -= (rep_dt < orig_dt).fillna(False).astype(float) * PENALTIES["date_anomaly"]

    scores -= (df["current_status"].isin(["Paid Off", "Prepaid"]) & (df["current_balance"] > 1000)).fillna(False).astype(float) * PENALTIES["paidoff_balance"]
    scores -= ((df["current_status"] == "Default") & (df["days_past_due"] < 60)).fillna(False).astype(float) * PENALTIES["default_low_dpd"]
    scores -= (df["interest_rate"] > 15.0).fillna(False).astype(float) * PENALTIES["rate_outlier"]
    scores -= (df["current_balance"] > df["original_balance"] * 2.0).fillna(False).astype(float) * PENALTIES["balance_outlier"]
    scores -= df["credit_score_band"].isna().astype(float) * PENALTIES["missing_credit_score"]
    scores -= df["interest_rate"].isna().astype(float) * PENALTIES["missing_interest_rate"]
    scores -= (df["document_status"] == "Missing Items").fillna(False).astype(float) * PENALTIES["missing_document"]

    return pd.Series(np.clip(scores, 0.0, 100.0), index=df.index, name="data_quality_score")


def diagnose_missingness(df: pd.DataFrame) -> dict:
    """Classify each column with missing values as MCAR / MAR / MNAR using
    Little's-style heuristics: correlate the missingness indicator against
    observed numeric features and against origination vintage."""
    cols_with_missing = [c for c in df.columns if df[c].isna().sum() > 0]
    result = {}

    df = df.copy()
    df["orig_year"] = pd.to_datetime(df["origination_month"] + "-01", errors="coerce").dt.year

    for col in cols_with_missing:
        miss = df[col].isna().astype(int)
        pct = round(float(miss.mean() * 100), 3)

        # Vintage-conditional missingness rate: the tell for MNAR in loan data
        by_vintage = df.groupby("orig_year")[col].apply(lambda s: s.isna().mean())
        vintage_spread = float(by_vintage.max() - by_vintage.min()) if len(by_vintage) > 1 else 0.0

        correlations = {}
        for other in df.select_dtypes(include=[np.number]).columns:
            if other == col or other == "orig_year":
                continue
            valid = ~df[other].isna()
            if valid.sum() > 10:
                corr, _ = stats.pointbiserialr(miss[valid], df[other][valid])
                if not np.isnan(corr) and abs(corr) > 0.03:
                    correlations[other] = round(float(corr), 4)

        if vintage_spread > 0.10:
            mechanism = "MNAR"
            rationale = (
                f"Missingness rate varies by {vintage_spread*100:.1f}pp across origination "
                f"vintages ({by_vintage.idxmin():.0f}: {by_vintage.min()*100:.1f}% -> "
                f"{by_vintage.idxmax():.0f}: {by_vintage.max()*100:.1f}%) — the value's own "
                f"unobserved history (how old the record-keeping is) predicts whether it's "
                f"missing, which is the definition of Missing Not At Random."
            )
        elif correlations:
            top = max(correlations.items(), key=lambda kv: abs(kv[1]))
            mechanism = "MAR"
            rationale = f"Missingness correlates with observed `{top[0]}` (r={top[1]})."
        else:
            mechanism = "MCAR"
            rationale = "No significant dependency on vintage or other observed features — missingness looks unconditional."

        result[col] = {
            "missing_pct": pct,
            "vintage_spread_pp": round(vintage_spread * 100, 2),
            "correlated_with": correlations,
            "inferred_mechanism": mechanism,
            "rationale": rationale,
        }

    return result


def main():
    train_path = RAW_DIR / "loan_monthly_performance_train.csv"
    if not train_path.exists():
        log.error(f"{train_path} not found — run training/generate_data.py first.")
        sys.exit(1)

    df = pd.read_csv(train_path)
    log.info(f"Profiling {len(df):,} records...")

    dq = compute_record_quality_scores(df)
    mean_dq = float(dq.mean())
    grade = "A" if mean_dq >= 95 else "B" if mean_dq >= 85 else "C" if mean_dq >= 75 else "D/F"
    log.info(f"Data quality score: {mean_dq:.2f}/100 (Grade {grade})")

    missingness = diagnose_missingness(df)
    for col, info in missingness.items():
        log.info(f"  {col}: {info['missing_pct']}% missing -> {info['inferred_mechanism']}")

    report = {
        "n_records": int(len(df)),
        "n_loans": int(df["loan_id"].nunique()),
        "quality_score": {
            "mean": round(mean_dq, 2),
            "median": round(float(dq.median()), 2),
            "grade": grade,
            "pct_records_below_75": round(float((dq < 75).mean() * 100), 2),
        },
        "missingness_diagnosis": missingness,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "data_quality_report.json", "w") as f:
        json.dump(report, f, indent=2)
    log.info(f"Done. Written to {OUT_DIR / 'data_quality_report.json'}")


if __name__ == "__main__":
    main()
