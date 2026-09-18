"""
Synthetic Loan Performance Data Generator
==========================================
Generates all 7 organizer-format data files for the Loan Performance Intelligence Engine.

Scale: ~50,000 loans x up to 36 months
Seed:  42 (fixed for reproducibility)

Output files:
  - data/raw/loan_monthly_performance_train.csv
  - data/raw/loan_monthly_performance_test.csv
  - data/raw/loan_static_attributes.csv
  - data/raw/servicer_updates.csv
  - data/data_dictionary.md
  - data/validation_rules.json
  - data/macro_scenarios.csv
  - submission/submission_template.csv
"""

import os
import sys
import json
import random
import logging
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
DATA_DIR = ROOT / "data"
SUBMISSION_DIR = ROOT / "submission"

RAW_DIR.mkdir(parents=True, exist_ok=True)
SUBMISSION_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

SEED = 42
N_LOANS = 50_000
MAX_MONTHS = 36
DEFAULT_RATE = 0.04
PREPAYMENT_RATE = 0.06
DELINQUENCY_3M_RATE = 0.08

STATES = [
    "CA", "TX", "FL", "NY", "IL", "PA", "OH", "GA", "NC", "MI",
    "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI",
]
CREDIT_BANDS = ["<620", "620-659", "660-699", "700-739", "740-779", "780+"]
LTV_BANDS = ["<60%", "60-70%", "70-80%", "80-90%", "90-95%", ">95%"]
DTI_BANDS = ["<20%", "20-28%", "28-36%", "36-43%", ">43%"]
LOAN_PURPOSES = ["Purchase", "Refinance", "Cash-Out Refinance", "Home Improvement"]
OCCUPANCY_TYPES = ["Primary", "Second Home", "Investment"]
PROPERTY_TYPES = ["Single Family", "Condo", "Multi-Family", "Townhouse", "Manufactured"]
SERVICERS = ["Servicer_A", "Servicer_B", "Servicer_C", "Servicer_D", "Servicer_E"]
SOURCE_SYSTEMS = ["CoreLogic", "Black Knight", "Ellie Mae", "Encompass"]
DOC_STATUSES = ["Complete", "Pending Review", "Missing Items", "Under Exception"]

CREDIT_BAND_DEFAULT_MULT = {
    "<620": 3.5, "620-659": 2.0, "660-699": 1.3,
    "700-739": 0.9, "740-779": 0.6, "780+": 0.35, "MISSING": 1.5,
}

LTV_DEFAULT_MULT = {
    "<60%": 0.5, "60-70%": 0.7, "70-80%": 0.9,
    "80-90%": 1.2, "90-95%": 1.5, ">95%": 2.0,
}

DTI_DEFAULT_MULT = {
    "<20%": 0.6, "20-28%": 0.8, "28-36%": 1.0,
    "36-43%": 1.3, ">43%": 1.8,
}

STATE_HAZARD_MULT = {s: 1.0 for s in STATES}
STATE_HAZARD_MULT.update({"FL": 1.3, "CA": 0.85, "TX": 1.1, "NY": 0.9})


def get_vintage_mult(orig_year: int) -> float:
    if orig_year <= 2007:
        return 1.6
    elif orig_year <= 2010:
        return 1.4
    elif orig_year <= 2015:
        return 1.1
    elif orig_year <= 2019:
        return 1.0
    else:
        return 0.85


