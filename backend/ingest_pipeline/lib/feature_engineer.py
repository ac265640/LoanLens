"""
Feature Engineering Engine
==========================
Computes the same panel-level features LoanScope's models were trained on,
from raw monthly loan performance rows. Strictly backward-looking (no
forward leakage): every rolling/trajectory feature only uses data up to
month t for a given loan_id.
"""

from typing import List
import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CREDIT_BAND_MAP = {
    "<620": 1, "620-659": 2, "660-699": 3,
    "700-739": 4, "740-779": 5, "780+": 6,
}
LTV_BAND_MAP = {
    "<60%": 1, "60-70%": 2, "70-80%": 3,
    "80-90%": 4, "90-95%": 5, ">95%": 6,
}
DTI_BAND_MAP = {
    "<20%": 1, "20-28%": 2, "28-36%": 3,
    "36-43%": 4, ">43%": 5,
}
STATUS_MAP = {
    "Current": 0, "30-59 DPD": 1, "60-89 DPD": 2,
    "90+ DPD": 3, "Default": 4, "Prepaid": 5, "Paid Off": 6,
}


def engineer_panel_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["loan_id", "month_index"]).reset_index(drop=True)

    df["credit_score_ordinal"] = df["credit_score_band"].map(CREDIT_BAND_MAP).fillna(0).astype(int)
    df["ltv_ordinal"] = df["ltv_band"].map(LTV_BAND_MAP).fillna(0).astype(int)
    df["dti_ordinal"] = df["dti_band"].map(DTI_BAND_MAP).fillna(0).astype(int)
    df["current_status_code"] = df["current_status"].map(STATUS_MAP).fillna(0).astype(int)

    orig_bal = df["original_balance"].replace(0, np.nan)
    df["balance_to_orig_ratio"] = (df["current_balance"] / orig_bal).fillna(1.0).clip(0.0, 3.0)

    median_ir = df["interest_rate"].median()
    df["interest_rate_imputed"] = df["interest_rate"].fillna(median_ir)
    df["interest_rate_is_missing"] = df["interest_rate"].isna().astype(int)
    df["credit_score_is_missing"] = df["credit_score_band"].isna().astype(int)

    df["rate_to_market_spread"] = df["interest_rate_imputed"] - 4.0

    total_term = df["loan_age_months"] + df["remaining_term_months"]
    df["seasoning_ratio"] = (df["loan_age_months"] / total_term.replace(0, 1)).clip(0.0, 1.0)

    grouped = df.groupby("loan_id", group_keys=False)
    df["dpd_roll_max_3m"] = grouped["days_past_due"].rolling(window=3, min_periods=1).max().reset_index(drop=True)
    df["dpd_roll_max_6m"] = grouped["days_past_due"].rolling(window=6, min_periods=1).max().reset_index(drop=True)
    df["dpd_roll_mean_6m"] = grouped["days_past_due"].rolling(window=6, min_periods=1).mean().reset_index(drop=True)

    bal_shift_1 = grouped["current_balance"].shift(1)
    df["balance_change_1m_pct"] = ((df["current_balance"] - bal_shift_1) / bal_shift_1.replace(0, np.nan)).fillna(0.0).clip(-1.0, 1.0)

    bal_shift_3 = grouped["current_balance"].shift(3)
    df["balance_change_3m_pct"] = ((df["current_balance"] - bal_shift_3) / bal_shift_3.replace(0, np.nan)).fillna(0.0).clip(-1.0, 1.0)

    df["is_currently_delinquent"] = (df["days_past_due"] > 0).astype(int)
    df["ever_delinquent_past"] = grouped["is_currently_delinquent"].cummax()

    for cat_col in ["state", "servicer_name", "loan_purpose", "occupancy_type", "property_type", "document_status", "source_system"]:
        if cat_col in df.columns:
            freq = df[cat_col].value_counts(normalize=True).to_dict()
            df[f"{cat_col}_freq"] = df[cat_col].map(freq).fillna(0.0)
        else:
            df[f"{cat_col}_freq"] = 0.0

    df["orig_year"] = pd.to_datetime(df["origination_month"] + "-01", errors="coerce").dt.year.fillna(2018).astype(int)
    df["is_legacy_vintage"] = (df["orig_year"] < 2012).astype(int)

    return df


def get_feature_columns() -> List[str]:
    return [
        "loan_age_months", "remaining_term_months", "original_balance", "current_balance",
        "interest_rate_imputed", "interest_rate_is_missing", "credit_score_is_missing",
        "credit_score_ordinal", "ltv_ordinal", "dti_ordinal", "current_status_code",
        "days_past_due", "modification_flag", "balance_to_orig_ratio", "rate_to_market_spread",
        "seasoning_ratio", "dpd_roll_max_3m", "dpd_roll_max_6m", "dpd_roll_mean_6m",
        "balance_change_1m_pct", "balance_change_3m_pct", "is_currently_delinquent",
        "ever_delinquent_past", "state_freq", "servicer_name_freq", "loan_purpose_freq",
        "occupancy_type_freq", "property_type_freq", "document_status_freq", "source_system_freq",
        "orig_year", "is_legacy_vintage",
    ]
