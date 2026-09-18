"""
Competing-Risk Survival Analysis
===================================
A loan doesn't just "default or not" — it ends one of two ways: default, or
prepayment (paid off early). Treating those as independent is wrong: every
loan that prepays was, at that moment, *removed* from the population at risk
of default. A single-risk Kaplan-Meier curve treats prepayment as if the
loan just vanished (non-informative censoring), which systematically
overstates default risk in any portfolio with active prepayment activity —
exactly the situation a low-rate refinance wave creates.

This script fits both models on the same loan-level event table and reports
the resulting bias, per credit band and at the 12/24/36 month horizons that
actually matter for provisioning decisions. It also derives the empirical
month-over-month state transition matrix (a 7x7 Markov model) that backs the
next_state prediction target.

Usage: python training/survival_analysis.py (run after training/generate_data.py)
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lifelines import AalenJohansenFitter, KaplanMeierFitter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "backend" / "ingest_pipeline" / "models"

STATUS_ORDER = ["Current", "30-59 DPD", "60-89 DPD", "90+ DPD", "Default", "Prepaid", "Paid Off"]
CREDIT_BANDS = ["<620", "620-659", "660-699", "700-739", "740-779", "780+"]


def build_event_table(panel_df: pd.DataFrame) -> pd.DataFrame:
    """One row per loan: duration in months, and which of {censored=0,
    default=1, prepaid=2} ended it (or right-censored if still active)."""
    df = panel_df.sort_values(["loan_id", "month_index"])
    is_default = df["current_status"].isin(["Default"])
    is_prepaid = df["current_status"].isin(["Prepaid", "Paid Off"])

    rows = []
    for loan_id, grp in df.groupby("loan_id", sort=False):
        default_hit = grp.index[is_default.loc[grp.index]]
        prepaid_hit = grp.index[is_prepaid.loc[grp.index]]
        if len(default_hit) and (not len(prepaid_hit) or default_hit[0] < prepaid_hit[0]):
            duration, event = grp.loc[default_hit[0], "month_index"], 1
        elif len(prepaid_hit):
            duration, event = grp.loc[prepaid_hit[0], "month_index"], 2
        else:
            duration, event = grp["month_index"].max(), 0  # right-censored, still active
        rows.append({
            "loan_id": loan_id,
            "duration": max(1, int(duration)),
            "event": event,
            "credit_score_band": grp["credit_score_band"].iloc[0],
        })
    return pd.DataFrame(rows)


def fit_competing_risk_vs_single_risk(event_df: pd.DataFrame) -> dict:
    ajf_default = AalenJohansenFitter()
    ajf_default.fit(event_df["duration"], event_df["event"], event_of_interest=1)
    ajf_prepaid = AalenJohansenFitter()
    ajf_prepaid.fit(event_df["duration"], event_df["event"], event_of_interest=2)

    kmf_default = KaplanMeierFitter()
    kmf_default.fit(event_df["duration"], event_observed=(event_df["event"] == 1).astype(int))
    kmf_prepaid = KaplanMeierFitter()
    kmf_prepaid.fit(event_df["duration"], event_observed=(event_df["event"] == 2).astype(int))

    def _at(series: pd.Series, t: int) -> float:
        idx = series.index[series.index <= t]
        return float(series.loc[idx[-1]]) if len(idx) else 0.0

    cif_d = ajf_default.cumulative_density_.iloc[:, 0]
    cif_p = ajf_prepaid.cumulative_density_.iloc[:, 0]
    single_risk_d = 1.0 - kmf_default.survival_function_.iloc[:, 0]
    single_risk_p = 1.0 - kmf_prepaid.survival_function_.iloc[:, 0]

    comparison = []
    for t in [12, 24, 36]:
        cr_d, sr_d = _at(cif_d, t), _at(single_risk_d, t)
        cr_p, sr_p = _at(cif_p, t), _at(single_risk_p, t)
        comparison.append({
            "horizon_months": t,
            "competing_risk_cif_default": round(cr_d, 4),
            "single_risk_cif_default": round(sr_d, 4),
            "single_risk_bias_pp": round((sr_d - cr_d) * 100, 2),
            "competing_risk_cif_prepaid": round(cr_p, 4),
            "single_risk_cif_prepaid": round(sr_p, 4),
        })

    by_band = {}
    for band in CREDIT_BANDS:
        sub = event_df[event_df["credit_score_band"] == band]
        if len(sub) < 20:
            continue
        ajf_b = AalenJohansenFitter()
        ajf_b.fit(sub["duration"], sub["event"], event_of_interest=1)
        cif_b = ajf_b.cumulative_density_.iloc[:, 0]
        by_band[band] = {
            "n_loans": int(len(sub)),
            "12m_cif_default": round(_at(cif_b, 12), 4),
            "36m_cif_default": round(_at(cif_b, 36), 4),
        }

    return {
        "event_summary": {
            "total_loans": int(len(event_df)),
            "defaulted": int((event_df["event"] == 1).sum()),
            "prepaid": int((event_df["event"] == 2).sum()),
            "censored_still_active": int((event_df["event"] == 0).sum()),
        },
        "competing_vs_single_risk": comparison,
        "cif_by_credit_band": by_band,
        "methodology": (
            "Aalen-Johansen non-parametric CIF (lifelines) for the competing-risk "
            "estimate; cause-specific Kaplan-Meier (1 - survival) for the naive "
            "single-risk comparison, which treats the competing event as "
            "non-informative censoring and is expected to overstate risk."
        ),
    }


def compute_markov_transition_matrix(panel_df: pd.DataFrame) -> dict:
    """Empirical month-over-month P(next_status | current_status)."""
    df = panel_df.sort_values(["loan_id", "month_index"])
    df["next_status"] = df.groupby("loan_id")["current_status"].shift(-1)
    transitions = df.dropna(subset=["next_status"])

    matrix = {}
    for state in STATUS_ORDER:
        sub = transitions[transitions["current_status"] == state]
        if len(sub) == 0:
            continue
        counts = sub["next_status"].value_counts(normalize=True)
        matrix[state] = {s: round(float(counts.get(s, 0.0)), 4) for s in STATUS_ORDER}
    return matrix


def main():
    train_path = RAW_DIR / "loan_monthly_performance_train.csv"
    if not train_path.exists():
        log.error(f"{train_path} not found — run training/generate_data.py first.")
        sys.exit(1)

    df = pd.read_csv(train_path)

    log.info("Building loan-level event table...")
    event_df = build_event_table(df)
    log.info(f"  {len(event_df):,} loans: {(event_df['event']==1).sum():,} default, "
              f"{(event_df['event']==2).sum():,} prepaid, {(event_df['event']==0).sum():,} still active")

    log.info("Fitting Aalen-Johansen competing-risk CIF vs. single-risk Kaplan-Meier...")
    survival_results = fit_competing_risk_vs_single_risk(event_df)
    for row in survival_results["competing_vs_single_risk"]:
        log.info(f"  {row['horizon_months']}m: competing-risk CIF={row['competing_risk_cif_default']}, "
                  f"single-risk CIF={row['single_risk_cif_default']} (bias +{row['single_risk_bias_pp']}pp)")

    log.info("Computing empirical Markov transition matrix...")
    markov = compute_markov_transition_matrix(df)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "survival_analysis.json", "w") as f:
        json.dump({"survival": survival_results, "markov_transition_matrix": markov}, f, indent=2)

    log.info(f"Done. Written to {OUT_DIR / 'survival_analysis.json'}")


if __name__ == "__main__":
    main()