def generate_loan_statics(n_loans: int) -> pd.DataFrame:
    log.info(f"Generating {n_loans:,} loan static attributes...")
    loan_ids = [f"LN{str(i).zfill(7)}" for i in range(1, n_loans + 1)]

    orig_months_pool = pd.date_range("2003-01", "2023-06", freq="MS")
    orig_months_choice = np.random.choice(orig_months_pool, size=n_loans)
    orig_months_str = [pd.Timestamp(d).strftime("%Y-%m") for d in orig_months_choice]

    original_balances = np.random.lognormal(mean=11.8, sigma=0.55, size=n_loans)
    original_balances = np.clip(original_balances, 50_000, 2_000_000).astype(int)

    interest_rates = np.random.normal(4.5, 1.2, size=n_loans)
    interest_rates = np.clip(interest_rates, 2.0, 12.0).round(3)
    outlier_mask = np.random.random(n_loans) < 0.01
    interest_rates[outlier_mask] = np.random.uniform(15.0, 25.0, outlier_mask.sum())

    credit_bands = np.random.choice(CREDIT_BANDS, size=n_loans, p=[0.08, 0.12, 0.20, 0.25, 0.20, 0.15])
    ltv_bands = np.random.choice(LTV_BANDS, size=n_loans, p=[0.10, 0.15, 0.30, 0.25, 0.12, 0.08])
    dti_bands = np.random.choice(DTI_BANDS, size=n_loans, p=[0.15, 0.30, 0.30, 0.15, 0.10])
    states = np.random.choice(STATES, size=n_loans)
    loan_purposes = np.random.choice(LOAN_PURPOSES, size=n_loans, p=[0.40, 0.30, 0.20, 0.10])
    occupancy_types = np.random.choice(OCCUPANCY_TYPES, size=n_loans, p=[0.75, 0.10, 0.15])
    property_types = np.random.choice(PROPERTY_TYPES, size=n_loans, p=[0.60, 0.15, 0.10, 0.10, 0.05])
    servicer_names = np.random.choice(SERVICERS, size=n_loans)
    loan_terms = np.random.choice([180, 240, 360], size=n_loans, p=[0.10, 0.10, 0.80])

    df = pd.DataFrame({
        "loan_id": loan_ids,
        "origination_month": orig_months_str,
        "original_balance": original_balances,
        "interest_rate": interest_rates,
        "credit_score_band": credit_bands,
        "ltv_band": ltv_bands,
        "dti_band": dti_bands,
        "state": states,
        "loan_purpose": loan_purposes,
        "occupancy_type": occupancy_types,
        "property_type": property_types,
        "servicer_name": servicer_names,
        "loan_term_months": loan_terms,
    })

    # MNAR: credit_score_band missing more for older vintages
    orig_years = pd.to_datetime(df["origination_month"] + "-01").dt.year
    missing_prob = np.where(orig_years < 2010, 0.15, np.where(orig_years < 2015, 0.05, 0.01))
    miss_mask = np.random.random(n_loans) < missing_prob
    df.loc[miss_mask, "credit_score_band"] = np.nan

    # MCAR: ~3% of interest_rate missing completely at random
    mcar_mask = np.random.random(n_loans) < 0.03
    df.loc[mcar_mask, "interest_rate"] = np.nan

    return df


def generate_panel_fast(statics: pd.DataFrame, max_months: int = MAX_MONTHS) -> pd.DataFrame:
    """Fast vectorized panel generator with realistic financial dynamics."""
    log.info(f"Generating monthly performance records for {len(statics):,} loans...")

    records = []
    # Pre-extract arrays for speed
    loan_ids = statics["loan_id"].values
    orig_months_str = statics["origination_month"].values
    orig_balances = statics["original_balance"].values
    rates = statics["interest_rate"].values
    c_bands = statics["credit_score_band"].fillna("MISSING").values
    ltv_b = statics["ltv_band"].values
    dti_b = statics["dti_band"].values
    states = statics["state"].values
    purposes = statics["loan_purpose"].values
    occupancies = statics["occupancy_type"].values
    properties = statics["property_type"].values
    servicers = statics["servicer_name"].values
    terms = statics["loan_term_months"].values

    n_loans = len(statics)
    durations = np.random.randint(8, max_months + 1, size=n_loans)

    for i in range(n_loans):
        lid = loan_ids[i]
        orig_str = orig_months_str[i]
        orig_dt = pd.Timestamp(orig_str + "-01")
        orig_bal = float(orig_balances[i])
        ir = float(rates[i]) if not np.isnan(rates[i]) else 4.5
        cb = c_bands[i]
        ltv = ltv_b[i]
        dti = dti_b[i]
        st = states[i]
        purp = purposes[i]
        occ = occupancies[i]
        prop = properties[i]
        serv = servicers[i]
        term = int(terms[i])
        n_m = int(durations[i])

        # Hazard rates
        cb_mult = CREDIT_BAND_DEFAULT_MULT.get(cb, 1.0)
        ltv_mult = LTV_DEFAULT_MULT.get(ltv, 1.0)
        dti_mult = DTI_DEFAULT_MULT.get(dti, 1.0)
        st_mult = STATE_HAZARD_MULT.get(st, 1.0)
        yr_mult = get_vintage_mult(orig_dt.year)

        comb_mult = cb_mult * ltv_mult * dti_mult * st_mult * yr_mult
        def_h = min(DEFAULT_RATE / 12.0 * comb_mult, 0.04)
        prep_h = min(PREPAYMENT_RATE / 12.0 * (1.0 / max(cb_mult, 0.5)), 0.06)
        del_h = min(DELINQUENCY_3M_RATE / 12.0 * comb_mult, 0.05)

        curr_bal = orig_bal
        status = "Current"
        dpd = 0
        mod_flag = 0
        def_flag = 0
        prep_flag = 0
        source_sys = SOURCE_SYSTEMS[i % len(SOURCE_SYSTEMS)]
        doc_stat = DOC_STATUSES[i % len(DOC_STATUSES)]

        ir_monthly = ir / 100.0 / 12.0

        loan_rows = []

        for m in range(1, n_m + 1):
            rep_dt = orig_dt + pd.DateOffset(months=m)
            rem_term = max(0, term - m)

            # Amortization
            if status not in ("Default", "Prepaid", "Paid Off"):
                if ir_monthly > 0:
                    tot_pay = orig_bal * (ir_monthly * (1 + ir_monthly) ** term) / ((1 + ir_monthly) ** term - 1)
                    princ = max(0, tot_pay - curr_bal * ir_monthly)
                else:
                    princ = orig_bal / term
                curr_bal = max(0.0, curr_bal - princ)

            disp_bal = curr_bal
            disp_dpd = dpd

            # Outlier injections (~0.3%)
            if np.random.random() < 0.003:
                disp_bal = curr_bal * 2.2
            if np.random.random() < 0.003:
                disp_dpd = np.random.randint(180, 400)

            # State transitions
            r = np.random.random()
            if status == "Current":
                if r < def_h:
                    status = "Default"
                    def_flag = 1
                    dpd = 90
                elif r < def_h + prep_h:
                    status = "Prepaid"
                    prep_flag = 1
                    disp_bal = 0.0
                elif r < def_h + prep_h + del_h:
                    status = "30-59 DPD"
                    dpd = 30
                elif rem_term == 0:
                    status = "Paid Off"
                    disp_bal = 0.0
            elif status == "30-59 DPD":
                if r < 0.35:
                    status = "Current"
                    dpd = 0
                elif r < 0.55:
                    status = "60-89 DPD"
                    dpd = 60
                elif r < 0.70:
                    status = "Default"
                    def_flag = 1
                    dpd = 90
            elif status == "60-89 DPD":
                if r < 0.25:
                    status = "Current"
                    dpd = 0
                elif r < 0.55:
                    status = "90+ DPD"
                    dpd = 120
                else:
                    status = "Default"
                    def_flag = 1
                    dpd = 90

            # Modification
            if status in ("30-59 DPD", "60-89 DPD", "90+ DPD") and np.random.random() < 0.03:
                mod_flag = 1

            loss_band = "None"
            if status == "Default":
                loss_band = "<20%" if np.random.random() < 0.3 else "35-50%"

            # Date anomaly injection (~0.2%)
            rep_month_str = rep_dt.strftime("%Y-%m")
            if np.random.random() < 0.002:
                bad_dt = orig_dt - pd.DateOffset(months=2)
                rep_month_str = bad_dt.strftime("%Y-%m")

            # Balance contradiction injection (~0.4%)
            if status == "Paid Off" and np.random.random() < 0.004:
                disp_bal = np.random.uniform(5000, 35000)

            loan_rows.append({
                "loan_id": lid,
                "month_index": m,
                "reporting_month": rep_month_str,
                "origination_month": orig_str,
                "loan_age_months": m,
                "remaining_term_months": rem_term,
                "original_balance": orig_bal,
                "current_balance": round(disp_bal, 2),
                "interest_rate": rates[i],
                "credit_score_band": None if cb == "MISSING" else cb,
                "ltv_band": ltv,
                "dti_band": dti,
                "state": st,
                "loan_purpose": purp,
                "occupancy_type": occ,
                "property_type": prop,
                "servicer_name": serv,
                "current_status": status,
                "days_past_due": disp_dpd,
                "modification_flag": mod_flag,
                "prepayment_flag": prep_flag,
                "default_flag": def_flag,
                "loss_severity_band": loss_band,
                "last_updated_at": rep_dt.strftime("%Y-%m-%d"),
                "source_system": source_sys,
                "document_status": doc_stat,
            })

            if status in ("Default", "Prepaid", "Paid Off"):
                break

        records.extend(loan_rows)

    panel_df = pd.DataFrame(records)
    log.info(f"Generated {len(panel_df):,} panel rows.")
    return panel_df


def add_forward_targets_and_exceptions(df: pd.DataFrame) -> pd.DataFrame:
    """Add forward-looking targets and deterministic exception labels."""
    log.info("Computing forward targets and validation exception labels...")
    df = df.sort_values(["loan_id", "month_index"]).reset_index(drop=True)

    # Shift operations per loan for fast target generation
    grouped = df.groupby("loan_id", group_keys=False)

    # 1. next_state: 1-month forward status
    next_s = grouped["current_status"].shift(-1)
    df["next_state"] = next_s.fillna(df["current_status"])

    # 2. next_3m_delinquency
    is_delinq_or_def = df["current_status"].isin(["30-59 DPD", "60-89 DPD", "90+ DPD", "Default"]).astype(int)
    # Forward rolling max
    del_3m = grouped.apply(lambda g: is_delinq_or_def.loc[g.index].iloc[::-1].rolling(3, min_periods=1).max().iloc[::-1].shift(-1))
    df["next_3m_delinquency_flag"] = del_3m.fillna(0).astype(int)

    # 3. next_6m_delinquency
    del_6m = grouped.apply(lambda g: is_delinq_or_def.loc[g.index].iloc[::-1].rolling(6, min_periods=1).max().iloc[::-1].shift(-1))
    df["next_6m_delinquency_flag"] = del_6m.fillna(0).astype(int)

    # 4. next_12m_default
    is_def = (df["default_flag"] == 1).astype(int)
    def_12m = grouped.apply(lambda g: is_def.loc[g.index].iloc[::-1].rolling(12, min_periods=1).max().iloc[::-1].shift(-1))
    df["next_12m_default_flag"] = def_12m.fillna(0).astype(int)

    # 5. next_12m_prepayment
    is_prep = (df["prepayment_flag"] == 1).astype(int)
    prep_12m = grouped.apply(lambda g: is_prep.loc[g.index].iloc[::-1].rolling(12, min_periods=1).max().iloc[::-1].shift(-1))
    df["next_12m_prepayment_flag"] = prep_12m.fillna(0).astype(int)

    # Deterministic exception rules
    r_dt = pd.to_datetime(df["reporting_month"] + "-01", errors="coerce")
    o_dt = pd.to_datetime(df["origination_month"] + "-01", errors="coerce")
    cond_date = (r_dt < o_dt).fillna(False)
    cond_bal = (df["current_status"] == "Paid Off") & (df["current_balance"] > 1000)
    cond_dpd = (df["current_status"] == "Default") & (df["days_past_due"] < 60)
    cond_doc = (df["document_status"] == "Missing Items") & (df["modification_flag"] == 1)
    cond_grow = df["current_balance"] > (df["original_balance"] * 2.0)

    exception_req = np.zeros(len(df), dtype=int)
    exception_type = np.full(len(df), "None", dtype=object)

    exception_req[cond_date] = 1
    exception_type[cond_date] = "Date Anomaly"

    exception_req[cond_bal] = 1
    exception_type[cond_bal] = "Balance Inconsistency"

    exception_req[cond_dpd] = 1
    exception_type[cond_dpd] = "Data Conflict"

    exception_req[cond_doc] = 1
    exception_type[cond_doc] = "Missing Document"

    exception_req[cond_grow] = 1
    exception_type[cond_grow] = "Valuation Discrepancy"

    df["exception_required"] = exception_req
    df["exception_type"] = exception_type

    return df


def generate_servicer_updates(train_df: pd.DataFrame) -> pd.DataFrame:
    log.info("Generating servicer_updates.csv...")
    sample = train_df.sample(frac=0.25, random_state=SEED)[
        ["loan_id", "reporting_month", "current_balance", "current_status", "days_past_due"]
    ].copy()

    conflict_mask = np.random.random(len(sample)) < 0.05
    noise = np.random.uniform(0.85, 1.25, len(sample))
    sample.loc[conflict_mask, "current_balance"] = (
        sample.loc[conflict_mask, "current_balance"] * noise[conflict_mask]
    ).round(2)

    status_conflicts = conflict_mask & (sample["current_status"] != "Current")
    sample.loc[status_conflicts, "current_status"] = "Current"

    sample["update_source"] = "Servicer Direct Feed"
    sample["conflict_flag"] = conflict_mask.astype(int)
    sample["last_servicer_update"] = pd.Timestamp("2024-01-01")
    return sample


def main(n_loans: int = N_LOANS, max_months: int = MAX_MONTHS):
    np.random.seed(SEED)
    random.seed(SEED)
    log.info(f"=== Synthetic Data Generation (N_LOANS={n_loans:,}) ===")

    # 1. Statics
    statics = generate_loan_statics(n_loans)
    statics.to_csv(RAW_DIR / "loan_static_attributes.csv", index=False)
    log.info("✓ loan_static_attributes.csv")

    # 2. Panel
    panel = generate_panel_fast(statics, max_months=max_months)
    panel = add_forward_targets_and_exceptions(panel)

    # 3. Time-aware split: Train <= 2021-12, Test >= 2022-01
    dates = pd.to_datetime(panel["origination_month"] + "-01")
    cutoff = pd.Timestamp("2022-01-01")
    train_mask = dates < cutoff
    test_mask = dates >= cutoff

    train_df = panel[train_mask].copy()
    test_df = panel[test_mask].copy()

    # Remove any overlap if present
    train_ids = set(train_df["loan_id"].unique())
    test_df = test_df[~test_df["loan_id"].isin(train_ids)].copy()

    train_df.to_csv(RAW_DIR / "loan_monthly_performance_train.csv", index=False)
    test_df.to_csv(RAW_DIR / "loan_monthly_performance_test.csv", index=False)
    log.info(f"✓ train.csv ({len(train_df):,} rows, {train_df['loan_id'].nunique():,} loans)")
    log.info(f"✓ test.csv  ({len(test_df):,} rows, {test_df['loan_id'].nunique():,} loans)")

    # 4. Servicer updates
    servicer = generate_servicer_updates(train_df)
    servicer.to_csv(RAW_DIR / "servicer_updates.csv", index=False)
    log.info("✓ servicer_updates.csv")

    # 5. Macro scenarios
    macro_df = pd.DataFrame([
        {
            "scenario_name": "base",
            "rate_shock_bps": 0,
            "unemployment_delta_pct": 0.0,
            "hpa_delta_pct": 0.0,
            "prepayment_multiplier": 1.0,
            "default_multiplier": 1.0,
            "delinquency_multiplier": 1.0,
            "description": "Base case — steady macro environment.",
        },
        {
            "scenario_name": "adverse_credit",
            "rate_shock_bps": 150,
            "unemployment_delta_pct": 2.5,
            "hpa_delta_pct": -8.0,
            "prepayment_multiplier": 0.6,
            "default_multiplier": 2.2,
            "delinquency_multiplier": 1.8,
            "description": "Adverse credit stress: rate rise 150bps, unemployment +2.5pp, HPI -8%.",
        },
        {
            "scenario_name": "high_prepayment",
            "rate_shock_bps": -75,
            "unemployment_delta_pct": -0.5,
            "hpa_delta_pct": 5.0,
            "prepayment_multiplier": 2.5,
            "default_multiplier": 0.75,
            "delinquency_multiplier": 0.8,
            "description": "High prepayment: rates drop 75bps, refi boom.",
        },
    ])
    macro_df.to_csv(DATA_DIR / "macro_scenarios.csv", index=False)
    log.info("✓ macro_scenarios.csv")

    # 6. Validation rules
    rules = {
        "version": "1.0",
        "description": "Deterministic validation rules for loan panel data quality checks.",
        "rules": [
            {"rule_id": "VR001", "name": "date_order_check", "condition": "reporting_month >= origination_month", "severity": "critical", "exception_type": "Date Anomaly"},
            {"rule_id": "VR002", "name": "paid_off_balance_check", "condition": "current_status == 'Paid Off' → current_balance <= 1000", "severity": "high", "exception_type": "Balance Inconsistency"},
            {"rule_id": "VR003", "name": "default_dpd_check", "condition": "current_status == 'Default' → days_past_due >= 60", "severity": "high", "exception_type": "Data Conflict"},
            {"rule_id": "VR004", "name": "modification_document_check", "condition": "modification_flag == 1 → document_status != 'Missing Items'", "severity": "medium", "exception_type": "Missing Document"},
            {"rule_id": "VR005", "name": "balance_growth_check", "condition": "current_balance <= original_balance * 2.0", "severity": "high", "exception_type": "Valuation Discrepancy"},
        ],
    }
    with open(DATA_DIR / "validation_rules.json", "w") as f:
        json.dump(rules, f, indent=2)
    log.info("✓ validation_rules.json")

    # 7. Submission template
    last_obs = test_df.sort_values(["loan_id", "month_index"]).groupby("loan_id").last().reset_index()
    template = pd.DataFrame({
        "loan_id": last_obs["loan_id"],
        "reporting_month": last_obs["reporting_month"],
        "prob_next_3m_delinquency": "",
        "prob_next_6m_delinquency": "",
        "prob_next_12m_default": "",
        "prob_next_12m_prepayment": "",
        "next_state": "",
        "exception_required": "",
        "exception_type": "",
        "anomaly_score": "",
        "top_driver_1": "",
        "top_driver_2": "",
        "top_driver_3": "",
        "recommended_action": "",
        "confidence": "",
    })
    template.to_csv(SUBMISSION_DIR / "submission_template.csv", index=False)
    log.info(f"✓ submission_template.csv ({len(template):,} rows)")
    log.info("✅ Phase 1 Data Generation Complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-loans", type=int, default=N_LOANS)
    parser.add_argument("--max-months", type=int, default=MAX_MONTHS)
    args = parser.parse_args()
    main(args.n_loans, args.max_months)
